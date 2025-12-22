"""
RVC (Retrieval-based Voice Conversion) processor module.
Uses rvc-python library for direct in-process voice conversion.
"""

import logging
import time
import tempfile
from typing import Optional
from pathlib import Path
import numpy as np
import soundfile as sf

from jf_sebastian.utils.async_file_utils import save_async

logger = logging.getLogger(__name__)

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
        self._device = device
        self._rvc_instance = None
        self._loaded_model_path = None

        if not self._available:
            logger.error("rvc-python library not available")
        else:
            logger.info(f"RVC processor initialized (direct library, device={device})")

    @property
    def available(self) -> bool:
        """Check if RVC library is available."""
        return self._available

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
        protect: float = 0.33
    ) -> Optional[np.ndarray]:
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
            Converted audio array or None on failure
        """
        if not self._available:
            logger.warning("RVC library not available, skipping conversion")
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

            try:
                logger.debug(f"Converting audio through RVC (f0={f0_method}, pitch={pitch_shift}, device={self._device}, sr={sample_rate}Hz)")
                start_time = time.time()

                # Debug: Save input audio before RVC (async - non-blocking)
                debug_path = Path('debug_audio')
                debug_path.mkdir(exist_ok=True)
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                input_debug = debug_path / f'rvc_input_{timestamp}.wav'
                save_async(sf.write, str(input_debug), audio, sample_rate, subtype='PCM_16')
                logger.info(f"Saving RVC input to {input_debug} (async)")

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

                # Perform conversion using underlying VC module directly
                logger.debug("Performing RVC conversion...")
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

                # Parse result - can be either direct numpy array, tuple, or None on failure
                if result is None:
                    logger.error("RVC conversion returned None (internal error)")
                    return None
                elif isinstance(result, np.ndarray):
                    # Direct numpy array result
                    converted_audio = result
                    converted_sr = rvc.vc.tgt_sr
                    logger.debug(f"RVC conversion successful (output={converted_sr}Hz, {len(result)} samples)")
                elif isinstance(result, tuple) and len(result) == 2:
                    # Tuple result (message, (sr, audio_data))
                    message, audio_result = result
                    if audio_result is not None:
                        converted_sr, converted_audio = audio_result
                        logger.debug(f"Conversion result: {message}")
                    else:
                        logger.error(f"RVC conversion failed: {message}")
                        return None
                else:
                    logger.error(f"Unexpected RVC result format: {type(result)}")
                    return None

                # Debug: Save RVC raw output (async - non-blocking)
                output_debug = debug_path / f'rvc_output_{timestamp}.wav'
                save_async(sf.write, str(output_debug), converted_audio.copy(), converted_sr, subtype='PCM_16')
                logger.info(f"Saving RVC output to {output_debug} ({converted_sr}Hz, async)")

                # RVC library returns audio in int16 value range (-32768 to 32767) as float32 dtype
                # Normalize to proper float32 range (-1.0 to 1.0)
                converted_audio = converted_audio.astype(np.float32) / 32768.0

                # No resampling needed - RVC outputs at 48kHz which matches our pipeline!
                logger.info(f"RVC output normalized and ready at {converted_sr}Hz")

                elapsed = time.time() - start_time
                logger.info(f"RVC conversion completed in {elapsed:.2f}s")

                return converted_audio

            except Exception as e:
                logger.error(f"RVC conversion failed: {e}", exc_info=True)
                return None

            finally:
                # Clean up temporary file
                try:
                    Path(input_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file: {e}")
