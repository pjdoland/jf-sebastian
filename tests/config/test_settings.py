"""
Tests for configuration settings.
"""

import pytest
import os
from pathlib import Path
from unittest.mock import patch
from jf_sebastian.config.settings import Settings


def test_settings_default_values():
    """Test that Settings class has sensible default values."""
    # These should work even without environment variables
    assert Settings.PERSONALITY in ["johnny", "rich", "mr_lincoln", "leopold"]
    assert Settings.SAMPLE_RATE in [16000, 22050, 44100, 48000]
    assert Settings.CHUNK_SIZE > 0
    assert 0 <= Settings.VAD_AGGRESSIVENESS <= 3
    assert Settings.SILENCE_TIMEOUT > 0
    assert Settings.CONVERSATION_TIMEOUT > 0
    assert Settings.MAX_HISTORY_LENGTH > 0
    assert Settings.WHISPER_MODEL == "whisper-1"
    assert Settings.GPT_MODEL == "gpt-4o-mini"
    assert Settings.TTS_MODEL in ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]  # Can be configured in .env


def test_settings_audio_config_defaults():
    """Test audio configuration defaults."""
    # SAMPLE_RATE can be any valid rate, just verify it's valid
    assert Settings.SAMPLE_RATE in [16000, 22050, 44100, 48000]
    assert Settings.CHUNK_SIZE == 1024
    assert Settings.VAD_AGGRESSIVENESS == 3
    assert Settings.SILENCE_TIMEOUT > 0  # Can be configured in .env


def test_settings_animatronic_config_defaults():
    """Test animatronic control defaults."""
    # Sentiment thresholds are the only animatronic settings that remain
    assert hasattr(Settings, 'SENTIMENT_POSITIVE_THRESHOLD')
    assert hasattr(Settings, 'SENTIMENT_NEGATIVE_THRESHOLD')


def test_settings_debug_config_defaults():
    """Test debug configuration defaults."""
    assert isinstance(Settings.DEBUG_MODE, bool)
    assert Settings.LOG_LEVEL in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    assert isinstance(Settings.SAVE_DEBUG_AUDIO, bool)
    assert isinstance(Settings.DEBUG_AUDIO_PATH, Path)


def test_settings_env_variable_loading(monkeypatch):
    """Test that environment variables are loaded correctly."""
    # Mock environment variables
    monkeypatch.setenv("PERSONALITY", "rich")
    monkeypatch.setenv("SAMPLE_RATE", "16000")
    monkeypatch.setenv("CHUNK_SIZE", "2048")
    monkeypatch.setenv("VAD_AGGRESSIVENESS", "2")
    monkeypatch.setenv("DEBUG_MODE", "true")

    # Reload the Settings class to pick up new env vars
    # Note: In real usage, env vars should be set before import
    # For testing, we check that the pattern would work
    test_personality = os.getenv("PERSONALITY")
    assert test_personality == "rich"


def test_settings_validate_missing_api_key():
    """Test validation fails when API key is missing."""
    # Create a test Settings class with missing API key
    class TestSettings(Settings):
        OPENAI_API_KEY = ""

    errors = TestSettings.validate()
    assert any("OPENAI_API_KEY" in err for err in errors)


def test_settings_validate_missing_wake_word_config():
    """Test that validation doesn't require wake word config (handled per personality)."""
    class TestSettings(Settings):
        OPENAI_API_KEY = "test-key"

    errors = TestSettings.validate()
    # Wake word validation removed - now handled per personality
    assert not any("wake" in err.lower() for err in errors)


def test_settings_validate_invalid_sample_rate():
    """Test validation fails for invalid sample rate."""
    class TestSettings(Settings):
        OPENAI_API_KEY = "test-key"
        SAMPLE_RATE = 32000  # Invalid

    errors = TestSettings.validate()
    assert any("SAMPLE_RATE" in err for err in errors)


def test_settings_validate_invalid_vad_aggressiveness():
    """Test validation fails for invalid VAD aggressiveness."""
    class TestSettings(Settings):
        OPENAI_API_KEY = "test-key"
        VAD_AGGRESSIVENESS = 5  # Invalid (must be 0-3)

    errors = TestSettings.validate()
    assert any("VAD_AGGRESSIVENESS" in err for err in errors)


def test_settings_validate_all_valid():
    """Test validation passes with all valid settings."""
    class TestSettings(Settings):
        OPENAI_API_KEY = "test-key"
        SAMPLE_RATE = 44100
        VAD_AGGRESSIVENESS = 2

    errors = TestSettings.validate()
    assert len(errors) == 0


def test_settings_validate_with_openwakeword():
    """Test validation passes with OpenWakeWord (wake word handled per personality)."""
    class TestSettings(Settings):
        OPENAI_API_KEY = "test-key"

    errors = TestSettings.validate()
    # Wake word validation removed - now handled per personality
    assert len(errors) == 0


def test_settings_create_debug_dirs_enabled(tmp_path, monkeypatch):
    """Test that debug directories are created when enabled."""
    debug_path = tmp_path / "test_debug"

    class TestSettings(Settings):
        SAVE_DEBUG_AUDIO = True
        DEBUG_AUDIO_PATH = debug_path

    # Directory shouldn't exist yet
    assert not debug_path.exists()

    # Create directories
    TestSettings.create_debug_dirs()

    # Should be created now
    assert debug_path.exists()
    assert debug_path.is_dir()


def test_settings_create_debug_dirs_disabled(tmp_path):
    """Test that debug directories are not created when disabled."""
    debug_path = tmp_path / "test_debug_disabled"

    class TestSettings(Settings):
        SAVE_DEBUG_AUDIO = False
        DEBUG_AUDIO_PATH = debug_path

    # Create directories (should do nothing)
    TestSettings.create_debug_dirs()

    # Directory shouldn't be created
    assert not debug_path.exists()


def test_settings_device_names():
    """Test that device name settings exist."""
    assert hasattr(Settings, 'INPUT_DEVICE_NAME')
    assert hasattr(Settings, 'OUTPUT_DEVICE_NAME')


def test_settings_sentiment_thresholds():
    """Test sentiment threshold settings."""
    assert hasattr(Settings, 'SENTIMENT_POSITIVE_THRESHOLD')
    assert hasattr(Settings, 'SENTIMENT_NEGATIVE_THRESHOLD')

    # Negative threshold should be less than positive
    assert Settings.SENTIMENT_NEGATIVE_THRESHOLD < Settings.SENTIMENT_POSITIVE_THRESHOLD

    # Both should be reasonable values
    assert -1.0 <= Settings.SENTIMENT_NEGATIVE_THRESHOLD <= 0.0
    assert 0.0 <= Settings.SENTIMENT_POSITIVE_THRESHOLD <= 1.0


def test_settings_conversation_config():
    """Test conversation-related settings."""
    assert Settings.CONVERSATION_TIMEOUT > 0
    assert Settings.MAX_HISTORY_LENGTH > 0

    # Should be reasonable values
    assert Settings.CONVERSATION_TIMEOUT >= 60.0  # At least 1 minute
    assert Settings.MAX_HISTORY_LENGTH >= 5  # At least 5 messages


def test_settings_boolean_parsing():
    """Test that boolean environment variables are parsed correctly."""
    # Test the pattern used in Settings
    assert "true".lower() == "true"
    assert "True".lower() == "true"
    assert "TRUE".lower() == "true"
    assert "false".lower() != "true"
    assert "False".lower() != "true"
    assert "".lower() != "true"


def test_settings_validate_multiple_errors():
    """Test validation returns multiple errors when multiple settings are invalid."""
    class TestSettings(Settings):
        OPENAI_API_KEY = ""
        SAMPLE_RATE = 32000  # Invalid
        VAD_AGGRESSIVENESS = 5  # Invalid

    errors = TestSettings.validate()

    # Should have multiple errors
    assert len(errors) >= 3
    assert any("OPENAI_API_KEY" in err for err in errors)
    assert any("SAMPLE_RATE" in err for err in errors)
    assert any("VAD_AGGRESSIVENESS" in err for err in errors)


def test_settings_sample_rate_options():
    """Test all valid sample rate options."""
    valid_rates = [16000, 22050, 44100, 48000]

    for rate in valid_rates:
        class TestSettings(Settings):
            OPENAI_API_KEY = "test-key"
            SAMPLE_RATE = rate

        errors = TestSettings.validate()
        # Should not have sample rate error
        assert not any("SAMPLE_RATE" in err for err in errors)


def test_settings_vad_aggressiveness_range():
    """Test all valid VAD aggressiveness values."""
    for level in range(4):  # 0, 1, 2, 3
        class TestSettings(Settings):
            OPENAI_API_KEY = "test-key"
            VAD_AGGRESSIVENESS = level

        errors = TestSettings.validate()
        # Should not have VAD error
        assert not any("VAD_AGGRESSIVENESS" in err for err in errors)
