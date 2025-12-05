"""
Tests for audio input module.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from teddy_ruxpin.modules.audio_input import AudioInput


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_audio_input_initialization_default_device(mock_pyaudio_class, mock_pyaudio):
    """Test AudioInput initialization with default device."""
    mock_pyaudio_class.return_value = mock_pyaudio

    audio_input = AudioInput()

    # Should initialize PyAudio
    mock_pyaudio_class.assert_called_once()

    # Should use default input device
    assert audio_input.device_index == 0  # MacBook Air Microphone from mock


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
@patch('teddy_ruxpin.modules.audio_input.find_audio_device_by_name')
def test_audio_input_initialization_by_name(mock_find_device, mock_pyaudio_class, mock_pyaudio):
    """Test AudioInput initialization with device name."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_find_device.return_value = 0  # MacBook Air Microphone

    audio_input = AudioInput(device_name="MacBook Air Microphone")

    # Should find device by name
    mock_find_device.assert_called_once()
    assert audio_input.device_index == 0


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_audio_input_initialization_by_index(mock_pyaudio_class, mock_pyaudio):
    """Test AudioInput initialization with device index."""
    mock_pyaudio_class.return_value = mock_pyaudio

    audio_input = AudioInput(device_index=0)

    assert audio_input.device_index == 0


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_start_recording(mock_pyaudio_class, mock_pyaudio):
    """Test starting audio recording."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value = mock_stream

    audio_input = AudioInput()
    audio_input.start_recording()

    # Should open stream
    mock_pyaudio.open.assert_called_once()

    # Should be recording
    assert audio_input.is_recording is True

    # Should clear buffer
    assert len(audio_input.frames) == 0


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_stop_recording(mock_pyaudio_class, mock_pyaudio):
    """Test stopping audio recording."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value = mock_stream

    audio_input = AudioInput()
    audio_input.start_recording()
    audio_input.stop_recording()

    # Should stop and close stream
    mock_stream.stop_stream.assert_called_once()
    mock_stream.close.assert_called_once()

    # Should not be recording
    assert audio_input.is_recording is False


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_get_audio_data(mock_pyaudio_class, mock_pyaudio):
    """Test getting recorded audio data."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value = mock_stream

    audio_input = AudioInput()
    audio_input.start_recording()

    # Simulate recorded frames
    test_frames = [b'\x00\x01' * 512 for _ in range(10)]
    audio_input.frames = test_frames

    audio_data = audio_input.get_audio_data()

    # Should return concatenated bytes
    assert isinstance(audio_data, bytes)
    assert len(audio_data) == len(b''.join(test_frames))


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_get_audio_data_empty(mock_pyaudio_class, mock_pyaudio):
    """Test getting audio data when no frames recorded."""
    mock_pyaudio_class.return_value = mock_pyaudio

    audio_input = AudioInput()

    audio_data = audio_input.get_audio_data()

    # Should return empty bytes
    assert audio_data == b''


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_read_chunk(mock_pyaudio_class, mock_pyaudio):
    """Test reading audio chunk."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_stream.read.return_value = b'\x00\x01' * 512
    mock_pyaudio.open.return_value = mock_stream

    audio_input = AudioInput(chunk_size=512)
    audio_input.start_recording()

    chunk = audio_input.read_chunk()

    # Should read from stream
    mock_stream.read.assert_called_with(512, exception_on_overflow=False)

    # Should return audio data
    assert isinstance(chunk, bytes)
    assert len(chunk) > 0


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_read_chunk_not_recording(mock_pyaudio_class, mock_pyaudio):
    """Test reading chunk when not recording."""
    mock_pyaudio_class.return_value = mock_pyaudio

    audio_input = AudioInput()

    chunk = audio_input.read_chunk()

    # Should return empty bytes
    assert chunk == b''


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_cleanup(mock_pyaudio_class, mock_pyaudio):
    """Test cleanup terminates PyAudio."""
    mock_pyaudio_class.return_value = mock_pyaudio

    audio_input = AudioInput()
    audio_input.cleanup()

    # Should terminate PyAudio
    mock_pyaudio.terminate.assert_called_once()


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_cleanup_while_recording(mock_pyaudio_class, mock_pyaudio):
    """Test cleanup stops recording if active."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value = mock_stream

    audio_input = AudioInput()
    audio_input.start_recording()
    audio_input.cleanup()

    # Should stop stream
    mock_stream.stop_stream.assert_called_once()
    mock_stream.close.assert_called_once()

    # Should terminate PyAudio
    mock_pyaudio.terminate.assert_called_once()


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_audio_input_retry_on_error(mock_pyaudio_class, mock_pyaudio):
    """Test retry logic when stream opening fails."""
    mock_pyaudio_class.return_value = mock_pyaudio

    # Mock stream to fail first time, succeed second time
    mock_stream = MagicMock()
    mock_pyaudio.open.side_effect = [
        OSError(-9986, "Internal PortAudio error"),  # First attempt fails
        mock_stream  # Second succeeds
    ]

    audio_input = AudioInput()
    audio_input.start_recording()

    # Should have retried
    assert mock_pyaudio.open.call_count == 2
    assert audio_input.is_recording is True


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_context_manager(mock_pyaudio_class, mock_pyaudio):
    """Test AudioInput as context manager."""
    mock_pyaudio_class.return_value = mock_pyaudio

    with AudioInput() as audio_input:
        assert audio_input is not None

    # Should cleanup on exit
    mock_pyaudio.terminate.assert_called_once()


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
@patch('teddy_ruxpin.modules.audio_input.find_audio_device_by_name')
def test_device_name_not_found_fallback(mock_find_device, mock_pyaudio_class, mock_pyaudio):
    """Test fallback to default when device name not found."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_find_device.return_value = None  # Device not found

    audio_input = AudioInput(device_name="Nonexistent Device")

    # Should fall back to default device
    assert audio_input.device_index == 0  # Default input from mock


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_audio_input_sample_rate(mock_pyaudio_class, mock_pyaudio):
    """Test AudioInput with custom sample rate."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value = mock_stream

    audio_input = AudioInput(sample_rate=44100)
    audio_input.start_recording()

    # Should use specified sample rate
    call_kwargs = mock_pyaudio.open.call_args[1]
    assert call_kwargs['rate'] == 44100


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_audio_input_chunk_size(mock_pyaudio_class, mock_pyaudio):
    """Test AudioInput with custom chunk size."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_stream.read.return_value = b'\x00\x01' * 1024
    mock_pyaudio.open.return_value = mock_stream

    audio_input = AudioInput(chunk_size=1024)
    audio_input.start_recording()
    audio_input.read_chunk()

    # Should read with specified chunk size
    mock_stream.read.assert_called_with(1024, exception_on_overflow=False)


@patch('teddy_ruxpin.modules.audio_input.pyaudio.PyAudio')
def test_multiple_start_stop_cycles(mock_pyaudio_class, mock_pyaudio):
    """Test multiple recording cycles."""
    mock_pyaudio_class.return_value = mock_pyaudio
    mock_stream = MagicMock()
    mock_pyaudio.open.return_value = mock_stream

    audio_input = AudioInput()

    # First cycle
    audio_input.start_recording()
    assert audio_input.is_recording is True
    audio_input.stop_recording()
    assert audio_input.is_recording is False

    # Second cycle
    audio_input.start_recording()
    assert audio_input.is_recording is True
    audio_input.stop_recording()
    assert audio_input.is_recording is False

    # Should have opened stream twice
    assert mock_pyaudio.open.call_count == 2
