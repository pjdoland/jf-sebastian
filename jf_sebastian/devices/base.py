"""
Abstract base class for output devices.
Defines the interface all animatronic output devices must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from personalities.base import Personality


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
        response_text: str,
        personality: Optional['Personality'] = None
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Create device-specific audio output from TTS.

        Args:
            voice_audio_mp3: Voice audio from TTS (MP3 format)
            response_text: Original text for sentiment/syllable analysis
            personality: Optional personality configuration (for RVC, etc.)

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

    # -------------------------------------------------------------------------
    # Optional visual hooks
    #
    # Most devices are pure audio transforms. A device that also drives an
    # on-screen talking head (e.g. the optional visual_device device) sets
    # requires_visual=True and overrides the hooks below. The application
    # (main.py) calls them only when requires_visual is True, so the default
    # no-op implementations keep every other device unaffected and keep all
    # rendering code out of the core. Method contract:
    #
    #   visual_start()              once, on the MAIN thread, before the app loop
    #   visual_step()               once per main-loop iteration (pumps one frame)
    #   visual_on_playback_start()  when a chunk begins playing (playback thread)
    #   visual_on_playback_end()    when a response finishes playing
    #   visual_set_mode(mode)       on state transitions: "idle"/"listening"/
    #                               "processing"/"speaking"
    #   visual_stop()               once, on the MAIN thread, during teardown
    # -------------------------------------------------------------------------

    @property
    def requires_visual(self) -> bool:
        """Whether this device drives an on-screen renderer (a GUI window)."""
        return False

    def visual_start(self) -> None:
        """Create the renderer/window. Called on the main thread before the loop."""
        return None

    def visual_step(self) -> None:
        """Render one frame. Called each main-loop iteration on the main thread."""
        return None

    def visual_on_playback_start(
        self,
        stereo_audio: np.ndarray,
        sample_rate: int,
        chunk_type: str = "chunk",
    ) -> None:
        """Notify that a chunk is about to play (drives lip-sync timing/envelope)."""
        return None

    def visual_on_playback_end(self) -> None:
        """Notify that the current response finished playing."""
        return None

    def visual_set_mode(self, mode: str) -> None:
        """Reflect a conversation-state change in the visuals."""
        return None

    def visual_stop(self) -> None:
        """Tear down the renderer/window. Called on the main thread during shutdown."""
        return None
