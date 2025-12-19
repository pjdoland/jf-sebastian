"""
Abstract base class for output devices.
Defines the interface all animatronic output devices must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple
import numpy as np


class OutputDevice(ABC):
    """
    Abstract base class for output devices.

    Each device implementation must define how to process TTS audio
    and create the final output format for that specific device.
    """

    @property
    @abstractmethod
    def device_name(self) -> str:
        """Human-readable name of the device (e.g., 'Teddy Ruxpin')."""
        pass

    @property
    @abstractmethod
    def requires_ppm(self) -> bool:
        """Whether this device requires PPM control signals."""
        pass

    @abstractmethod
    def create_output(
        self,
        voice_audio_mp3: bytes,
        response_text: str
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Create device-specific audio output from TTS.

        Args:
            voice_audio_mp3: Voice audio from TTS (MP3 format)
            response_text: Original text for sentiment/syllable analysis

        Returns:
            Tuple of (audio_array, sample_rate), or None on error
            - audio_array: Can be mono (N,) or stereo (N, 2)
            - sample_rate: Sample rate in Hz
        """
        pass

    @abstractmethod
    def get_output_channels(self) -> int:
        """
        Get number of output channels.

        Returns:
            1 for mono, 2 for stereo
        """
        pass

    def validate_settings(self) -> list[str]:
        """
        Validate device-specific settings.

        Returns:
            List of error messages (empty if valid)
        """
        return []
