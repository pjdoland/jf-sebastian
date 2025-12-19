"""
Tests for animatronic control module.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
import subprocess

from jf_sebastian.modules.animatronic_control import (
    AnimatronicControlGenerator,
    save_stereo_wav
)


def test_animatronic_control_initialization():
    """Test AnimatronicControlGenerator initialization."""
    generator = AnimatronicControlGenerator()

    assert generator.ppm_sample_rate == 44100
    assert generator.ppm_generator is not None
    assert generator.sentiment_analyzer is not None


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
@patch('jf_sebastian.modules.animatronic_control.PPMGenerator')
def test_create_stereo_output_success(mock_ppm_generator_class, mock_subprocess, mock_settings):
    """Test successful stereo output creation."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock FFmpeg subprocess
    mock_audio = np.array([100, 200, 300], dtype=np.int16)
    mock_subprocess.return_value = MagicMock(
        stdout=mock_audio.tobytes()
    )

    # Mock PPM generator
    mock_ppm_instance = MagicMock()
    mock_ppm_instance.audio_to_channel_values.return_value = [(0.5, 0.5, 0.5, 0.5)]
    mock_ppm_instance.generate_ppm_signal.return_value = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    mock_ppm_generator_class.return_value = mock_ppm_instance

    generator = AnimatronicControlGenerator()

    # Create test MP3 data
    mp3_data = b"fake mp3 data"
    response_text = "Hello, this is a test response"

    result = generator.create_stereo_output(mp3_data, response_text)

    assert result is not None
    stereo_audio, sample_rate = result

    # Check shape and sample rate
    assert sample_rate == 44100
    assert stereo_audio.shape[1] == 2  # Stereo
    assert stereo_audio.dtype == np.float64 or stereo_audio.dtype == np.float32


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
def test_mp3_to_pcm_success(mock_subprocess, mock_settings):
    """Test MP3 to PCM conversion."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock FFmpeg output
    mock_audio = np.array([32767, -32768, 0], dtype=np.int16)
    mock_subprocess.return_value = MagicMock(
        stdout=mock_audio.tobytes()
    )

    generator = AnimatronicControlGenerator()
    mp3_data = b"fake mp3"

    result = generator._mp3_to_pcm(mp3_data)

    assert result is not None
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32

    # Check normalization
    assert np.all(result >= -1.0)
    assert np.all(result <= 1.0)


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
def test_mp3_to_pcm_ffmpeg_error(mock_subprocess, mock_settings):
    """Test MP3 to PCM conversion with FFmpeg error."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock FFmpeg failure
    mock_subprocess.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd="ffmpeg",
        stderr=b"FFmpeg error"
    )

    generator = AnimatronicControlGenerator()
    mp3_data = b"fake mp3"

    result = generator._mp3_to_pcm(mp3_data)

    assert result is None


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
def test_mp3_to_pcm_exception(mock_subprocess, mock_settings):
    """Test MP3 to PCM conversion with general exception."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock general exception
    mock_subprocess.side_effect = Exception("Unexpected error")

    generator = AnimatronicControlGenerator()
    mp3_data = b"fake mp3"

    result = generator._mp3_to_pcm(mp3_data)

    assert result is None


def test_analyze_sentiment_positive():
    """Test sentiment analysis with positive text."""
    generator = AnimatronicControlGenerator()

    sentiment = generator._analyze_sentiment("I love this! It's wonderful and amazing!")

    assert isinstance(sentiment, float)
    assert sentiment > 0  # Positive sentiment


def test_analyze_sentiment_negative():
    """Test sentiment analysis with negative text."""
    generator = AnimatronicControlGenerator()

    sentiment = generator._analyze_sentiment("I hate this. It's terrible and awful.")

    assert isinstance(sentiment, float)
    assert sentiment < 0  # Negative sentiment


def test_analyze_sentiment_neutral():
    """Test sentiment analysis with neutral text."""
    generator = AnimatronicControlGenerator()

    sentiment = generator._analyze_sentiment("The sky is blue.")

    assert isinstance(sentiment, float)
    assert -0.5 < sentiment < 0.5  # Neutral sentiment


def test_analyze_sentiment_empty():
    """Test sentiment analysis with empty text."""
    generator = AnimatronicControlGenerator()

    sentiment = generator._analyze_sentiment("")

    assert isinstance(sentiment, float)


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
@patch('jf_sebastian.modules.animatronic_control.PPMGenerator')
def test_create_stereo_output_mp3_conversion_failure(mock_ppm_generator_class, mock_subprocess, mock_settings):
    """Test stereo output creation when MP3 conversion fails."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock FFmpeg failure
    mock_subprocess.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd="ffmpeg"
    )

    mock_ppm_generator_class.return_value = MagicMock()

    generator = AnimatronicControlGenerator()

    mp3_data = b"fake mp3 data"
    response_text = "Test"

    result = generator.create_stereo_output(mp3_data, response_text)

    assert result is None


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
@patch('jf_sebastian.modules.animatronic_control.PPMGenerator')
def test_create_stereo_output_general_exception(mock_ppm_generator_class, mock_subprocess, mock_settings):
    """Test stereo output creation with general exception."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock successful FFmpeg
    mock_audio = np.array([100, 200], dtype=np.int16)
    mock_subprocess.return_value = MagicMock(stdout=mock_audio.tobytes())

    # Mock PPM generator to raise exception
    mock_ppm_instance = MagicMock()
    mock_ppm_instance.audio_to_channel_values.side_effect = Exception("PPM error")
    mock_ppm_generator_class.return_value = mock_ppm_instance

    generator = AnimatronicControlGenerator()

    mp3_data = b"fake mp3"
    response_text = "Test"

    result = generator.create_stereo_output(mp3_data, response_text)

    assert result is None


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
@patch('jf_sebastian.modules.animatronic_control.PPMGenerator')
def test_create_stereo_output_channel_structure(mock_ppm_generator_class, mock_subprocess, mock_settings):
    """Test that stereo output has correct channel structure."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock FFmpeg
    mock_audio = np.array([1000, 2000, 3000], dtype=np.int16)
    mock_subprocess.return_value = MagicMock(stdout=mock_audio.tobytes())

    # Mock PPM generator
    mock_ppm_instance = MagicMock()
    mock_ppm_instance.audio_to_channel_values.return_value = [(0.5, 0.5, 0.5, 0.5)]
    mock_ppm_instance.generate_ppm_signal.return_value = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    mock_ppm_generator_class.return_value = mock_ppm_instance

    generator = AnimatronicControlGenerator()

    mp3_data = b"fake mp3"
    response_text = "Test"

    result = generator.create_stereo_output(mp3_data, response_text)

    assert result is not None
    stereo_audio, sample_rate = result

    # Verify stereo structure (2 channels)
    assert stereo_audio.shape[1] == 2
    # LEFT channel = voice, RIGHT channel = control
    assert stereo_audio.shape[0] > 0  # Has samples


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
@patch('jf_sebastian.modules.animatronic_control.PPMGenerator')
def test_create_stereo_output_applies_gains(mock_ppm_generator_class, mock_subprocess, mock_settings):
    """Test that gains are applied to voice and control channels."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock FFmpeg
    mock_audio = np.array([10000], dtype=np.int16)
    mock_subprocess.return_value = MagicMock(stdout=mock_audio.tobytes())

    # Mock PPM generator
    mock_ppm_instance = MagicMock()
    mock_ppm_instance.audio_to_channel_values.return_value = [(0.5, 0.5, 0.5, 0.5)]
    mock_ppm_instance.generate_ppm_signal.return_value = np.array([0.5], dtype=np.float32)
    mock_ppm_generator_class.return_value = mock_ppm_instance

    generator = AnimatronicControlGenerator()

    mp3_data = b"fake mp3"
    response_text = "Test"

    result = generator.create_stereo_output(mp3_data, response_text)

    assert result is not None
    stereo_audio, sample_rate = result

    # Check that audio is not at full scale (gains applied)
    assert np.max(np.abs(stereo_audio)) < 1.0


@patch('scipy.io.wavfile.write')
def test_save_stereo_wav_success(mock_wavfile_write):
    """Test saving stereo WAV file."""
    stereo_audio = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    sample_rate = 44100
    filename = "test.wav"

    save_stereo_wav(stereo_audio, sample_rate, filename)

    mock_wavfile_write.assert_called_once()
    args, kwargs = mock_wavfile_write.call_args
    assert args[0] == filename
    assert args[1] == sample_rate
    # Check that audio was converted to int16
    assert args[2].dtype == np.int16


@patch('scipy.io.wavfile.write')
def test_save_stereo_wav_exception(mock_wavfile_write):
    """Test save_stereo_wav with exception."""
    mock_wavfile_write.side_effect = Exception("Write error")

    stereo_audio = np.array([[0.1, 0.2]], dtype=np.float32)
    sample_rate = 44100
    filename = "test.wav"

    # Should not raise exception
    save_stereo_wav(stereo_audio, sample_rate, filename)


def test_animatronic_control_generator_sample_rate():
    """Test that PPM sample rate is set to 44100."""
    generator = AnimatronicControlGenerator()

    assert generator.ppm_sample_rate == 44100


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
@patch('jf_sebastian.modules.animatronic_control.PPMGenerator')
def test_create_stereo_output_length_matching(mock_ppm_generator_class, mock_subprocess, mock_settings):
    """Test that voice and PPM signals are matched in length."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock FFmpeg with specific length
    mock_audio = np.array([100] * 1000, dtype=np.int16)
    mock_subprocess.return_value = MagicMock(stdout=mock_audio.tobytes())

    # Mock PPM generator with different length
    mock_ppm_instance = MagicMock()
    mock_ppm_instance.audio_to_channel_values.return_value = [(0.5, 0.5, 0.5, 0.5)] * 10
    mock_ppm_instance.generate_ppm_signal.return_value = np.array([0.1] * 800, dtype=np.float32)
    mock_ppm_generator_class.return_value = mock_ppm_instance

    generator = AnimatronicControlGenerator()

    mp3_data = b"fake mp3"
    response_text = "Test"

    result = generator.create_stereo_output(mp3_data, response_text)

    assert result is not None
    stereo_audio, sample_rate = result

    # Both channels should have same length
    assert stereo_audio.shape[0] > 0
    assert stereo_audio.shape[1] == 2


@patch('jf_sebastian.modules.animatronic_control.settings')
@patch('subprocess.run')
@patch('jf_sebastian.modules.animatronic_control.PPMGenerator')
def test_create_stereo_output_uses_sentiment(mock_ppm_generator_class, mock_subprocess, mock_settings):
    """Test that sentiment is passed to PPM generator."""
    mock_settings.SAMPLE_RATE = 16000

    # Mock FFmpeg
    mock_audio = np.array([100], dtype=np.int16)
    mock_subprocess.return_value = MagicMock(stdout=mock_audio.tobytes())

    # Mock PPM generator
    mock_ppm_instance = MagicMock()
    mock_ppm_instance.audio_to_channel_values.return_value = [(0.5, 0.5, 0.5, 0.5)]
    mock_ppm_instance.generate_ppm_signal.return_value = np.array([0.1], dtype=np.float32)
    mock_ppm_generator_class.return_value = mock_ppm_instance

    generator = AnimatronicControlGenerator()

    mp3_data = b"fake mp3"
    response_text = "I'm so happy and excited!"  # Positive sentiment

    result = generator.create_stereo_output(mp3_data, response_text)

    # Verify audio_to_channel_values was called with sentiment parameter
    mock_ppm_instance.audio_to_channel_values.assert_called_once()
    call_kwargs = mock_ppm_instance.audio_to_channel_values.call_args.kwargs
    assert 'sentiment' in call_kwargs
    # Sentiment should be a float
    assert isinstance(call_kwargs['sentiment'], float)


def test_sentiment_analyzer_error_handling():
    """Test sentiment analysis error handling."""
    generator = AnimatronicControlGenerator()

    # Patch the sentiment analyzer to raise exception
    with patch.object(generator.sentiment_analyzer, 'polarity_scores', side_effect=Exception("Sentiment error")):
        sentiment = generator._analyze_sentiment("Test text")

        # Should return neutral sentiment (0.0) on error
        assert sentiment == 0.0
