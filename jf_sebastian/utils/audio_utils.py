"""
Audio utility functions.
"""

import logging
import numpy as np
import soundfile as sf

from jf_sebastian.utils import vad as _vad

logger = logging.getLogger(__name__)


def calculate_rms(audio_data: bytes, window_ms: int = 100, sample_rate: int = 16000) -> float:
    """
    Calculate peak RMS amplitude of audio data using sliding window.

    Instead of averaging across the entire audio (which gets dragged down by silence),
    this calculates RMS over small windows and returns the MAXIMUM value found.
    This effectively detects if there's ANY actual speech in the buffer.

    Args:
        audio_data: Raw audio bytes (16-bit PCM format)
        window_ms: Window size in milliseconds for RMS calculation (default: 100ms)
        sample_rate: Audio sample rate in Hz (default: 16000)

    Returns:
        Peak RMS value (float). Typical ranges:
        - Normal speech: ~1500-5000
        - Quiet speech: ~500-1500
        - Background noise: ~100-500
        - Near silence: <100

    Example:
        >>> from jf_sebastian.config import settings
        >>> audio_bytes = b'...'  # Raw PCM audio
        >>> peak_rms = calculate_rms(audio_bytes)
        >>> if peak_rms < settings.MIN_AUDIO_RMS:
        ...     print("No speech detected in any window")
    """
    # Convert bytes to float64 array (avoids int16 overflow when squaring)
    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float64)

    # Calculate window size in samples
    window_samples = int(sample_rate * window_ms / 1000)

    # If audio is shorter than one window, just calculate RMS of the whole thing
    if len(audio_array) < window_samples:
        return float(np.sqrt(np.mean(audio_array**2)))

    # Calculate RMS for each window and return the maximum
    max_rms = 0.0
    for i in range(0, len(audio_array) - window_samples + 1, window_samples // 2):  # 50% overlap
        window = audio_array[i:i + window_samples]
        window_rms = np.sqrt(np.mean(window**2))
        max_rms = max(max_rms, window_rms)

    return float(max_rms)


def contains_speech(audio_data: bytes, sample_rate: int = 16000,
                    min_speech_ratio: float = 0.3,
                    threshold: float = _vad.SILERO_DEFAULT_THRESHOLD) -> bool:
    """
    Return True if at least `min_speech_ratio` of `audio_data` is human
    speech per Silero VAD's neural-net classification.

    Use to filter out silence and sustained background noise before sending
    audio to Whisper.

    Args:
        audio_data: Raw audio bytes (16-bit PCM format)
        sample_rate: Audio sample rate in Hz (default: 16000)
        min_speech_ratio: Minimum ratio of speech to total audio (default 0.3)
        threshold: Per-window speech probability cutoff, 0.0-1.0 (default 0.5)
    """
    try:
        return _vad.contains_speech(
            audio_data, sample_rate=sample_rate,
            min_speech_ratio=min_speech_ratio, threshold=threshold,
        )
    except Exception as e:
        logger.error(f"Error analyzing speech content: {e}", exc_info=True)
        # On error, assume it contains speech to avoid false negatives
        return True


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
