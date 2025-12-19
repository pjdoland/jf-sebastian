"""
Configuration management for J.F. Sebastian AI system.
Loads settings from environment variables with sensible defaults.
"""

import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Central configuration class for all application settings."""

    # Personality Selection
    PERSONALITY: str = os.getenv("PERSONALITY", "johnny")  # 'johnny' or 'rich'

    # OpenAI API
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Wake Word Detection (OpenWakeWord)
    # Custom wake word models should be placed in the models/ directory
    # No API key required - OpenWakeWord is fully open source

    # Audio Configuration
    INPUT_DEVICE_NAME: Optional[str] = os.getenv("INPUT_DEVICE_NAME")
    OUTPUT_DEVICE_NAME: Optional[str] = os.getenv("OUTPUT_DEVICE_NAME")
    OUTPUT_DEVICE_TYPE: str = os.getenv("OUTPUT_DEVICE_TYPE", "teddy_ruxpin")
    SAMPLE_RATE: int = int(os.getenv("SAMPLE_RATE", "44100"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1024"))

    # Voice Activity Detection
    VAD_AGGRESSIVENESS: int = int(os.getenv("VAD_AGGRESSIVENESS", "3"))
    SILENCE_TIMEOUT: float = float(os.getenv("SILENCE_TIMEOUT", "10.0"))
    SPEECH_END_SILENCE_SECONDS: float = float(os.getenv("SPEECH_END_SILENCE_SECONDS", "1.5"))
    MIN_LISTEN_SECONDS: float = float(os.getenv("MIN_LISTEN_SECONDS", "1.0"))

    # Conversation Settings
    CONVERSATION_TIMEOUT: float = float(os.getenv("CONVERSATION_TIMEOUT", "120.0"))
    MAX_HISTORY_LENGTH: int = int(os.getenv("MAX_HISTORY_LENGTH", "20"))

    # OpenAI Models
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "whisper-1")
    GPT_MODEL: str = os.getenv("GPT_MODEL", "gpt-4o-mini")
    TTS_MODEL: str = os.getenv("TTS_MODEL", "tts-1")
    # Note: TTS_VOICE is now defined per-personality

    # Animatronic Control
    SENTIMENT_POSITIVE_THRESHOLD: float = float(os.getenv("SENTIMENT_POSITIVE_THRESHOLD", "0.3"))
    SENTIMENT_NEGATIVE_THRESHOLD: float = float(os.getenv("SENTIMENT_NEGATIVE_THRESHOLD", "-0.3"))
    VOICE_GAIN: float = float(os.getenv("VOICE_GAIN", "1.05"))  # Voice audio volume (0.0 to 2.0)
    CONTROL_GAIN: float = float(os.getenv("CONTROL_GAIN", "0.52"))  # Control track volume (0.0 to 1.0)

    # Wake Word Detection
    WAKE_WORD_THRESHOLD: float = float(os.getenv("WAKE_WORD_THRESHOLD", "0.99"))  # Detection threshold (0.0 to 1.0)

    # Debug Settings
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SAVE_DEBUG_AUDIO: bool = os.getenv("SAVE_DEBUG_AUDIO", "false").lower() == "true"
    DEBUG_AUDIO_PATH: Path = Path(os.getenv("DEBUG_AUDIO_PATH", "./debug_audio/"))
    PLAYBACK_PREROLL_MS: int = int(os.getenv("PLAYBACK_PREROLL_MS", "240"))

    # Note: System prompt is now defined per-personality

    @classmethod
    def validate(cls) -> list[str]:
        """
        Validate critical settings are present.
        Returns list of error messages, empty if all valid.
        """
        errors = []

        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required")

        if cls.SAMPLE_RATE not in [16000, 22050, 44100, 48000]:
            errors.append(f"Invalid SAMPLE_RATE: {cls.SAMPLE_RATE}. Must be 16000, 22050, 44100, or 48000")

        if not 0 <= cls.VAD_AGGRESSIVENESS <= 3:
            errors.append(f"VAD_AGGRESSIVENESS must be 0-3, got {cls.VAD_AGGRESSIVENESS}")

        # Validate device type
        from jf_sebastian.devices import DeviceRegistry
        available_devices = DeviceRegistry.list_devices()
        if cls.OUTPUT_DEVICE_TYPE.lower() not in available_devices:
            errors.append(
                f"Invalid OUTPUT_DEVICE_TYPE: '{cls.OUTPUT_DEVICE_TYPE}'. "
                f"Available devices: {', '.join(available_devices)}"
            )

        return errors

    @classmethod
    def create_debug_dirs(cls):
        """Create necessary directories for debug output."""
        if cls.SAVE_DEBUG_AUDIO:
            cls.DEBUG_AUDIO_PATH.mkdir(parents=True, exist_ok=True)


# Create singleton instance
settings = Settings()
