"""
Audio utility functions.
"""

import logging
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


def calculate_rms(audio_data: bytes) -> float:
    """
    Calculate RMS (Root Mean Square) amplitude of audio data.

    RMS provides a mathematical measure of signal amplitude/loudness.
    Higher RMS = louder audio. Useful for filtering silence/quiet audio.

    Args:
        audio_data: Raw audio bytes (16-bit PCM format)

    Returns:
        RMS value (float). Typical ranges:
        - Normal speech: ~1500-5000
        - Quiet speech: ~800-1500
        - Background noise: ~100-500
        - Near silence: <100

    Example:
        >>> audio_bytes = b'...'  # Raw PCM audio
        >>> rms = calculate_rms(audio_bytes)
        >>> if rms < 800:
        ...     print("Audio too quiet, likely silence")
    """
    # Convert bytes to numpy array of 16-bit integers
    audio_array = np.frombuffer(audio_data, dtype=np.int16)

    # Calculate RMS: square root of mean of squares
    rms = np.sqrt(np.mean(audio_array**2))

    return float(rms)


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
