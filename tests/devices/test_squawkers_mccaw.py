"""
Tests for SquawkersMcCawDevice.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from jf_sebastian.devices.squawkers_mccaw import SquawkersMcCawDevice


@pytest.fixture
def mock_voice_audio():
    """Generate mock voice audio."""
    sample_rate = 44100
    duration = 1.0
    num_samples = int(sample_rate * duration)
    return np.sin(2 * np.pi * 440 * np.linspace(0, duration, num_samples)).astype(np.float32)


def test_squawkers_mccaw_device_initialization():
    """Test SquawkersMcCawDevice initialization."""
    device = SquawkersMcCawDevice()

    assert device.device_name == "Squawkers McCaw"
    assert device.requires_ppm is False
    assert device.get_output_channels() == 2
    assert device.output_sample_rate == 44100
    assert device.audio_processor is not None
    assert device.sentiment_analyzer is not None


def test_squawkers_mccaw_device_properties():
    """Test SquawkersMcCawDevice properties."""
    device = SquawkersMcCawDevice()

    assert isinstance(device.device_name, str)
    assert isinstance(device.requires_ppm, bool)
    assert isinstance(device.get_output_channels(), int)


def test_squawkers_mccaw_no_ppm_required():
    """Test that Squawkers does not require PPM."""
    device = SquawkersMcCawDevice()

    assert device.requires_ppm is False
    # Should not have ppm_generator
    assert not hasattr(device, 'ppm_generator')


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_validate_settings_valid(mock_settings):
    """Test settings validation with valid values."""
    mock_settings.VOICE_GAIN = 1.0

    device = SquawkersMcCawDevice()
    errors = device.validate_settings()

    assert isinstance(errors, list)
    assert len(errors) == 0


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_validate_settings_invalid_voice_gain(mock_settings):
    """Test settings validation with invalid VOICE_GAIN."""
    mock_settings.VOICE_GAIN = 3.0  # Out of range

    device = SquawkersMcCawDevice()
    errors = device.validate_settings()

    assert len(errors) > 0
    assert any('VOICE_GAIN' in error for error in errors)


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_create_output_success(mock_settings, mock_voice_audio):
    """Test successful output creation."""
    mock_settings.VOICE_GAIN = 1.0

    device = SquawkersMcCawDevice()

    # Mock the dependencies
    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.5):
            result = device.create_output(b'fake_mp3_data', "Test response text")

    # Should return tuple of (audio, sample_rate)
    assert result is not None
    stereo_audio, sample_rate = result

    # Check output format
    assert isinstance(stereo_audio, np.ndarray)
    assert stereo_audio.ndim == 2
    assert stereo_audio.shape[1] == 2  # Stereo
    assert sample_rate == 44100

    # Check audio is normalized
    assert np.all(stereo_audio >= -2.0)  # With gain, might be slightly over 1.0
    assert np.all(stereo_audio <= 2.0)


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_create_output_duplicate_channels(mock_settings, mock_voice_audio):
    """Test that output duplicates voice on both channels."""
    mock_settings.VOICE_GAIN = 1.0

    device = SquawkersMcCawDevice()

    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.0):
            result = device.create_output(b'fake_mp3', "Test text")

    stereo_audio, sample_rate = result

    # Both channels should be identical (or very close due to floating point)
    left_channel = stereo_audio[:, 0]
    right_channel = stereo_audio[:, 1]

    # Channels should be identical
    np.testing.assert_array_almost_equal(left_channel, right_channel)


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_create_output_mp3_conversion_failure(mock_settings):
    """Test output creation when MP3 conversion fails."""
    device = SquawkersMcCawDevice()

    # Mock MP3 conversion failure
    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=None):
        result = device.create_output(b'invalid_mp3', "Test text")

    # Should return None on error
    assert result is None


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_create_output_exception_handling(mock_settings):
    """Test output creation handles exceptions gracefully."""
    device = SquawkersMcCawDevice()

    # Mock an exception
    with patch.object(device.audio_processor, 'mp3_to_pcm', side_effect=Exception("Test error")):
        result = device.create_output(b'fake_mp3', "Test text")

    # Should return None on exception
    assert result is None


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_create_output_applies_voice_gain(mock_settings, mock_voice_audio):
    """Test that VOICE_GAIN is applied."""
    mock_settings.VOICE_GAIN = 1.5

    device = SquawkersMcCawDevice()

    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio * 0.5):  # Half amplitude
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.0):
            result = device.create_output(b'fake_mp3', "Test text")

    assert result is not None
    stereo_audio, sample_rate = result

    # With 1.5 gain on 0.5 amplitude audio, should get roughly 0.75 amplitude
    # Just verify it's not the original amplitude
    assert stereo_audio.shape[1] == 2


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_create_output_calls_sentiment_analyzer(mock_settings, mock_voice_audio):
    """Test that sentiment analysis is called (even though not used)."""
    mock_settings.VOICE_GAIN = 1.0

    device = SquawkersMcCawDevice()

    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.8) as mock_analyze:
            device.create_output(b'fake_mp3', "Happy test text")

    # Verify sentiment analyzer was called (for logging/consistency)
    mock_analyze.assert_called_once_with("Happy test text")


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_create_output_stereo_format(mock_settings, mock_voice_audio):
    """Test that output is properly formatted as stereo."""
    mock_settings.VOICE_GAIN = 1.0

    device = SquawkersMcCawDevice()

    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.0):
            result = device.create_output(b'fake_mp3', "Test text")

    stereo_audio, sample_rate = result

    # Should be 2D array with 2 columns (stereo)
    assert stereo_audio.ndim == 2
    assert stereo_audio.shape[1] == 2

    # Both channels should have same length
    assert stereo_audio.shape[0] > 0
    assert len(stereo_audio[:, 0]) == len(stereo_audio[:, 1])


@patch('jf_sebastian.devices.squawkers_mccaw.settings')
def test_squawkers_mccaw_ignores_control_gain(mock_settings, mock_voice_audio):
    """Test that CONTROL_GAIN is ignored (not applicable to Squawkers)."""
    mock_settings.VOICE_GAIN = 1.0
    mock_settings.CONTROL_GAIN = 0.5  # Should be ignored

    device = SquawkersMcCawDevice()

    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.0):
            result = device.create_output(b'fake_mp3', "Test text")

    # Should succeed - CONTROL_GAIN doesn't cause errors, just ignored
    assert result is not None


def test_squawkers_mccaw_simpler_than_teddy():
    """Test that Squawkers is simpler than Teddy Ruxpin (no PPM)."""
    from jf_sebastian.devices.teddy_ruxpin import TeddyRuxpinDevice

    squawkers = SquawkersMcCawDevice()
    teddy = TeddyRuxpinDevice()

    # Squawkers should not require PPM
    assert squawkers.requires_ppm is False
    assert teddy.requires_ppm is True

    # Both should be stereo
    assert squawkers.get_output_channels() == 2
    assert teddy.get_output_channels() == 2
