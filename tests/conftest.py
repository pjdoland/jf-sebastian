"""
Pytest configuration and shared fixtures for J.F. Sebastian tests.
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, MagicMock
import tempfile


@pytest.fixture
def sample_audio():
    """Generate sample audio waveform for testing."""
    sample_rate = 16000
    duration = 2.0
    frequency = 440  # A4 note
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = np.sin(2 * np.pi * frequency * t).astype(np.float32) * 0.5
    return audio, sample_rate


@pytest.fixture
def mock_pyaudio():
    """Mock PyAudio instance for testing."""
    mock = MagicMock()
    mock.get_device_count.return_value = 3
    mock.get_device_info_by_index.side_effect = lambda idx: {
        0: {
            'name': 'MacBook Air Microphone',
            'maxInputChannels': 1,
            'maxOutputChannels': 0,
            'defaultSampleRate': 44100.0
        },
        1: {
            'name': 'MacBook Air Speakers',
            'maxInputChannels': 0,
            'maxOutputChannels': 2,
            'defaultSampleRate': 44100.0
        },
        2: {
            'name': 'Arsvita USB Audio',
            'maxInputChannels': 0,
            'maxOutputChannels': 2,
            'defaultSampleRate': 48000.0
        }
    }[idx]
    mock.get_default_input_device_info.return_value = {
        'index': 0,
        'name': 'MacBook Air Microphone'
    }
    mock.get_default_output_device_info.return_value = {
        'index': 1,
        'name': 'MacBook Air Speakers'
    }
    return mock


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing."""
    mock_client = MagicMock()

    # Mock Whisper STT response
    mock_client.audio.transcriptions.create.return_value = MagicMock(
        text="Hello, this is a test transcription"
    )

    # Mock GPT chat completion response
    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(
            message=MagicMock(
                content="This is a test response from the AI."
            )
        )
    ]
    mock_client.chat.completions.create.return_value = mock_completion

    # Mock TTS response
    mock_client.audio.speech.create.return_value = MagicMock(
        content=b'\xff\xfb\x90\x00'  # Fake MP3 data
    )

    return mock_client


@pytest.fixture
def mock_porcupine():
    """Mock Porcupine wake word detector."""
    mock = MagicMock()
    mock.process.return_value = -1  # No wake word detected
    mock.frame_length = 512
    mock.sample_rate = 16000
    return mock


@pytest.fixture
def temp_audio_dir():
    """Create temporary directory for audio files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_ppm_channel_values():
    """Generate sample PPM channel values for testing."""
    num_frames = 100  # 100 frames @ 60Hz = ~1.67 seconds
    channels = np.zeros((num_frames, 8), dtype=np.uint8)

    # Add some mouth movement (channels 2 and 3)
    mouth_pattern = np.sin(np.linspace(0, 4 * np.pi, num_frames)) * 127 + 128
    channels[:, 2] = (mouth_pattern * 0.7).astype(np.uint8)  # Upper jaw
    channels[:, 3] = mouth_pattern.astype(np.uint8)  # Lower jaw

    # Add eye position (channel 1)
    channels[:, 1] = 128  # Middle position

    return channels


@pytest.fixture
def mock_personality():
    """Mock personality instance."""
    mock = MagicMock()
    mock.name = "TestBot"
    mock.system_prompt = "You are a test bot."
    mock.tts_voice = "onyx"
    mock.wake_word_path = Path("/fake/path/wake_word.ppn")
    mock.filler_phrases = [
        "Let me think about that for a moment...",
        "Give me a second to process that...",
        "Hold on, checking something..."
    ]
    mock.filler_audio_dir = Path("/fake/path/filler_audio")
    mock.has_fillers = True
    return mock


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings configuration."""
    class MockSettings:
        OPENAI_API_KEY = "test-api-key"
        PICOVOICE_ACCESS_KEY = "test-pv-key"
        PERSONALITY = "johnny"
        INPUT_DEVICE_NAME = "MacBook Air Microphone"
        INPUT_DEVICE_INDEX = -1
        OUTPUT_DEVICE_NAME = "Arsvita"
        OUTPUT_DEVICE_INDEX = -1
        SAMPLE_RATE = 16000
        CHUNK_SIZE = 512
        CHANNELS = 2
        SILENCE_THRESHOLD = 1000
        SILENCE_DURATION = 2.0

        @staticmethod
        def validate():
            return []

    return MockSettings
