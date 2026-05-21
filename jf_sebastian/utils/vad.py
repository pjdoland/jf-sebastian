"""Silero VAD wrapper. Single shared model instance.

Silero is a small neural VAD trained to distinguish human speech from
noise. Substantially harder to fool than WebRTC VAD on sustained ambient
hum or speaker electronic noise — the model that previously let through
~974 RMS speaker hum as "98.8 % speech" classifies the same audio as not
speech.

The model operates on 512-sample windows (32 ms at 16 kHz) and carries an
RNN hidden state across calls — call reset_state() at the start of each
new recording session so prior context doesn't bleed in.
"""

import logging
from threading import Lock
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

SILERO_WINDOW_SAMPLES = 512  # required at 16 kHz; 256 at 8 kHz
SILERO_DEFAULT_THRESHOLD = 0.5

_model = None
_model_lock = Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from silero_vad import load_silero_vad
                logger.info("Loading Silero VAD model...")
                _model = load_silero_vad()
                logger.info("Silero VAD loaded")
    return _model


def reset_state() -> None:
    """Drop the model's RNN hidden state."""
    try:
        model = _get_model()
        if hasattr(model, "reset_states"):
            model.reset_states()
    except Exception as e:
        logger.warning(f"Silero VAD reset_state failed: {e}")


def is_speech_window(
    window_int16: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = SILERO_DEFAULT_THRESHOLD,
) -> bool:
    """Classify a single 512-sample int16 window as speech or not.

    Maintains the model's RNN state across calls. Call reset_state() to
    start a new session.
    """
    if len(window_int16) != SILERO_WINDOW_SAMPLES:
        return False  # Silero requires exact window size at 16 kHz

    import torch
    model = _get_model()
    window_float = window_int16.astype(np.float32) / 32768.0
    tensor = torch.from_numpy(window_float)
    with torch.no_grad():
        speech_prob = model(tensor, sample_rate).item()
    return speech_prob >= threshold


def contains_speech(
    audio_data: bytes,
    sample_rate: int = 16000,
    min_speech_ratio: float = 0.3,
    threshold: float = SILERO_DEFAULT_THRESHOLD,
) -> bool:
    """Analyze a complete buffer for speech content.

    Returns True if the buffer contains at least min_speech_ratio of
    speech (by duration) per Silero's segmentation.
    """
    if not audio_data:
        return False

    import torch
    from silero_vad import get_speech_timestamps

    model = _get_model()
    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
    audio_tensor = torch.from_numpy(audio_array)

    total_samples = len(audio_tensor)
    if total_samples == 0:
        return False

    try:
        timestamps = get_speech_timestamps(
            audio_tensor,
            model,
            threshold=threshold,
            sampling_rate=sample_rate,
            return_seconds=False,
        )
    except Exception as e:
        logger.warning(f"Silero get_speech_timestamps failed: {e}")
        return False

    speech_samples = sum(t["end"] - t["start"] for t in timestamps)
    speech_ratio = speech_samples / total_samples

    logger.info(
        f"🎤 Speech analysis (Silero): {len(timestamps)} segments, "
        f"{speech_ratio:.1%} speech (threshold: {min_speech_ratio:.0%})"
    )

    return speech_ratio >= min_speech_ratio
