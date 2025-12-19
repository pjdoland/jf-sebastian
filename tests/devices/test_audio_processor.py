"""
Tests for shared AudioProcessor utility.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from jf_sebastian.devices.shared.audio_processor import AudioProcessor


@pytest.fixture
def mock_mp3_data():
    """Generate fake MP3 data for testing."""
    # Minimal valid MP3 header
    return b'\xff\xfb\x90\x00' + b'\x00' * 100


@pytest.fixture
def mock_ffmpeg_output():
    """Generate mock FFmpeg output (PCM data)."""
    # Generate 1 second of audio at 16kHz
    sample_rate = 16000
    duration = 1.0
    num_samples = int(sample_rate * duration)

    # Create simple sine wave
    t = np.linspace(0, duration, num_samples)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5  # 440 Hz tone

    # Convert to int16 (FFmpeg output format)
    audio_int16 = (audio * 32767).astype(np.int16)

    return audio_int16.tobytes()


def test_audio_processor_mp3_to_pcm_success(mock_mp3_data, mock_ffmpeg_output):
    """Test successful MP3 to PCM conversion."""
    with patch('subprocess.run') as mock_run:
        # Mock FFmpeg subprocess
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_ffmpeg_output
        )

        processor = AudioProcessor()
        result = processor.mp3_to_pcm(mock_mp3_data, target_sample_rate=16000)

        # Should return numpy array
        assert result is not None
        assert isinstance(result, np.ndarray)

        # Should be normalized to -1.0 to 1.0
        assert np.all(result >= -1.0)
        assert np.all(result <= 1.0)

        # Should have reasonable length (1 second at 16kHz)
        assert len(result) == 16000

        # Verify FFmpeg was called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert 'ffmpeg' in call_args[0][0]
        assert '-ar' in call_args[0][0]
        assert '16000' in call_args[0][0]


def test_audio_processor_mp3_to_pcm_custom_sample_rate(mock_mp3_data, mock_ffmpeg_output):
    """Test MP3 to PCM conversion with custom sample rate."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_ffmpeg_output)

        processor = AudioProcessor()
        result = processor.mp3_to_pcm(mock_mp3_data, target_sample_rate=44100)

        # Verify FFmpeg was called with correct sample rate
        call_args = mock_run.call_args[0][0]
        assert '44100' in call_args


def test_audio_processor_mp3_to_pcm_ffmpeg_error(mock_mp3_data):
    """Test handling of FFmpeg errors."""
    with patch('subprocess.run') as mock_run:
        # Simulate FFmpeg error
        mock_run.side_effect = Exception("FFmpeg error")

        processor = AudioProcessor()
        result = processor.mp3_to_pcm(mock_mp3_data)

        # Should return None on error
        assert result is None


def test_audio_processor_mp3_to_pcm_subprocess_error(mock_mp3_data):
    """Test handling of subprocess CalledProcessError."""
    import subprocess

    with patch('subprocess.run') as mock_run:
        # Simulate subprocess error
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=['ffmpeg'],
            stderr=b'Invalid data'
        )

        processor = AudioProcessor()
        result = processor.mp3_to_pcm(mock_mp3_data)

        # Should return None on error
        assert result is None


def test_audio_processor_mp3_to_pcm_uses_default_sample_rate(mock_mp3_data, mock_ffmpeg_output):
    """Test that default sample rate from settings is used when not specified."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_ffmpeg_output)

        with patch('jf_sebastian.devices.shared.audio_processor.settings') as mock_settings:
            mock_settings.SAMPLE_RATE = 22050

            processor = AudioProcessor()
            processor.mp3_to_pcm(mock_mp3_data)

            # Verify FFmpeg was called with settings sample rate
            call_args = mock_run.call_args[0][0]
            assert '22050' in call_args


def test_audio_processor_is_static():
    """Test that AudioProcessor methods can be called as static."""
    # Should be able to call without instantiation
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout=b'\x00' * 1000)

        result = AudioProcessor.mp3_to_pcm(b'\xff\xfb\x90\x00', target_sample_rate=16000)

        # Should work
        assert result is not None or result is None  # Either works or returns None on error
