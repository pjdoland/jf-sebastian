"""
Audio utility functions.
"""

import logging
import numpy as np
from scipy.io import wavfile

logger = logging.getLogger(__name__)


def save_stereo_wav(stereo_audio: np.ndarray, sample_rate: int, filename: str):
    """
    Save stereo audio to WAV file.

    Args:
        stereo_audio: Stereo audio array (num_samples, 2)
        sample_rate: Sample rate in Hz
        filename: Output filename
    """
    try:
        # Convert to int16 for WAV
        audio_int16 = (stereo_audio * 32767).astype(np.int16)

        wavfile.write(filename, sample_rate, audio_int16)
        logger.info(f"Stereo audio saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving stereo audio: {e}", exc_info=True)
