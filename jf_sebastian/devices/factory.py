"""
Device factory for creating output device instances.
Uses registry pattern to support plugin-style device additions.
"""

import logging
from typing import Dict, Type
from jf_sebastian.devices.base import OutputDevice

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """Registry for output device types."""

    _devices: Dict[str, Type[OutputDevice]] = {}

    @classmethod
    def register(cls, device_type: str, device_class: Type[OutputDevice]):
        """
        Register a device type.

        Args:
            device_type: Device type identifier (e.g., 'teddy_ruxpin')
            device_class: Device class implementing OutputDevice
        """
        cls._devices[device_type.lower()] = device_class
        logger.debug(f"Registered device type: {device_type}")

    @classmethod
    def create(cls, device_type: str) -> OutputDevice:
        """
        Create a device instance by type.

        Args:
            device_type: Device type identifier

        Returns:
            Device instance

        Raises:
            ValueError: If device type is not registered
        """
        device_type_lower = device_type.lower()

        if device_type_lower not in cls._devices:
            available = ', '.join(cls._devices.keys())
            raise ValueError(
                f"Unknown device type: '{device_type}'. "
                f"Available devices: {available}"
            )

        device_class = cls._devices[device_type_lower]
        logger.info(f"Creating device: {device_type}")
        return device_class()

    @classmethod
    def list_devices(cls) -> list[str]:
        """Get list of registered device types."""
        return list(cls._devices.keys())


def register_device(device_type: str):
    """
    Decorator for registering device classes.

    Usage:
        @register_device('teddy_ruxpin')
        class TeddyRuxpinDevice(OutputDevice):
            ...
    """
    def decorator(device_class: Type[OutputDevice]):
        DeviceRegistry.register(device_type, device_class)
        return device_class
    return decorator
