"""
Squawkers McCaw output device implementation.
Simple stereo audio output without PPM control signals.
"""

import logging
from typing import Optional, Tuple
import numpy as np

from jf_sebastian.devices.base import OutputDevice
from jf_sebastian.devices.factory import register_device
from jf_sebastian.devices.shared.audio_processor import AudioProcessor
from jf_sebastian.devices.shared.sentiment_analyzer import SentimentAnalyzer
from jf_sebastian.config import settings

logger = logging.getLogger(__name__)


@register_device('squawkers_mccaw')
class SquawkersMcCawDevice(OutputDevice):
    """
    Squawkers McCaw output device.

    Creates stereo output with same audio on both channels:
    - LEFT channel: Voice audio
    - RIGHT channel: Voice audio (duplicate)

    No PPM control signals - just plays audio.
    Sentiment analysis is still performed for consistency/logging.
    """

    def __init__(self):
        """Initialize Squawkers McCaw device."""
        self.audio_processor = AudioProcessor()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.output_sample_rate = 44100  # Standard audio quality
        logger.info(f"Squawkers McCaw device initialized ({self.output_sample_rate}Hz)")

    @property
    def device_name(self) -> str:
        return "Squawkers McCaw"

    @property
    def requires_ppm(self) -> bool:
        return False

    def get_output_channels(self) -> int:
        return 2  # Stereo (duplicate channels)

    def create_output(
        self,
        voice_audio_mp3: bytes,
        response_text: str
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Create stereo output with voice on both channels.

        Args:
            voice_audio_mp3: Voice audio from TTS (MP3 format)
            response_text: Original text for sentiment analysis (logging only)

        Returns:
            Tuple of (stereo_audio, sample_rate) where stereo_audio shape is (N, 2)
        """
        try:
            # Convert MP3 to PCM
            voice_audio = self.audio_processor.mp3_to_pcm(
                voice_audio_mp3,
                target_sample_rate=self.output_sample_rate
            )

            if voice_audio is None:
                logger.error("Failed to convert MP3 to PCM")
                return None

            # Analyze sentiment (for logging/future use)
            sentiment = self.sentiment_analyzer.analyze(response_text)
            logger.info(f"Sentiment: compound={sentiment:+.2f} (not used by Squawkers)")

            # Apply voice gain
            voice_audio = voice_audio * settings.VOICE_GAIN

            # Create stereo: duplicate voice on both channels
            stereo_audio = np.column_stack((voice_audio, voice_audio))

            logger.info(
                f"Squawkers McCaw output created: {stereo_audio.shape[0]} samples @ {self.output_sample_rate}Hz, "
                f"sentiment={sentiment:.2f}"
            )

            return stereo_audio, self.output_sample_rate

        except Exception as e:
            logger.error(f"Error creating Squawkers McCaw output: {e}", exc_info=True)
            return None

    def validate_settings(self) -> list[str]:
        """Validate Squawkers-specific settings."""
        errors = []

        if not (0.0 <= settings.VOICE_GAIN <= 2.0):
            errors.append(f"VOICE_GAIN must be 0.0-2.0, got {settings.VOICE_GAIN}")

        # Note: CONTROL_GAIN is ignored for Squawkers

        return errors
