"""
Shared audio processing utilities for all output devices.
Extracted from AnimatronicControlGenerator for reusability.
"""

import logging
import tempfile
import subprocess
import os
from typing import Optional
import numpy as np
from jf_sebastian.config import settings

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Shared audio processing utilities."""

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
