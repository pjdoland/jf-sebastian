"""
Headless output device implementation.
Simple stereo audio output without PPM control signals.
Designed for running on a computer without physical animatronic hardware.
"""

import logging
from typing import Optional, Tuple, TYPE_CHECKING
import numpy as np
from scipy import signal as scipy_signal

from jf_sebastian.devices.base import OutputDevice
from jf_sebastian.devices.factory import register_device
from jf_sebastian.devices.shared.audio_processor import AudioProcessor
from jf_sebastian.config import settings

if TYPE_CHECKING:
    from personalities.base import Personality

logger = logging.getLogger(__name__)


@register_device('headless')
class HeadlessDevice(OutputDevice):
    """
    Headless output device.

    Creates stereo output with same audio on both channels:
    - LEFT channel: Voice audio
    - RIGHT channel: Voice audio (duplicate)

    No PPM control signals - just plays audio.
    """

    def __init__(self):
        """Initialize Headless device."""
        self.audio_processor = AudioProcessor()
        self.rvc_input_sample_rate = 16000  # 16kHz for fast RVC processing
        self.output_sample_rate = 48000  # 48kHz to match RVC output and device
        logger.info(f"{self.device_name} device initialized (RVC input: {self.rvc_input_sample_rate}Hz, output: {self.output_sample_rate}Hz)")

    @property
    def device_name(self) -> str:
        return "Headless"

    @property
    def requires_ppm(self) -> bool:
        return False

    def get_output_channels(self) -> int:
        return 2  # Stereo (duplicate channels)

    def create_output(
        self,
        voice_audio_mp3: bytes,
        response_text: str,
        personality: Optional['Personality'] = None
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Create stereo output with voice on both channels.

        Args:
            voice_audio_mp3: Voice audio from TTS (MP3 format)
            response_text: Original text (unused by this device)
            personality: Optional personality configuration (for RVC, etc.)

        Returns:
            Tuple of (stereo_audio, sample_rate) where stereo_audio shape is (N, 2)
        """
        try:
            # Convert MP3 to PCM at 16kHz for fast RVC processing
            voice_audio = self.audio_processor.mp3_to_pcm(
                voice_audio_mp3,
                target_sample_rate=self.rvc_input_sample_rate
            )

            if voice_audio is None:
                logger.error("Failed to convert MP3 to PCM")
                return None

            # Apply RVC voice conversion if enabled for this personality
            current_sample_rate = self.rvc_input_sample_rate
            rvc_applied = False
            if personality and personality.rvc_enabled and settings.RVC_ENABLED:
                voice_audio, current_sample_rate = self.audio_processor.apply_rvc_conversion(
                    voice_audio, self.rvc_input_sample_rate, personality
                )
                rvc_applied = (current_sample_rate != self.rvc_input_sample_rate)

            # Resample to output sample rate if needed
            if current_sample_rate != self.output_sample_rate:
                voice_duration = len(voice_audio) / current_sample_rate
                voice_samples_needed = int(voice_duration * self.output_sample_rate)
                voice_audio = scipy_signal.resample(voice_audio, voice_samples_needed)
                logger.debug(f"Resampled audio from {current_sample_rate}Hz to {self.output_sample_rate}Hz")

            # Apply VOICE_GAIN to both RVC-converted and raw TTS paths. Some RVC
            # models output noticeably quieter than OpenAI TTS, and a single user-
            # facing volume knob is more useful than asking people to characterize
            # which path produced the audio. Clip to the float32 range so any
            # boost past unity doesn't wrap when converted to int16 downstream.
            voice_audio = np.clip(voice_audio * settings.VOICE_GAIN, -1.0, 1.0)

            # Create stereo: duplicate voice on both channels
            stereo_audio = np.column_stack((voice_audio, voice_audio))

            logger.info(
                f"{self.device_name} output created: {stereo_audio.shape[0]} samples @ {self.output_sample_rate}Hz"
            )

            return stereo_audio, self.output_sample_rate

        except Exception as e:
            logger.error(f"Error creating {self.device_name} output: {e}", exc_info=True)
            return None

    def validate_settings(self) -> list[str]:
        """Validate device-specific settings."""
        errors = []

        if not (0.0 <= settings.VOICE_GAIN <= 2.0):
            errors.append(f"VOICE_GAIN must be 0.0-2.0, got {settings.VOICE_GAIN}")

        return errors
