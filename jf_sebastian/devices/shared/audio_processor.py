"""
Shared audio processing utilities for all output devices.
Extracted from AnimatronicControlGenerator for reusability.
"""

import logging
import tempfile
import subprocess
import os
from typing import Optional, TYPE_CHECKING
import numpy as np
from jf_sebastian.config import settings

if TYPE_CHECKING:
    from personalities.base import Personality

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Shared audio processing utilities."""

    def __init__(self):
        """Initialize audio processor."""
        self._rvc_processor = None  # Lazy-loaded when needed

    @staticmethod
    def mp3_to_pcm(mp3_data: bytes, target_sample_rate: Optional[int] = None) -> Optional[np.ndarray]:
        """
        Convert MP3 audio to PCM array using FFmpeg.

        Args:
            mp3_data: MP3 audio bytes
            target_sample_rate: Target sample rate (uses settings.SAMPLE_RATE if None)

        Returns:
            Numpy array of audio samples (normalized to -1.0 to 1.0), or None on error
        """
        if target_sample_rate is None:
            target_sample_rate = settings.SAMPLE_RATE

        try:
            # Write MP3 to temporary file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file:
                mp3_file.write(mp3_data)
                mp3_path = mp3_file.name

            # Use FFmpeg to convert MP3 to raw PCM
            result = subprocess.run([
                'ffmpeg',
                '-i', mp3_path,
                '-f', 's16le',
                '-acodec', 'pcm_s16le',
                '-ac', '1',  # mono
                '-ar', str(target_sample_rate),
                '-'
            ], capture_output=True, check=True)

            # Clean up temp file
            os.unlink(mp3_path)

            # Convert to numpy array
            samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)

            # Normalize to -1.0 to 1.0
            samples = samples / 32768.0

            logger.debug(f"Converted MP3 to PCM: {len(samples)} samples at {target_sample_rate}Hz")
            return samples

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error converting MP3 to PCM: {e}", exc_info=True)
            return None

    def apply_rvc_conversion(
        self,
        audio: np.ndarray,
        sample_rate: int,
        personality: 'Personality'
    ) -> np.ndarray:
        """
        Apply RVC voice conversion to audio if enabled for the personality.

        Args:
            audio: Input audio array (float32, -1.0 to 1.0)
            sample_rate: Audio sample rate (Hz)
            personality: Personality configuration

        Returns:
            Converted audio array (or original if RVC disabled/failed)
        """
        # Check if RVC enabled for this personality
        if not personality.rvc_enabled:
            logger.debug("RVC not enabled for this personality")
            return audio

        # Check if global RVC is disabled
        if not settings.RVC_ENABLED:
            logger.debug("RVC globally disabled in settings")
            return audio

        # Lazy-load RVC processor
        if self._rvc_processor is None:
            try:
                from jf_sebastian.modules.rvc_processor import RVCProcessor
                # Get device from settings (don't import torch here - only in RVC service)
                # RVC server will validate device availability and fallback if needed
                device = settings.RVC_DEVICE
                self._rvc_processor = RVCProcessor(device=device)
                logger.info(f"RVC processor initialized (device={device})")
            except Exception as e:
                logger.error(f"Failed to initialize RVC processor: {e}", exc_info=True)
                return audio

        # Check if RVC is available
        if not self._rvc_processor.available:
            logger.warning("RVC processor not available, using original audio")
            return audio

        # Get model path
        model_path = personality.rvc_model_path
        if model_path is None:
            logger.error(f"RVC model not found: {personality.rvc_model}")
            return audio

        # Get index path (optional)
        index_path = personality.rvc_index_path
        if personality.rvc_index_file and index_path is None:
            logger.warning(f"RVC index file not found: {personality.rvc_index_file}")

        # Convert audio through RVC
        try:
            logger.info(f"Applying RVC conversion: {personality.rvc_model}")
            converted = self._rvc_processor.convert_audio(
                audio=audio,
                sample_rate=sample_rate,
                model_path=str(model_path),
                index_path=str(index_path) if index_path else None,
                pitch_shift=personality.rvc_pitch_shift,
                index_rate=personality.rvc_index_rate,
                f0_method=personality.rvc_f0_method,
                filter_radius=personality.rvc_filter_radius,
                rms_mix_rate=personality.rvc_rms_mix_rate,
                protect=personality.rvc_protect
            )

            # If conversion failed, return original
            if converted is None:
                logger.warning("RVC conversion failed, using original audio")
                return audio

            logger.info("RVC conversion successful")
            return converted

        except Exception as e:
            logger.error(f"Error during RVC conversion: {e}", exc_info=True)
            return audio

    def warmup_rvc(self, personality: 'Personality') -> bool:
        """
        Warm up RVC by loading model and running a quick inference.
        This eliminates the first-use delay when the personality uses RVC.

        Args:
            personality: Personality with RVC configuration

        Returns:
            True if warmup successful or not needed, False on error
        """
        # Check if RVC is enabled for this personality
        if not personality.rvc_enabled:
            logger.debug(f"RVC not enabled for personality '{personality.name}', skipping warmup")
            return True

        # Check if global RVC is disabled
        if not settings.RVC_ENABLED:
            logger.debug("RVC globally disabled in settings, skipping warmup")
            return True

        # Initialize RVC processor if needed
        if self._rvc_processor is None:
            try:
                from jf_sebastian.modules.rvc_processor import RVCProcessor
                device = settings.RVC_DEVICE
                self._rvc_processor = RVCProcessor(device=device)
                logger.info(f"RVC processor initialized for warmup (device={device})")
            except Exception as e:
                logger.error(f"Failed to initialize RVC processor: {e}", exc_info=True)
                return False

        # Check if RVC is available
        if not self._rvc_processor.available:
            logger.warning("RVC processor not available, skipping warmup")
            return False

        # Get model path
        model_path = personality.rvc_model_path
        if model_path is None:
            logger.warning(f"RVC model not found for warmup: {personality.rvc_model}")
            return False

        # Get index path (optional)
        index_path = personality.rvc_index_path

        # Warm up the RVC processor
        return self._rvc_processor.warmup(
            model_path=str(model_path),
            index_path=str(index_path) if index_path else None,
            pitch_shift=personality.rvc_pitch_shift,
            f0_method=personality.rvc_f0_method
        )
