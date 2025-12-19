"""
Tests for device factory and registry.
"""

import pytest
from jf_sebastian.devices.base import OutputDevice
from jf_sebastian.devices.factory import DeviceRegistry, register_device
from jf_sebastian.devices import TeddyRuxpinDevice, SquawkersMcCawDevice


def test_device_registry_lists_devices():
    """Test that DeviceRegistry lists all registered devices."""
    devices = DeviceRegistry.list_devices()

    assert 'teddy_ruxpin' in devices
    assert 'squawkers_mccaw' in devices
    assert len(devices) >= 2


def test_device_registry_create_teddy_ruxpin():
    """Test creating Teddy Ruxpin device from registry."""
    device = DeviceRegistry.create('teddy_ruxpin')

    assert isinstance(device, TeddyRuxpinDevice)
    assert device.device_name == "Teddy Ruxpin"
    assert device.requires_ppm is True
    assert device.get_output_channels() == 2


def test_device_registry_create_squawkers_mccaw():
    """Test creating Squawkers McCaw device from registry."""
    device = DeviceRegistry.create('squawkers_mccaw')

    assert isinstance(device, SquawkersMcCawDevice)
    assert device.device_name == "Squawkers McCaw"
    assert device.requires_ppm is False
    assert device.get_output_channels() == 2


def test_device_registry_create_case_insensitive():
    """Test that device creation is case-insensitive."""
    device1 = DeviceRegistry.create('TEDDY_RUXPIN')
    device2 = DeviceRegistry.create('Teddy_Ruxpin')
    device3 = DeviceRegistry.create('teddy_ruxpin')

    assert all(isinstance(d, TeddyRuxpinDevice) for d in [device1, device2, device3])


def test_device_registry_create_invalid_device():
    """Test that creating invalid device raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        DeviceRegistry.create('invalid_device_name')

    assert "Unknown device type" in str(exc_info.value)
    assert "invalid_device_name" in str(exc_info.value)
    assert "Available devices" in str(exc_info.value)


def test_register_device_decorator():
    """Test that register_device decorator works correctly."""
    # Create a test device class
    @register_device('test_device')
    class TestDevice(OutputDevice):
        @property
        def device_name(self):
            return "Test Device"

        @property
        def requires_ppm(self):
            return False

        def get_output_channels(self):
            return 1

        def create_output(self, voice_audio_mp3, response_text):
            return None

    # Verify it's registered
    devices = DeviceRegistry.list_devices()
    assert 'test_device' in devices

    # Verify we can create it
    device = DeviceRegistry.create('test_device')
    assert isinstance(device, TestDevice)
    assert device.device_name == "Test Device"

    # Clean up
    DeviceRegistry._devices.pop('test_device', None)


def test_all_registered_devices_implement_interface():
    """Test that all registered devices properly implement OutputDevice interface."""
    devices = DeviceRegistry.list_devices()

    for device_type in devices:
        device = DeviceRegistry.create(device_type)

        # Check all required properties exist
        assert hasattr(device, 'device_name')
        assert hasattr(device, 'requires_ppm')
        assert hasattr(device, 'get_output_channels')
        assert hasattr(device, 'create_output')
        assert hasattr(device, 'validate_settings')

        # Check properties return correct types
        assert isinstance(device.device_name, str)
        assert isinstance(device.requires_ppm, bool)
        assert isinstance(device.get_output_channels(), int)
        assert callable(device.create_output)
        assert callable(device.validate_settings)

        # Check validation returns list
        errors = device.validate_settings()
        assert isinstance(errors, list)
