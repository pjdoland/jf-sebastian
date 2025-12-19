"""
Output device package for J.F. Sebastian animatronic system.
Provides plugin-style device support via registry pattern.
"""

from jf_sebastian.devices.base import OutputDevice
from jf_sebastian.devices.factory import DeviceRegistry, register_device

# Import device implementations to trigger registration
from jf_sebastian.devices.teddy_ruxpin import TeddyRuxpinDevice
from jf_sebastian.devices.squawkers_mccaw import SquawkersMcCawDevice

__all__ = [
    'OutputDevice',
    'DeviceRegistry',
    'register_device',
    'TeddyRuxpinDevice',
    'SquawkersMcCawDevice',
]
