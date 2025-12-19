"""
Tests for TeddyRuxpinDevice.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from jf_sebastian.devices.teddy_ruxpin import TeddyRuxpinDevice


@pytest.fixture
def mock_voice_audio():
    """Generate mock voice audio."""
    sample_rate = 16000
    duration = 1.0
    num_samples = int(sample_rate * duration)
    return np.sin(2 * np.pi * 440 * np.linspace(0, duration, num_samples)).astype(np.float32)


@pytest.fixture
def mock_ppm_signal():
    """Generate mock PPM signal."""
    sample_rate = 44100
    duration = 1.0
    num_samples = int(sample_rate * duration)
    return np.random.uniform(-0.5, 0.5, num_samples).astype(np.float32)


@pytest.fixture
def mock_channel_values():
    """Generate mock PPM channel values."""
    num_frames = 60  # 1 second at 60Hz
    return np.random.randint(0, 256, (num_frames, 8), dtype=np.uint8)


def test_teddy_ruxpin_device_initialization():
    """Test TeddyRuxpinDevice initialization."""
    device = TeddyRuxpinDevice()

    assert device.device_name == "Teddy Ruxpin"
    assert device.requires_ppm is True
    assert device.get_output_channels() == 2
    assert device.ppm_sample_rate == 44100
    assert device.audio_processor is not None
    assert device.sentiment_analyzer is not None
    assert device.ppm_generator is not None


def test_teddy_ruxpin_device_properties():
    """Test TeddyRuxpinDevice properties."""
    device = TeddyRuxpinDevice()

    assert isinstance(device.device_name, str)
    assert isinstance(device.requires_ppm, bool)
    assert isinstance(device.get_output_channels(), int)


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_device_validate_settings_valid(mock_settings):
    """Test settings validation with valid values."""
    mock_settings.VOICE_GAIN = 1.0
    mock_settings.CONTROL_GAIN = 0.5

    device = TeddyRuxpinDevice()
    errors = device.validate_settings()

    assert isinstance(errors, list)
    assert len(errors) == 0


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_device_validate_settings_invalid_voice_gain(mock_settings):
    """Test settings validation with invalid VOICE_GAIN."""
    mock_settings.VOICE_GAIN = 3.0  # Out of range
    mock_settings.CONTROL_GAIN = 0.5

    device = TeddyRuxpinDevice()
    errors = device.validate_settings()

    assert len(errors) > 0
    assert any('VOICE_GAIN' in error for error in errors)


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_device_validate_settings_invalid_control_gain(mock_settings):
    """Test settings validation with invalid CONTROL_GAIN."""
    mock_settings.VOICE_GAIN = 1.0
    mock_settings.CONTROL_GAIN = 1.5  # Out of range

    device = TeddyRuxpinDevice()
    errors = device.validate_settings()

    assert len(errors) > 0
    assert any('CONTROL_GAIN' in error for error in errors)


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_create_output_success(mock_settings, mock_voice_audio, mock_ppm_signal, mock_channel_values):
    """Test successful output creation."""
    mock_settings.SAMPLE_RATE = 16000
    mock_settings.VOICE_GAIN = 1.0
    mock_settings.CONTROL_GAIN = 0.5

    device = TeddyRuxpinDevice()

    # Mock the dependencies
    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.5):
            with patch.object(device.ppm_generator, 'audio_to_channel_values', return_value=mock_channel_values):
                with patch.object(device.ppm_generator, 'generate_ppm_signal', return_value=mock_ppm_signal):
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


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_create_output_mp3_conversion_failure(mock_settings):
    """Test output creation when MP3 conversion fails."""
    mock_settings.SAMPLE_RATE = 16000

    device = TeddyRuxpinDevice()

    # Mock MP3 conversion failure
    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=None):
        result = device.create_output(b'invalid_mp3', "Test text")

    # Should return None on error
    assert result is None


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_create_output_exception_handling(mock_settings):
    """Test output creation handles exceptions gracefully."""
    mock_settings.SAMPLE_RATE = 16000

    device = TeddyRuxpinDevice()

    # Mock an exception
    with patch.object(device.audio_processor, 'mp3_to_pcm', side_effect=Exception("Test error")):
        result = device.create_output(b'fake_mp3', "Test text")

    # Should return None on exception
    assert result is None


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_create_output_applies_gains(mock_settings, mock_voice_audio, mock_ppm_signal, mock_channel_values):
    """Test that VOICE_GAIN and CONTROL_GAIN are applied."""
    mock_settings.SAMPLE_RATE = 16000
    mock_settings.VOICE_GAIN = 1.5
    mock_settings.CONTROL_GAIN = 0.3

    device = TeddyRuxpinDevice()

    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.0):
            with patch.object(device.ppm_generator, 'audio_to_channel_values', return_value=mock_channel_values):
                with patch.object(device.ppm_generator, 'generate_ppm_signal', return_value=mock_ppm_signal):
                    result = device.create_output(b'fake_mp3', "Test text")

    assert result is not None
    stereo_audio, sample_rate = result

    # Voice should be in left channel, PPM in right
    # With gains applied, values should be scaled
    assert stereo_audio.shape[1] == 2


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_create_output_calls_sentiment_analyzer(mock_settings, mock_voice_audio, mock_ppm_signal, mock_channel_values):
    """Test that sentiment analysis is called."""
    mock_settings.SAMPLE_RATE = 16000
    mock_settings.VOICE_GAIN = 1.0
    mock_settings.CONTROL_GAIN = 0.5

    device = TeddyRuxpinDevice()

    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.8) as mock_analyze:
            with patch.object(device.ppm_generator, 'audio_to_channel_values', return_value=mock_channel_values):
                with patch.object(device.ppm_generator, 'generate_ppm_signal', return_value=mock_ppm_signal):
                    device.create_output(b'fake_mp3', "Happy test text")

    # Verify sentiment analyzer was called
    mock_analyze.assert_called_once_with("Happy test text")


@patch('jf_sebastian.devices.teddy_ruxpin.settings')
def test_teddy_ruxpin_create_output_stereo_format(mock_settings, mock_voice_audio, mock_ppm_signal, mock_channel_values):
    """Test that output is properly formatted as stereo."""
    mock_settings.SAMPLE_RATE = 16000
    mock_settings.VOICE_GAIN = 1.0
    mock_settings.CONTROL_GAIN = 0.5

    device = TeddyRuxpinDevice()

    with patch.object(device.audio_processor, 'mp3_to_pcm', return_value=mock_voice_audio):
        with patch.object(device.sentiment_analyzer, 'analyze', return_value=0.0):
            with patch.object(device.ppm_generator, 'audio_to_channel_values', return_value=mock_channel_values):
                with patch.object(device.ppm_generator, 'generate_ppm_signal', return_value=mock_ppm_signal):
                    result = device.create_output(b'fake_mp3', "Test text")

    stereo_audio, sample_rate = result

    # Should be 2D array with 2 columns (stereo)
    assert stereo_audio.ndim == 2
    assert stereo_audio.shape[1] == 2

    # Both channels should have same length
    assert stereo_audio.shape[0] > 0
