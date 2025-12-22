"""
Audio utility functions.
"""

import logging
import numpy as np
import soundfile as sf

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
        # Save as float32 - no conversion needed, preserves full quality
        sf.write(filename, stereo_audio, sample_rate, subtype='FLOAT')
        logger.info(f"Stereo audio saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving stereo audio: {e}", exc_info=True)
