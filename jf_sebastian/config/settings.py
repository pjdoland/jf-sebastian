"""
Configuration management for J.F. Sebastian AI system.
Loads settings from environment variables with sensible defaults.

Layered configuration (highest precedence wins):
  1. Personality:  personalities/{PERSONALITY}/.env
  2. Device:       jf_sebastian/devices/{OUTPUT_DEVICE_TYPE}/.env
  3. Base:         .env

PERSONALITY and OUTPUT_DEVICE_TYPE are read from base (.env) or the
process environment to select which overlay files to load; do not set
them inside overlay files.
"""

import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
LOADED_ENV_OVERLAYS: list[str] = []  # repo-relative paths for logging

load_dotenv()


def _apply_overlay(path: Path) -> None:
    if path.exists():
        load_dotenv(path, override=True)
        LOADED_ENV_OVERLAYS.append(str(path.relative_to(_REPO_ROOT)))


_device = os.getenv("OUTPUT_DEVICE_TYPE")
if _device:
    # Derived from this package's location so the path follows the code, not
    # an assumed repo layout.
    _apply_overlay(Path(__file__).resolve().parents[1] / "devices" / _device / ".env")

_personality = os.getenv("PERSONALITY")
if _personality:
    _apply_overlay(_REPO_ROOT / "personalities" / _personality / ".env")


class Settings:
    """Central configuration class for all application settings."""

    # Override files (device, personality) that were applied on top of the
    # base .env. Populated at module import; exposed via the Settings instance
    # for logging at startup. See module docstring for layering rules.
    LOADED_ENV_OVERLAYS: list[str] = LOADED_ENV_OVERLAYS

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

    # Voice Activity Detection (Silero). Probability above which a 32 ms
    # window is classified as speech (0.0 = call everything speech,
    # 1.0 = call nothing speech). 0.5 is balanced; raise toward 0.7 if
    # noise is leaking through, lower toward 0.3 if real speech is rejected.
    VAD_THRESHOLD: float = float(os.getenv("VAD_THRESHOLD", "0.5"))
    SILENCE_TIMEOUT: float = float(os.getenv("SILENCE_TIMEOUT", "10.0"))
    SPEECH_END_SILENCE_SECONDS: float = float(os.getenv("SPEECH_END_SILENCE_SECONDS", "1.5"))
    MIN_LISTEN_SECONDS: float = float(os.getenv("MIN_LISTEN_SECONDS", "1.0"))
    MIN_AUDIO_RMS: float = float(os.getenv("MIN_AUDIO_RMS", "60"))  # Minimum peak RMS amplitude to transcribe (filters silence)
    MIN_SPEECH_RATIO: float = float(os.getenv("MIN_SPEECH_RATIO", "0.3"))  # Minimum ratio of speech frames (0.0-1.0, default 30%)

    # Location & Weather (for real-world context in conversations)
    # WEATHER_PROVIDER: "wttr", "homeassistant", "manual", "none", or unset/"auto"
    # Unset/"auto" picks the first configured provider; existing ZIPCODE-only
    # setups keep working unchanged via the wttr fallback.
    WEATHER_PROVIDER: Optional[str] = os.getenv("WEATHER_PROVIDER")
    ZIPCODE: Optional[str] = os.getenv("ZIPCODE")
    HOME_ASSISTANT_URL: Optional[str] = os.getenv("HOME_ASSISTANT_URL")
    HOME_ASSISTANT_TOKEN: Optional[str] = os.getenv("HOME_ASSISTANT_TOKEN")
    HOME_ASSISTANT_WEATHER_ENTITY: Optional[str] = os.getenv("HOME_ASSISTANT_WEATHER_ENTITY")
    MANUAL_WEATHER: Optional[str] = os.getenv("MANUAL_WEATHER")

    # News headlines (in LLM context). NEWS_PROVIDER unset auto-selects rss
    # with the NPR default feed, so headlines are on out-of-the-box.
    # Set NEWS_PROVIDER=none to disable.
    NEWS_PROVIDER: Optional[str] = os.getenv("NEWS_PROVIDER")
    NEWS_RSS_URL: Optional[str] = os.getenv("NEWS_RSS_URL")
    MANUAL_NEWS: Optional[str] = os.getenv("MANUAL_NEWS")
    NEWS_HEADLINE_LIMIT: int = int(os.getenv("NEWS_HEADLINE_LIMIT", "5"))
    NEWS_CACHE_TTL_MINUTES: int = int(os.getenv("NEWS_CACHE_TTL_MINUTES", "30"))

    # Spotify playback control (optional). Only active when SPOTIFY_ENABLED=true AND
    # the personality sets spotify_enabled: true. PKCE auth -> no client secret on
    # device. The token cache is a private credential: keep it outside any synced
    # bundle (default ~/.config). See docs/SPOTIFY_SETUP.md.
    SPOTIFY_ENABLED: bool = os.getenv("SPOTIFY_ENABLED", "false").lower() == "true"
    SPOTIFY_CLIENT_ID: Optional[str] = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    SPOTIFY_TOKEN_CACHE: str = os.getenv(
        "SPOTIFY_TOKEN_CACHE", os.path.expanduser("~/.config/jf-sebastian/spotify-token.json"))
    SPOTIFY_DEFAULT_DEVICE: Optional[str] = os.getenv("SPOTIFY_DEFAULT_DEVICE")  # speaker for unspecified 'play'
    SPOTIFY_DEVICE_ALIASES: Optional[str] = os.getenv("SPOTIFY_DEVICE_ALIASES")  # "kitchen=Kitchen Echo,den=Living Room"
    # Inject the currently-playing track into the LLM context each turn so the
    # personality can answer questions about it. Cached + refreshed in the
    # background (non-blocking). Only active when Spotify is enabled.
    SPOTIFY_NOW_PLAYING_CONTEXT: bool = os.getenv("SPOTIFY_NOW_PLAYING_CONTEXT", "true").lower() == "true"

    # Proactive scheduler (per-personality scheduled_events.yaml)
    SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    # Global quiet hours override (HH:MM); empty = let the personality YAML decide.
    QUIET_HOURS_START: Optional[str] = os.getenv("QUIET_HOURS_START")
    QUIET_HOURS_END: Optional[str] = os.getenv("QUIET_HOURS_END")

    # Conversation Settings
    CONVERSATION_TIMEOUT: float = float(os.getenv("CONVERSATION_TIMEOUT", "120.0"))
    MAX_HISTORY_LENGTH: int = int(os.getenv("MAX_HISTORY_LENGTH", "20"))
    MIN_CHUNK_WORDS: int = int(os.getenv("MIN_CHUNK_WORDS", "15"))
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "300"))
    MAX_TOKENS_STREAMING: int = int(os.getenv("MAX_TOKENS_STREAMING", "200"))
    ENABLE_FILLER_AUDIO: bool = os.getenv("ENABLE_FILLER_AUDIO", "true").lower() == "true"

    # OpenAI Models
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "whisper-1")
    GPT_MODEL: str = os.getenv("GPT_MODEL", "gpt-4o-mini")
    TTS_MODEL: str = os.getenv("TTS_MODEL", "tts-1")
    # reasoning_effort for the GPT-5 family (e.g. low/medium/high). Defaults to
    # 'low' for snappy real-time replies. Set it empty to omit the parameter and
    # use the model's own default. Ignored for GPT-4 models (no reasoning param).
    GPT_REASONING_EFFORT: Optional[str] = (os.getenv("GPT_REASONING_EFFORT", "low") or "").strip() or None
    # Note: TTS_VOICE is now defined per-personality

    # Animatronic Control
    SENTIMENT_POSITIVE_THRESHOLD: float = float(os.getenv("SENTIMENT_POSITIVE_THRESHOLD", "0.3"))
    SENTIMENT_NEGATIVE_THRESHOLD: float = float(os.getenv("SENTIMENT_NEGATIVE_THRESHOLD", "-0.3"))
    VOICE_GAIN: float = float(os.getenv("VOICE_GAIN", "1.05"))  # Voice audio volume (0.0 to 2.0)
    CONTROL_GAIN: float = float(os.getenv("CONTROL_GAIN", "0.52"))  # Control track volume (0.0 to 1.0)

    # Wake Word Detection
    WAKE_WORD_THRESHOLD: float = float(os.getenv("WAKE_WORD_THRESHOLD", "0.99"))  # Detection threshold (0.0 to 1.0)

    # RVC Voice Conversion (optional - per personality)
    RVC_ENABLED: bool = os.getenv("RVC_ENABLED", "true").lower() == "true"  # Global override to disable RVC
    RVC_DEVICE: str = os.getenv("RVC_DEVICE", "auto")  # Device for RVC inference (auto/cpu/mps/cuda)
    RVC_MODEL_DIR: Path = Path(os.getenv("RVC_MODEL_DIR", "./rvc_models/"))  # Global RVC model directory

    # Supervisor / Heartbeat (used by scripts/supervisor.py)
    # Set HEARTBEAT_FILE to opt in to liveness reporting; otherwise no-op.
    HEARTBEAT_FILE: Optional[Path] = (
        Path(os.environ["HEARTBEAT_FILE"]) if os.environ.get("HEARTBEAT_FILE") else None
    )
    HEARTBEAT_INTERVAL: float = float(os.getenv("HEARTBEAT_INTERVAL", "10.0"))

    # Debug Settings
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SAVE_DEBUG_AUDIO: bool = os.getenv("SAVE_DEBUG_AUDIO", "false").lower() == "true"
    DEBUG_AUDIO_PATH: Path = Path(os.getenv("DEBUG_AUDIO_PATH", "./debug_audio/"))
    PLAYBACK_PREROLL_MS: int = int(os.getenv("PLAYBACK_PREROLL_MS", "240"))
    # Wait this long after the audio stream closes before re-opening the
    # microphone for the next turn. Covers speaker buffer drain and acoustic
    # decay so the bot doesn't capture its own tail audio as the user's input.
    PLAYBACK_TAIL_GUARD_MS: int = int(os.getenv("PLAYBACK_TAIL_GUARD_MS", "500"))

    # Note: settings consumed by exactly one device live in that device's own
    # package (devices/<name>/config.py), not here. The layered .env overlays
    # (jf_sebastian/devices/<name>/.env) are applied to the environment before any
    # device package loads, so device configs read them transparently.

    # Note: System prompt is now defined per-personality

    @classmethod
    def resolve_rvc_device(cls):
        """Resolve RVC_DEVICE='auto' to the best available GPU device."""
        if cls.RVC_DEVICE == "auto":
            from jf_sebastian.utils.gpu_utils import detect_gpu_device
            cls.RVC_DEVICE = detect_gpu_device()

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

        if not 0.0 <= cls.VAD_THRESHOLD <= 1.0:
            errors.append(f"VAD_THRESHOLD must be 0.0-1.0, got {cls.VAD_THRESHOLD}")

        # Validate device type
        from jf_sebastian.devices import DeviceRegistry
        available_devices = DeviceRegistry.list_devices()
        if cls.OUTPUT_DEVICE_TYPE.lower() not in available_devices:
            errors.append(
                f"Invalid OUTPUT_DEVICE_TYPE: '{cls.OUTPUT_DEVICE_TYPE}'. "
                f"Available devices: {', '.join(available_devices)}"
            )

        # Validate weather provider name (if explicitly set)
        if cls.WEATHER_PROVIDER:
            from jf_sebastian.utils.weather import VALID_PROVIDER_NAMES
            valid = VALID_PROVIDER_NAMES | {"none", "auto"}
            if cls.WEATHER_PROVIDER.lower() not in valid:
                errors.append(
                    f"Invalid WEATHER_PROVIDER: '{cls.WEATHER_PROVIDER}'. "
                    f"Valid values: {', '.join(sorted(valid))}"
                )

        # Validate news provider name (if explicitly set)
        if cls.NEWS_PROVIDER:
            from jf_sebastian.utils.news import VALID_PROVIDER_NAMES as NEWS_VALID
            valid = NEWS_VALID | {"none", "auto"}
            if cls.NEWS_PROVIDER.lower() not in valid:
                errors.append(
                    f"Invalid NEWS_PROVIDER: '{cls.NEWS_PROVIDER}'. "
                    f"Valid values: {', '.join(sorted(valid))}"
                )

        # Spotify: if enabled, a client id is required (don't silently no-op).
        if cls.SPOTIFY_ENABLED and not (cls.SPOTIFY_CLIENT_ID or "").strip():
            errors.append("SPOTIFY_ENABLED=true but SPOTIFY_CLIENT_ID is not set (see docs/SPOTIFY_SETUP.md)")

        return errors

    @classmethod
    def create_debug_dirs(cls):
        """Create necessary directories for debug output."""
        if cls.SAVE_DEBUG_AUDIO:
            cls.DEBUG_AUDIO_PATH.mkdir(parents=True, exist_ok=True)


# Create singleton instance
settings = Settings()
