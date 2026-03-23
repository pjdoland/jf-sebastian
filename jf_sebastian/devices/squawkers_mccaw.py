"""
Squawkers McCaw output device implementation.
Simple stereo audio output without PPM control signals.
Identical to HeadlessDevice except for the device name.
"""

import logging

from jf_sebastian.devices.factory import register_device
from jf_sebastian.devices.headless import HeadlessDevice

logger = logging.getLogger(__name__)


@register_device('squawkers_mccaw')
class SquawkersMcCawDevice(HeadlessDevice):
    """
    Squawkers McCaw output device.

    Creates stereo output with same audio on both channels.
    Functionally identical to HeadlessDevice.
    """

    @property
    def device_name(self) -> str:
        return "Squawkers McCaw"
