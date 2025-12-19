"""
Teddy Ruxpin output device implementation.
Generates PPM control signals with syllable-based lip sync.
"""

import logging
from typing import Optional, Tuple
import numpy as np
from scipy import signal as scipy_signal

from jf_sebastian.devices.base import OutputDevice
from jf_sebastian.devices.factory import register_device
from jf_sebastian.devices.shared.audio_processor import AudioProcessor
from jf_sebastian.devices.shared.sentiment_analyzer import SentimentAnalyzer
from jf_sebastian.modules.ppm_generator import PPMGenerator
from jf_sebastian.config import settings

logger = logging.getLogger(__name__)


@register_device('teddy_ruxpin')
class TeddyRuxpinDevice(OutputDevice):
    """
    Teddy Ruxpin output device.

    Creates stereo output:
    - LEFT channel: Voice audio
    - RIGHT channel: PPM control signals for motors
    """

    def __init__(self):
        """Initialize Teddy Ruxpin device."""
        self.audio_processor = AudioProcessor()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.ppm_sample_rate = 44100  # PPM at 44.1kHz for precise timing
        self.ppm_generator = PPMGenerator(sample_rate=self.ppm_sample_rate)
        logger.info(f"Teddy Ruxpin device initialized (PPM @ {self.ppm_sample_rate}Hz)")

    @property
    def device_name(self) -> str:
        return "Teddy Ruxpin"

    @property
    def requires_ppm(self) -> bool:
        return True

    def get_output_channels(self) -> int:
        return 2  # Stereo

    def create_output(
        self,
        voice_audio_mp3: bytes,
        response_text: str
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Create stereo output with voice and PPM control signals.

        Args:
            voice_audio_mp3: Voice audio from TTS (MP3 format)
            response_text: Original text for sentiment/syllable analysis

        Returns:
            Tuple of (stereo_audio, sample_rate) where stereo_audio shape is (N, 2)
        """
        try:
            # Convert MP3 to PCM
            voice_audio = self.audio_processor.mp3_to_pcm(voice_audio_mp3)
            if voice_audio is None:
                logger.error("Failed to convert MP3 to PCM")
                return None

            # Analyze sentiment for eye control
            sentiment = self.sentiment_analyzer.analyze(response_text)
            logger.info(f"Eye sentiment driver: compound={sentiment:+.2f}")

            # Calculate duration and resample voice to match PPM sample rate
            voice_duration = len(voice_audio) / settings.SAMPLE_RATE
            voice_samples_needed = int(voice_duration * self.ppm_sample_rate)
            voice_resampled = scipy_signal.resample(voice_audio, voice_samples_needed)

            # Generate PPM channel values using syllable-based lip sync
            channel_values = self.ppm_generator.audio_to_channel_values(
                voice_audio,
                settings.SAMPLE_RATE,
                text=response_text,
                eyes_base=0.9,
                sentiment=sentiment
            )

            # Generate PPM control signal at 44.1kHz
            ppm_signal = self.ppm_generator.generate_ppm_signal(voice_duration, channel_values)

            # Ensure same length
            min_length = min(len(voice_resampled), len(ppm_signal))
            voice_resampled = voice_resampled[:min_length]
            ppm_signal = ppm_signal[:min_length]

            # Apply channel-specific gains
            voice_resampled = voice_resampled * settings.VOICE_GAIN
            ppm_signal = ppm_signal * settings.CONTROL_GAIN

            # Create stereo: LEFT=voice, RIGHT=PPM control
            stereo_audio = np.column_stack((voice_resampled, ppm_signal))

            logger.info(
                f"Teddy Ruxpin output created: {stereo_audio.shape[0]} samples @ {self.ppm_sample_rate}Hz, "
                f"sentiment={sentiment:.2f}, {len(channel_values)} PPM frames"
            )

            return stereo_audio, self.ppm_sample_rate

        except Exception as e:
            logger.error(f"Error creating Teddy Ruxpin output: {e}", exc_info=True)
            return None

    def validate_settings(self) -> list[str]:
        """Validate Teddy-specific settings."""
        errors = []

        if not (0.0 <= settings.VOICE_GAIN <= 2.0):
            errors.append(f"VOICE_GAIN must be 0.0-2.0, got {settings.VOICE_GAIN}")

        if not (0.0 <= settings.CONTROL_GAIN <= 1.0):
            errors.append(f"CONTROL_GAIN must be 0.0-1.0, got {settings.CONTROL_GAIN}")

        return errors
