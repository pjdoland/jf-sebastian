"""
RVC (Retrieval-based Voice Conversion) processor module.
Uses rvc-python library for direct in-process voice conversion.
"""

import gc
import logging
import threading
import time
import tempfile
import os
from datetime import datetime
from typing import Optional, Tuple
from pathlib import Path
import numpy as np
import soundfile as sf

from jf_sebastian.config import settings
from jf_sebastian.utils.async_file_utils import save_async

logger = logging.getLogger(__name__)

# Fix faiss OpenMP conflict with PyTorch on macOS
# Both libraries use OpenMP and can conflict, causing crashes
# Setting OMP_NUM_THREADS=1 prevents the conflict
if 'OMP_NUM_THREADS' not in os.environ:
    os.environ['OMP_NUM_THREADS'] = '1'
    logger.debug("Set OMP_NUM_THREADS=1 to prevent faiss/PyTorch OpenMP conflict")

# Patch torch.load BEFORE importing rvc-python
# PyTorch 2.6+ changed default weights_only from False to True
# Fairseq models require weights_only=False
try:
    import torch
    _original_torch_load = torch.load

    def _patched_torch_load(*args, **kwargs):
        """Patched torch.load that sets weights_only=False for compatibility."""
        kwargs['weights_only'] = False
        return _original_torch_load(*args, **kwargs)

    torch.load = _patched_torch_load
    logger.debug("Applied torch.load patch for fairseq compatibility")
except Exception as e:
    logger.warning(f"Failed to patch torch.load: {e}")

# Try to import RVC library
try:
    from rvc_python.infer import RVCInference
    RVC_AVAILABLE = True
    logger.info("rvc-python library is available")
except ImportError as e:
    RVC_AVAILABLE = False
    logger.warning(f"rvc-python library not available: {e}")
    logger.warning("Voice conversion will not be available.")
    RVCInference = None


# Backoff (seconds) before each retry attempt of vc_single. Index 0 = wait
# before attempt 2, index 1 = wait before attempt 3, etc. The first retry
# is short because most transient failures recover quickly; later retries
# wait longer for the nvmap allocator to settle after a true cold start.
_RETRY_BACKOFFS = (0.5, 1.5, 3.0)


class RVCProcessor:
    """
    Handles RVC voice conversion using rvc-python library.

    Uses direct library calls with GPU acceleration (MPS/CUDA) support.
    """

    def __init__(self, device: str = "cpu"):
        """
        Initialize RVC processor.

        Args:
            device: Device to use for inference ('cpu', 'mps', or 'cuda')
        """
        self._available = RVC_AVAILABLE
        self._device = self._validate_device(device)
        self._rvc_instance = None
        self._loaded_model_path = None
        self._permanently_failed = False
        # Serializes concurrent convert_audio() callers. rvc.vc.set_params and
        # rvc.load_model mutate shared instance state on the rvc-python side;
        # without this lock, a scheduler-thread warmup running concurrently
        # with a wake-word-triggered conversion (during the IDLE window
        # before the scheduled event's atomic SPEAKING CAS) can tear the
        # parameter set or model-load state.
        self._conversion_lock = threading.Lock()

        if not self._available:
            logger.error("rvc-python library not available")
        else:
            logger.info(f"RVC processor initialized (direct library, device={self._device})")

    @staticmethod
    def _validate_device(device: str) -> str:
        """Validate that the requested PyTorch device is actually available, fall back if not."""
        try:
            import torch
            if device == "cuda" and torch.cuda.is_available():
                return "cuda"
            if device == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            if device in ("cuda", "mps"):
                logger.warning(f"Requested device '{device}' is not available, falling back to CPU")
                return "cpu"
        except ImportError:
            pass
        return device

    @property
    def available(self) -> bool:
        """Check if RVC library is available."""
        return self._available

    def _release_gpu_memory(self):
        """Drop Python refs and free PyTorch's CUDA cache.

        Jetson's nvmap allocator (the kernel-level GPU memory manager backing
        the unified-memory pool) intermittently returns ENOMEM under load,
        which surfaces as NVML_SUCCESS asserts inside PyTorch's caching
        allocator. Running gc.collect + empty_cache clears whatever is
        freeable so the next allocation has a clean budget.
        """
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    @staticmethod
    def _parse_vc_result(result, target_sr: int) -> Tuple[Optional[np.ndarray], Optional[int], str]:
        """Unpack a vc_single() return value.

        rvc-python returns either a raw ndarray, a (message, (sr, audio))
        tuple, or None. Returns (audio, sr, reason) where audio is None on
        failure and reason describes why.
        """
        if result is None:
            return None, None, "vc_single returned None"
        if isinstance(result, np.ndarray):
            return result, target_sr, ""
        if isinstance(result, tuple) and len(result) == 2:
            message, audio_result = result
            if audio_result is None or not isinstance(audio_result, tuple):
                return None, None, f"failed: {message}"
            sr, audio = audio_result
            if audio is None:
                return None, None, f"produced no audio: {message}"
            return audio, sr, ""
        return None, None, f"unexpected result format: {type(result)}"

    @staticmethod
    def _save_debug_audio(audio: np.ndarray, sample_rate: int, kind: str, timestamp: str) -> None:
        """Async-save a debug snapshot of audio (input or output of RVC)."""
        path = Path('debug_audio') / f'rvc_{kind}_{timestamp}.wav'
        save_async(sf.write, str(path), audio, sample_rate, subtype='PCM_16')
        logger.info(f"Saving RVC {kind} to {path} ({sample_rate}Hz, async)")

    def _get_rvc_instance(self) -> Optional['RVCInference']:
        """Get or create RVC inference instance."""
        if not self._available:
            return None

        if self._rvc_instance is None:
            try:
                logger.debug(f"Creating RVC inference instance with device={self._device}")
                self._rvc_instance = RVCInference(device=self._device)
            except Exception as e:
                logger.error(f"Failed to create RVC instance: {e}", exc_info=True)
                return None

        return self._rvc_instance

    def convert_audio(
        self,
        audio: np.ndarray,
        sample_rate: int,
        model_path: str,
        index_path: Optional[str] = None,
        pitch_shift: int = 0,
        index_rate: float = 0.5,
        f0_method: str = "harvest",
        filter_radius: int = 3,
        rms_mix_rate: float = 0.25,
        protect: float = 0.33,
        max_attempts: int = 3,
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Convert audio through RVC model using rvc-python library.

        Args:
            audio: Input audio array (float32, -1.0 to 1.0)
            sample_rate: Audio sample rate (Hz)
            model_path: Path to RVC model file
            index_path: Optional path to index file
            pitch_shift: Pitch shift in semitones (-12 to +12)
            index_rate: Feature retrieval influence (0.0 to 1.0)
            f0_method: Pitch extraction method (harvest/crepe/pm/dio/rmvpe)
            filter_radius: Median filtering radius for pitch (0-7)
            rms_mix_rate: Volume envelope mix rate (0.0 to 1.0)
            protect: Protect voiceless consonants (0.0 to 0.5)

        Returns:
            Tuple of (converted_audio, sample_rate) or None on failure
        """
        if not self._available:
            logger.warning("RVC library not available, skipping conversion")
            return None

        if self._permanently_failed:
            logger.debug("RVC permanently failed, skipping conversion")
            return None

        # Validate model path
        if not Path(model_path).exists():
            logger.error(f"RVC model not found: {model_path}")
            return None

        # Get RVC instance
        rvc = self._get_rvc_instance()
        if rvc is None:
            return None

        # Create temporary file for input audio
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as input_file:
            input_path = input_file.name

            # Serialize across threads — rvc.load_model / rvc.set_params /
            # rvc.vc.vc_single all mutate shared state on the wrapped rvc
            # instance. Most reachable race: a scheduled-event warmup running
            # on the scheduler thread while a wake-word-triggered conversion
            # runs on the recorder thread.
            with self._conversion_lock:
                try:
                    logger.debug(f"Converting audio through RVC (f0={f0_method}, pitch={pitch_shift}, device={self._device}, sr={sample_rate}Hz)")
                    start_time = time.time()

                    timestamp = None
                    if settings.SAVE_DEBUG_AUDIO:
                        Path('debug_audio').mkdir(exist_ok=True)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        self._save_debug_audio(audio, sample_rate, 'input', timestamp)

                    # Write input audio to temp file (expecting 16kHz)
                    sf.write(input_path, audio, sample_rate, subtype='PCM_16')

                    # Load model if not already loaded or if different model
                    if self._loaded_model_path != model_path:
                        logger.debug(f"Loading RVC model: {model_path}")
                        rvc.load_model(model_path, index_path=index_path or '')
                        self._loaded_model_path = model_path

                    # Set conversion parameters
                    logger.debug(f"Setting RVC parameters (f0={f0_method}, pitch={pitch_shift})...")
                    rvc.set_params(
                        f0method=f0_method,
                        f0up_key=pitch_shift,
                        index_rate=index_rate,
                        filter_radius=filter_radius,
                        rms_mix_rate=rms_mix_rate,
                        protect=protect
                    )

                    # Retry on inner failure. On Jetson the first inference
                    # after a long idle period sometimes hits nvmap ENOMEM /
                    # NVML asserts because the allocator state went cold; the
                    # backoff gives it time to recover. Backoffs are explicit
                    # rather than computed so they match the docstring above.
                    # Worst-case sleep total: sum(_RETRY_BACKOFFS[:max_attempts-1])
                    # plus per-attempt inference time (~1.3 s on Jetson).
                    converted_audio: Optional[np.ndarray] = None
                    converted_sr: Optional[int] = None
                    failure_reason = "unknown"

                    for attempt in range(1, max_attempts + 1):
                        try:
                            logger.debug(f"Performing RVC conversion (attempt {attempt}/{max_attempts})...")
                            result = rvc.vc.vc_single(
                                sid=0,
                                input_audio_path=input_path,
                                f0_up_key=pitch_shift,
                                f0_file=None,
                                f0_method=f0_method,
                                file_index=index_path or '',
                                file_index2='',
                                index_rate=index_rate,
                                filter_radius=filter_radius,
                                resample_sr=0,
                                rms_mix_rate=rms_mix_rate,
                                protect=protect
                            )
                            converted_audio, converted_sr, failure_reason = self._parse_vc_result(result, rvc.vc.tgt_sr)
                        except Exception as e:
                            # Inner CUDA/torch failure (e.g. NVML allocator on Jetson)
                            converted_audio = None
                            failure_reason = f"raised: {type(e).__name__}: {e}"

                        if converted_audio is not None:
                            break

                        if attempt < max_attempts:
                            # Backoff before the next attempt. Indexed by
                            # (attempt - 1): 0.5 s before attempt 2, 1.5 s
                            # before attempt 3, 3.0 s before attempt 4. Use
                            # the last entry for any attempt past the table.
                            backoff_s = _RETRY_BACKOFFS[min(attempt - 1, len(_RETRY_BACKOFFS) - 1)]
                            logger.warning(
                                f"RVC attempt {attempt}/{max_attempts} failed ({failure_reason}); "
                                f"freeing GPU memory and retrying after {backoff_s:.1f}s"
                            )
                            self._release_gpu_memory()
                            time.sleep(backoff_s)

                    if converted_audio is None:
                        logger.error(
                            f"RVC conversion failed after {max_attempts} attempts: {failure_reason}"
                        )
                        # Forget the cached model path so the next call
                        # force-reloads. The rvc-python instance state may
                        # be torn after a string of failed inferences and
                        # we don't want the next caller to skip load_model
                        # based on a stale cache hit.
                        self._loaded_model_path = None
                        return None

                    if timestamp is not None:
                        self._save_debug_audio(converted_audio.copy(), converted_sr, 'output', timestamp)

                    # RVC library returns audio in int16 value range (-32768 to 32767) as float32 dtype
                    # Normalize to proper float32 range (-1.0 to 1.0)
                    converted_audio = converted_audio.astype(np.float32) / 32768.0

                    logger.info(f"RVC output normalized and ready at {converted_sr}Hz")

                    elapsed = time.time() - start_time
                    logger.info(f"RVC conversion completed in {elapsed:.2f}s")

                    self._release_gpu_memory()
                    return converted_audio, converted_sr

                except RuntimeError as e:
                    # Device errors (MPS/CUDA unavailable) are permanent — don't retry
                    logger.error(f"RVC conversion failed permanently: {e}", exc_info=True)
                    self._permanently_failed = True
                    self._loaded_model_path = None
                    return None

                except Exception as e:
                    logger.error(f"RVC conversion failed: {e}", exc_info=True)
                    self._loaded_model_path = None
                    return None

                finally:
                    # Clean up temporary file (still inside the lock — cheap)
                    try:
                        Path(input_path).unlink(missing_ok=True)
                    except Exception as e:
                        logger.warning(f"Failed to clean up temp file: {e}")

    def warmup(
        self,
        model_path: str,
        index_path: Optional[str] = None,
        pitch_shift: int = 0,
        f0_method: str = "harvest"
    ) -> bool:
        """
        Warm up RVC by loading model and running a quick inference.
        This eliminates the first-use delay by pre-loading the model and
        initializing all the inference components.

        Args:
            model_path: Path to RVC model file
            index_path: Optional path to index file
            pitch_shift: Pitch shift in semitones
            f0_method: Pitch extraction method

        Returns:
            True if warmup successful, False otherwise
        """
        if not self._available:
            logger.debug("RVC not available, skipping warmup")
            return False

        if not Path(model_path).exists():
            logger.warning(f"RVC model not found for warmup: {model_path}")
            return False

        try:
            logger.info(f"Warming up RVC model: {model_path}")
            start_time = time.time()

            # Create a short dummy audio clip. Pure silence makes f0 extractors
            # (harvest/rmvpe/pm) short-circuit at the energy-detection step on
            # some rvc-python versions, which means the GPU kernels and nvmap
            # allocator never actually exercise — defeating the warmup's whole
            # point. Use a low-amplitude tone instead so f0 returns real pitch.
            sample_rate = 16000
            duration = 0.5
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False, dtype=np.float32)
            dummy_audio = (0.05 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

            # Run a quick conversion to warm up the model. max_attempts=1
            # because the caller (e.g. _on_scheduled_event) already has its
            # own real convert_audio call right after this with the full
            # retry budget; doubling the retries here just wastes time on a
            # cold-start failure that the real call will hit anyway.
            result = self.convert_audio(
                audio=dummy_audio,
                sample_rate=sample_rate,
                model_path=model_path,
                index_path=index_path,
                pitch_shift=pitch_shift,
                f0_method=f0_method,
                index_rate=0.0,  # Disable index for faster warmup
                max_attempts=1,
            )

            if result is not None:
                elapsed = time.time() - start_time
                logger.info(f"RVC warmup completed in {elapsed:.2f}s - model ready")
                return True
            else:
                logger.warning("RVC warmup failed - model may not be properly loaded")
                return False

        except Exception as e:
            logger.error(f"Error during RVC warmup: {e}", exc_info=True)
            return False
