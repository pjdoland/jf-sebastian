"""
Audio utility functions.
"""

import logging
import numpy as np
import soundfile as sf
import webrtcvad

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
    # Convert bytes to numpy array of 16-bit integers
    audio_array = np.frombuffer(audio_data, dtype=np.int16)

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
                    vad_aggressiveness: int = 3, min_speech_ratio: float = 0.3) -> bool:
    """
    Analyze audio to determine if it contains actual speech using VAD.

    This function analyzes the entire audio buffer frame-by-frame using WebRTC VAD
    to determine what percentage of the audio contains speech. This helps filter out
    silence, background noise, or very brief utterances before sending to Whisper.

    Args:
        audio_data: Raw audio bytes (16-bit PCM format)
        sample_rate: Audio sample rate in Hz (default: 16000)
        vad_aggressiveness: VAD aggressiveness level 0-3 (default: 3, most strict)
        min_speech_ratio: Minimum ratio of speech frames required (default: 0.3 = 30%)

    Returns:
        True if audio contains sufficient speech content, False otherwise

    Example:
        >>> audio_bytes = b'...'  # Raw PCM audio
        >>> if not contains_speech(audio_bytes):
        ...     print("No meaningful speech detected, skipping Whisper")
    """
    if not audio_data or len(audio_data) == 0:
        return False

    try:
        # Initialize VAD
        vad = webrtcvad.Vad(vad_aggressiveness)

        # VAD requires specific frame durations (10, 20, or 30 ms)
        frame_duration_ms = 30
        frame_size = int(sample_rate * frame_duration_ms / 1000)
        frame_bytes = frame_size * 2  # 2 bytes per sample (16-bit)

        # Convert to numpy array for processing
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Count frames with speech
        speech_frames = 0
        total_frames = 0

        # Analyze each frame
        for i in range(0, len(audio_array) - frame_size + 1, frame_size):
            frame = audio_array[i:i + frame_size].tobytes()

            # Ensure frame is correct size
            if len(frame) != frame_bytes:
                continue

            total_frames += 1

            # Check if frame contains speech
            try:
                if vad.is_speech(frame, sample_rate):
                    speech_frames += 1
            except Exception as e:
                logger.debug(f"VAD frame analysis error: {e}")
                continue

        if total_frames == 0:
            return False

        # Calculate speech ratio
        speech_ratio = speech_frames / total_frames

        logger.info(f"🎤 Speech analysis: {speech_frames}/{total_frames} frames "
                   f"({speech_ratio:.1%}) - threshold: {min_speech_ratio:.0%}")

        return speech_ratio >= min_speech_ratio

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
