"""Audio device utility functions."""

import logging
from typing import Optional
import pyaudio

logger = logging.getLogger(__name__)


def find_audio_device_by_name(
    pyaudio_instance: pyaudio.PyAudio,
    device_name: str,
    device_type: str = "input"
) -> Optional[int]:
    """
    Find audio device index by name.

    Args:
        pyaudio_instance: PyAudio instance
        device_name: Name of the device to find (case-insensitive, partial match)
        device_type: Either "input" or "output"

    Returns:
        Device index if found, None otherwise
    """
    device_count = pyaudio_instance.get_device_count()

    for i in range(device_count):
        try:
            device_info = pyaudio_instance.get_device_info_by_index(i)
            name = device_info.get('name', '')

            # Check if device name matches (case-insensitive, partial match)
            if device_name.lower() in name.lower():
                # Check if it's the right type
                if device_type == "input":
                    if device_info.get('maxInputChannels', 0) > 0:
                        logger.info(f"Found input device '{name}' at index {i}")
                        return i
                elif device_type == "output":
                    if device_info.get('maxOutputChannels', 0) > 0:
                        logger.info(f"Found output device '{name}' at index {i}")
                        return i
        except Exception as e:
            logger.warning(f"Error checking device {i}: {e}")
            continue

    logger.warning(f"Could not find {device_type} device matching '{device_name}'")
    return None
