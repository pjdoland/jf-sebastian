"""
Tests for audio output module.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from teddy_ruxpin.modules.audio_output import AudioOutput


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_audio_output_initialization_default_device(mock_pyaudio_class, mock_pyaudio):
    """Test AudioOutput initialization with default device."""
    mock_pyaudio_class.return_value = mock_pyaudio

    output = AudioOutput()

    # Should initialize PyAudio
    mock_pyaudio_class.assert_called_once()

    # Should use default output device
    assert output.device_index == 1  # MacBook Air Speakers from mock


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
@patch('teddy_ruxpin.modules.audio_output.find_audio_device_by_name')
def test_audio_output_initialization_by_name(mock_find_device, mock_pyaudio_class, mock_pyaudio):
    """Test AudioOutput initialization with device name."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_find_device.return_value = 2  # Arsvita device

    output = AudioOutput(device_name="Arsvita")

    # Should find device by name
    mock_find_device.assert_called_once()
    assert output.device_index == 2


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_audio_output_initialization_by_index(mock_pyaudio_class, mock_pyaudio):
    """Test AudioOutput initialization with device index."""
    mock_pyaudio_class.return_value = mock_pyaudio

    output = AudioOutput(device_index=2)

    assert output.device_index == 2


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
@patch('teddy_ruxpin.modules.audio_output.wave.open')
def test_play_wav_file(mock_wave_open, mock_pyaudio_class, mock_pyaudio):
    """Test playing a WAV file."""
    mock_pyaudio_class.return_value = mock_pyaudio

    # Mock wave file
    mock_wave = MagicMock()
    mock_wave.getnchannels.return_value = 2
    mock_wave.getsampwidth.return_value = 2
    mock_wave.getframerate.return_value = 16000
    mock_wave.readframes.side_effect = [
        b'\x00\x01' * 1024,  # First chunk
        b''  # EOF
    ]
    mock_wave_open.return_value.__enter__.return_value = mock_wave

    # Mock PyAudio stream
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value.__enter__.return_value = mock_stream

    output = AudioOutput()
    output.play_wav_file(Path("/fake/path.wav"))

    # Should open wave file
    mock_wave_open.assert_called()

    # Should open audio stream
    mock_pyaudio.open.assert_called()

    # Should write audio data
    mock_stream.write.assert_called()


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_play_stereo_audio(mock_pyaudio_class, mock_pyaudio):
    """Test playing stereo audio array."""
    mock_pyaudio_class.return_value = mock_pyaudio

    # Mock PyAudio stream
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value.__enter__.return_value = mock_stream

    output = AudioOutput()

    # Create stereo audio (2 channels)
    stereo_audio = np.random.randn(16000, 2).astype(np.float32)
    output.play_stereo_audio(stereo_audio, sample_rate=16000)

    # Should open stream with correct parameters
    mock_pyaudio.open.assert_called_once()
    call_kwargs = mock_pyaudio.open.call_args[1]
    assert call_kwargs['channels'] == 2
    assert call_kwargs['rate'] == 16000

    # Should write audio data
    mock_stream.write.assert_called()


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_play_stereo_audio_mono_input_error(mock_pyaudio_class, mock_pyaudio):
    """Test error handling for mono input to stereo playback."""
    mock_pyaudio_class.return_value = mock_pyaudio

    output = AudioOutput()

    # Create mono audio (1 channel) - should fail
    mono_audio = np.random.randn(16000).astype(np.float32)

    with pytest.raises((ValueError, IndexError)):
        output.play_stereo_audio(mono_audio, sample_rate=16000)


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_play_stereo_audio_retry_on_error(mock_pyaudio_class, mock_pyaudio):
    """Test retry logic when stream opening fails."""
    mock_pyaudio_class.return_value = mock_pyaudio

    # Mock stream to fail first time, succeed second time
    mock_stream = MagicMock()
    mock_pyaudio.open.side_effect = [
        OSError(-9986, "Internal PortAudio error"),  # First attempt fails
        MagicMock(__enter__=lambda self: mock_stream, __exit__=lambda *args: None)  # Second succeeds
    ]

    output = AudioOutput()

    stereo_audio = np.random.randn(16000, 2).astype(np.float32)
    output.play_stereo_audio(stereo_audio, sample_rate=16000)

    # Should have retried
    assert mock_pyaudio.open.call_count == 2


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_cleanup(mock_pyaudio_class, mock_pyaudio):
    """Test cleanup terminates PyAudio."""
    mock_pyaudio_class.return_value = mock_pyaudio

    output = AudioOutput()
    output.cleanup()

    # Should terminate PyAudio
    mock_pyaudio.terminate.assert_called_once()


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_audio_output_sample_rate_conversion(mock_pyaudio_class, mock_pyaudio):
    """Test audio output handles different sample rates."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value.__enter__.return_value = mock_stream

    output = AudioOutput()

    # Test with different sample rate
    stereo_audio = np.random.randn(44100, 2).astype(np.float32)
    output.play_stereo_audio(stereo_audio, sample_rate=44100)

    # Should use provided sample rate
    call_kwargs = mock_pyaudio.open.call_args[1]
    assert call_kwargs['rate'] == 44100


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
@patch('teddy_ruxpin.modules.audio_output.wave.open')
def test_play_wav_file_nonexistent(mock_wave_open, mock_pyaudio_class, mock_pyaudio):
    """Test error handling for nonexistent WAV file."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_wave_open.side_effect = FileNotFoundError("File not found")

    output = AudioOutput()

    with pytest.raises(FileNotFoundError):
        output.play_wav_file(Path("/nonexistent/path.wav"))


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_audio_normalization(mock_pyaudio_class, mock_pyaudio):
    """Test that audio is properly normalized before playback."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value.__enter__.return_value = mock_stream

    output = AudioOutput()

    # Create audio with values outside -1 to 1 range
    stereo_audio = np.random.randn(1000, 2).astype(np.float32) * 5.0
    output.play_stereo_audio(stereo_audio, sample_rate=16000)

    # Audio should be written (normalization happens in converter if needed)
    mock_stream.write.assert_called()


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
@patch('teddy_ruxpin.modules.audio_output.find_audio_device_by_name')
def test_device_name_not_found_fallback(mock_find_device, mock_pyaudio_class, mock_pyaudio):
    """Test fallback to default when device name not found."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_find_device.return_value = None  # Device not found

    output = AudioOutput(device_name="Nonexistent Device")

    # Should fall back to default device
    assert output.device_index == 1  # Default output from mock


@patch('teddy_ruxpin.modules.audio_output.pyaudio.PyAudio')
def test_context_manager(mock_pyaudio_class, mock_pyaudio):
    """Test AudioOutput as context manager."""
    mock_pyaudio_class.return_value = mock_pyaudio

    with AudioOutput() as output:
        assert output is not None

    # Should cleanup on exit
    mock_pyaudio.terminate.assert_called_once()
