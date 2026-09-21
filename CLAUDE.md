# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

J.F. Sebastian is an AI-powered animatronic conversation system that brings vintage animatronic toys to life through real-time voice interactions. The system enables personality-driven conversations with ChatGPT through devices like the 1985 Teddy Ruxpin doll, featuring speech recognition, text-to-speech synthesis, and optional voice conversion.

**Critical Requirements:**
- Python 3.10.x specifically (RVC dependencies incompatible with 3.11+)
- macOS is the primary environment (audio device names in `.env.example` are Mac devices); Linux/Jetson is also supported (see `docs/JETSON_DEPLOYMENT.md`)
- OpenAI API key required for Whisper, the GPT chat model (`GPT_MODEL`), and TTS

## Essential Commands

### Setup and Installation
```bash
# Automated setup (recommended)
./setup.sh

# Manual virtual environment setup
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Install RVC (optional, requires Python 3.10)
./scripts/install_rvc.sh
# OR manually:
pip install pip==24.0
pip install -r requirements-rvc.txt
pip install --upgrade pip

# Download OpenWakeWord preprocessing models
python3 -c "from openwakeword import utils; utils.download_models(['alexa'])"

# List available audio devices
python -m jf_sebastian.modules.audio_output
```

### Running the Application
```bash
# Using convenience script
./run.sh

# Direct execution
python -m jf_sebastian.main

# Supervised (recommended for unattended deployments: auto-restart on crash,
# watchdog kill of hung children, crash reports to ./crash_reports/).
# See scripts/jf-sebastian.plist (macOS) and scripts/jf-sebastian.service (Linux)
# for the production install paths.
HEARTBEAT_FILE=/tmp/jf_sebastian.heartbeat python scripts/supervisor.py
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test markers (all five are registered in pytest.ini, but only
# `unit` is applied today, in the tool-provider, Hue, and conversation-tools
# tests; the other markers currently select nothing)
pytest -m unit        # Unit tests only
pytest -m integration # Integration tests
pytest -m audio       # Audio-related tests
pytest -m slow        # Long-running tests

# Run tests with verbose output
pytest -v tests/

# Test specific component
pytest tests/modules/test_state_machine.py
pytest tests/personalities/test_base.py
```

### Personality Management
```bash
# Generate filler audio for all personalities
python scripts/generate_fillers.py

# Generate for specific personality
python scripts/generate_fillers.py --personality johnny

# Test microphone
python scripts/test_microphone.py

# Benchmark RVC performance
python scripts/benchmark_rvc.py
```

## Architecture Overview

### Core State Machine
The system operates through a 4-state finite state machine:
```
IDLE ──wake word──> LISTENING ──speech end──> PROCESSING ──response ready──> SPEAKING
 ▲                      │                             │                          │
 └──timeout/silence────┘─────────────────────────────┴──────────────────────────┘
```

State transitions managed in `jf_sebastian/modules/state_machine.py` (StateMachine class, `VALID_TRANSITIONS`). Two edges are not shown above:
- IDLE → SPEAKING: a scheduled event, entered only via `try_transition(IDLE, SPEAKING)`
- SPEAKING → LISTENING: the normal end of a turn (trigger `continue_conversation`), which reopens the mic for a follow-up. SPEAKING → IDLE happens instead after a scheduled event, or when a tool set `suppress_followup` (trigger `playback_action`).

### Main Application Flow (TeddyRuxpinApp in main.py)
1. Initialize all modules (wake word detector, audio I/O, STT, LLM, TTS, device output)
2. Start in IDLE state with background wake word detection
3. On wake word: IDLE → LISTENING
4. On speech end (VAD detection): LISTENING → PROCESSING
5. Multi-stage audio validation (filters silence/noise before Whisper):
   - Length check → RMS amplitude check → VAD speech content analysis
   - Only if all checks pass: Select filler phrase → Call Whisper API
   - Transcript validation (hallucination detection as backup)
6. Parallel processing pipeline:
   - Whisper API transcribes speech (only if validation passed)
   - ConversationEngine injects real-world context (date/time, weather, news headlines) as transient system message
   - ConversationEngine streams GPT response with word-based chunking (MIN_CHUNK_WORDS=15)
   - TextToSpeech synthesizes each chunk to MP3
   - Output device (`create_output`) decodes it, optionally applies RVC, and creates stereo audio (LEFT=voice, RIGHT=PPM control for Teddy Ruxpin)
   - This whole pipeline runs on the recorder thread inside the `_on_speech_end` callback; only playback runs on a separate per-turn worker thread fed by a queue
7. AudioPlayer plays chunks: the playback worker performs PROCESSING → SPEAKING when it dequeues the first real (non-filler) chunk
8. On completion: SPEAKING → LISTENING (follow-up window), or SPEAKING → IDLE when the turn started music (`suppress_followup`)

### Key Module Responsibilities

**jf_sebastian/modules/**
- `state_machine.py`: StateMachine class managing conversation states. `try_transition(expected, target, trigger)` is the atomic CAS used by the scheduler to enter SPEAKING without racing the wake-word detector.
- `wake_word.py`: WakeWordDetector using OpenWakeWord with debouncing (2s minimum)
- `audio_input.py`: AudioRecorder with PyAudio and Silero VAD (512-sample frames). Runs one continuous recording session per conversation; `pause()`/`resume()` stop and restart the input stream around playback.
- `speech_to_text.py`: SpeechToText wrapping OpenAI Whisper API
- `conversation.py`: ConversationEngine managing the OpenAI chat model (`GPT_MODEL`; GPT-5 family models get `max_completion_tokens`, no custom temperature, and `GPT_REASONING_EFFORT`) with streaming, word-chunked responses, and real-world context injection. Holds a list of **tool providers** (Spotify, Hue); each contributes its `OPENAI_TOOLS` schemas and claims its own tool-name namespace via `handles(name)`. The engine concatenates the enabled schemas, accumulates streamed tool-call deltas, routes each call to the provider that claims it, and yields a templated spoken confirmation (no second LLM round-trip); `suppress_followup` signals main.py to go IDLE rather than re-listen over a music bed. Adding a provider means adding a module that subclasses `ToolProvider` (see `modules/tool_provider.py`) plus a constructor kwarg, with no changes to the streaming or dispatch logic. Tools are attached only on the streaming path; the non-streaming path (scheduled `prompt:` events) cannot call tools. The system prompt is pinned outside the `MAX_HISTORY_LENGTH` turn deque, so it is never evicted.
- `sentence_chunker.py`: `SentenceChunker`, the pure-text streaming chunker used by the engine. Emits groups of complete sentences totalling at least `MIN_CHUNK_WORDS`, is abbreviation-aware and decimal-safe, and has a soft cap (2x the minimum) that flushes at a clause comma so run-ons still stream.
- `tool_provider.py`: shared scaffolding every LLM tool provider builds on. Owns `ToolResult`/`ToolError` (the types the conversation engine reads), `tool_schema()` (the OpenAI function envelope), `fold()` (case/whitespace/curly-apostrophe normalization), `resolve_by_name()` (the exact → containment → fuzzy ladder over **ordered tiers**, where an ambiguous earlier tier is resolved within itself rather than falling through to a later one), and the `ToolProvider` base (namespace claim via `handles()`, plus a `dispatch()` that converts every failure, including a broken `handlers()`, into a `ToolResult` so nothing raises into a turn). A provider supplies `namespace`, `handlers()`, `error_hints`, and optionally `classify()`.
- `spotify_tool.py`: `SpotifyTool(ToolProvider)` (optional) wrapping the Spotify Web API via `spotipy` with PKCE auth. Exposes nine `music_*` tools to the LLM (`OPENAI_TOOLS`), resolves Connect speakers by name (alias map and configured default layered over the shared resolver, then the active device), and degrades every failure into a neutral spoken hint via an error taxonomy. Lazy, non-blocking init; minimal scopes locked by test.
- `hue_tool.py`: `HueTool(ToolProvider)` (optional) wrapping the Philips Hue Bridge **local** v1 API via `requests` (no cloud account, no extra dependency). Exposes six `lights_*` tools to the LLM (`OPENAI_TOOLS`), resolves targets by supplying rooms/zones as the first tier and bulbs as the second to the shared resolver (bare or "everything" → the all-lights group), and degrades every failure into a neutral spoken hint via an error taxonomy. Capability-aware across three bulb tiers (White & Colour; White Ambiance, which has colour temperature but no hue channel; and plain White): a request a bulb can't express returns `no-color` rather than a Bridge error, a mixed room colours only the bulbs that can, and an identical write across all members collapses to one group action. Scenes are per-room, so naming a single bulb is refused rather than silently restyling that bulb's whole room. Colour names match on **word boundaries** (so "ultraviolet" is rejected rather than matching `violet`). Inventory (names/ids/capabilities) is cached 60 s; on/off state never is. Paired once via `scripts/hue_pair.py`.
- `text_to_speech.py`: TextToSpeech wrapping OpenAI TTS with per-personality voice/speed/style
- `filler_phrases.py`: FillerPhraseManager for low-latency response playback
- `ppm_generator.py`: PPMGenerator for ~60Hz PPM control signals (16.6ms frames, 400µs pulses, 630-1590µs gaps that encode position)
- `rvc_processor.py`: RVCProcessor for optional voice conversion (conversions serialized by a lock; output at the RVC model's native rate, typically 48kHz)
- `audio_output.py`: AudioPlayer for stereo playback with device enumeration. Gapless per-turn playback session (`start_playback_session` / `write_session_chunk` / `end_playback_session`) plus single-shot `play_stereo`; resamples when the sound card's default rate differs.
- `scheduler.py`: `ProactiveScheduler` background thread that fires personality-defined events (greet at 7am, bedtime story at 9pm, holiday surprises) when state is IDLE. Tiny schedule syntax (`HH:MM`, `HH:MM weekdays`, `HH:MM YYYY-MM-DD`); per-personality `scheduled_events.yaml`; suppressed during quiet hours.

**jf_sebastian/devices/** (Modular Output Device Architecture)
- `base.py`: OutputDevice abstract base class defining the interface. Also defines the **optional visual seam**: `requires_visual` (default `False`) plus six no-op `visual_*` hooks (`visual_start`, `visual_step`, `visual_on_playback_start`, `visual_on_playback_end`, `visual_set_mode`, `visual_stop`). Audio-only devices inherit the no-ops and are unaffected; a device that drives an on-screen renderer overrides them.
- `factory.py`: DeviceRegistry providing plugin-style registration/creation
- `teddy_ruxpin.py`: TeddyRuxpinDevice generating stereo (LEFT=voice, RIGHT=PPM)
- `headless.py`: HeadlessDevice base class for simple stereo output (computer playback)
- `squawkers_mccaw.py`: SquawkersMcCawDevice thin subclass of HeadlessDevice
- `shared/audio_processor.py`: `AudioProcessor`: MP3→PCM conversion via FFmpeg, plus `apply_rvc_conversion()` and `warmup_rvc()` (lazily creates the RVCProcessor; falls back to raw TTS audio on failure)
- `shared/sentiment_analyzer.py`: VADER sentiment analysis for eye control
- `__init__.py`: imports the built-in devices explicitly (loud failures), then auto-discovers every other subpackage in `devices/` best-effort so drop-in device packages self-register via `@register_device` (a failed optional import logs a warning; the core fleet is unchanged)

**Drop-in device packages** (optional, not distributed with this repo)
- Devices are modular like personalities: clone or symlink an extra device package into `jf_sebastian/devices/<name>/` and it self-registers; nothing else changes. Private packages are kept out of the repo via `.git/info/exclude` (local-only ignores), so the public tree carries no trace of them.
- A visually-rendered device integrates through the IP-free **visual seam** in `base.py` (`requires_visual` + the `visual_*` hooks): `main.py` inverts its loop to pump `visual_step` (renderers own the main thread), and the playback worker publishes per-chunk timing via `visual_on_playback_start`. `VISUAL_ENABLED=false` (or a host with no display) falls back to audio-only.
- A drop-in device owns its settings in its own `config.py` (read from the environment; generic visual conventions use the `VISUAL_` prefix, device-specific tunables use a device prefix) and documents them in its own README. Per-device tuning lives in the bundle itself (`jf_sebastian/devices/<name>/.env`), loaded automatically when that device is selected.

**jf_sebastian/config/**
- `settings.py`: Central Settings class loading from `.env` (plus the layered overlays) with validation. Code defaults and `.env.example` differ for two models: `GPT_MODEL` defaults to `gpt-4o-mini` in code while `.env.example` sets `gpt-5.4-mini`; `TTS_MODEL` defaults to `tts-1` in code while `.env.example` sets `gpt-4o-mini-tts`.

**jf_sebastian/utils/**
- `audio_utils.py`: Audio utility functions including `calculate_rms()` for amplitude analysis, `contains_speech()` for VAD-based speech detection (fails open: returns True on error), and `save_stereo_wav()`
- `vad.py`: Silero VAD wrapper. `is_speech_window()` classifies one 512-sample window (live recorder path); `contains_speech()` measures the speech ratio of a whole buffer via `get_speech_timestamps`. Only 16 kHz (512 samples) and 8 kHz (256 samples) are supported.
- `gpu_utils.py`: `detect_gpu_device()` resolves `RVC_DEVICE=auto` to `cuda`, `mps`, or `cpu`
- `audio_device_utils.py`: `find_audio_device_by_name()` shared by the recorder, wake word detector, and player
- `async_file_utils.py`: `save_async()` hands debug-audio writes to one background writer thread with a bounded queue (16); overflow is dropped
- `context_provider.py`: Real-world context (date/time + weather + news headlines) for LLM conversations. Each subsystem has its own cache + provider singleton + lock + refresh-in-flight flag; HTTP I/O outside the cache lock; one in-flight refresh per subsystem
- `weather.py`: Pluggable `WeatherProvider` ABC + three adapters (`WttrWeatherProvider`, `HomeAssistantWeatherProvider`, `ManualWeatherProvider`) selected via `WEATHER_PROVIDER` env var. HA URL validation rejects unparseable URLs and refuses plain HTTP to non-private hosts to protect the bearer token.
- `news.py`: Pluggable `NewsProvider` ABC + three adapters (`RssNewsProvider`, `HackerNewsProvider`, `ManualNewsProvider`) selected via `NEWS_PROVIDER` env var. RSS uses `feedparser` and defaults to NPR Topics: News if `NEWS_RSS_URL` is unset, so headlines are on out-of-the-box. Hacker News is excluded from auto-selection (tech-only; opt in explicitly).
- `heartbeat.py`: `Heartbeat` background thread that touches a file every N seconds plus a `heartbeat_age()` helper. The supervisor reads the file's mtime to detect hung children. Started by `TeddyRuxpinApp.__init__` only when `HEARTBEAT_FILE` is set; stopped early in `TeddyRuxpinApp.stop()` (right after the scheduler, before the audio teardown) so a hung shutdown surfaces to the supervisor. When `HEARTBEAT_FILE` is set, `main()` also skips `kill_existing_instances()` because the supervisor is the sole spawner.

**scripts/** (Operations)
- `supervisor.py`: Process supervisor wrapping `python -m jf_sebastian.main`. Exponential-backoff restart, watchdog-kills hung children via SIGTERM/SIGKILL on the child's process group (`start_new_session=True` + `os.killpg`), writes enriched crash reports to `CRASH_REPORT_DIR`, prunes old reports, switches to long permanent-failure backoff after N consecutive crashes (`PERMANENT_FAILURE_THRESHOLD`). The watchdog is not enforced during `FIRST_HEARTBEAT_GRACE` (default 60 s), and a clean child exit (code 0) is not restarted.
- `jf-sebastian.plist`: launchd agent template for macOS. `KeepAlive` restarts the supervisor itself on crash; `LimitLoadToSessionType=Aqua` ensures the audio session is available.
- `jf-sebastian.service`: systemd user-unit template for Linux. `Restart=on-failure` + `StartLimitBurst=5` is the safety net for the supervisor process; `pipewire-pulse.service` dependency for audio.

### Device Architecture Pattern
The system uses a **plugin-style device registry** allowing easy addition of new output devices:
- Inherit from `OutputDevice` abstract base class
- Implement the abstract members: `device_name`, `requires_ppm`, `create_output()`, `get_output_channels()` (optionally `validate_settings()`)
- Register with `@register_device('device_name')` decorator
- Device-specific processing automatically applied (PPM generation for Teddy, simple stereo for others)

### Personality System
Zero-code personality definition via YAML files in `personalities/` directory:
- Each personality is a folder with `personality.yaml`
- No Python code changes needed to add new characters
- Per-personality configuration:
  - Wake word models (ONNX files)
  - TTS voice, speed, style instructions
  - System prompt for LLM personality
  - Filler phrases for low-latency feel
  - Optional RVC voice conversion models (`*.pth`, `*.index`)
  - Optional `scheduled_events.yaml` for proactive utterances (see `personalities/johnny/scheduled_events.yaml` for the working example)
  - Optional `spotify_enabled` / `hue_enabled` (both default `true`, so a personality opts out rather than in; they only matter when `SPOTIFY_ENABLED` / `HUE_ENABLED` is on globally)
- Required `personality.yaml` fields: `name`, `tts_voice`, `wake_word_model`, `system_prompt`, `filler_phrases`
- Filler audio stored in device-specific subdirectories: `filler_audio/teddy_ruxpin/`, `filler_audio/squawkers_mccaw/`, `filler_audio/headless/`

**Available personalities:** fred, jarvis, johnny, kitt, leopold, mr_lincoln, teddy_ruxpin

### Streaming Response Pipeline
Advanced **word-based sentence chunking** for parallel processing:
1. LLM streams response as tokens
2. Chunks accumulate to MIN_CHUNK_WORDS (default: 15)
3. Each complete sentence chunk triggers TTS immediately
4. TTS output optionally passes through RVC inside the device's `create_output()`
5. The device builds the stereo output for that chunk (PPM control track for Teddy Ruxpin)
6. Chunks are queued for the playback worker; chunk N+1 is produced while chunk N plays
7. Results in nearly-instant perceived response despite backend processing

### Proactive Scheduler
Personalities can define proactive utterances in `personalities/<name>/scheduled_events.yaml`:
- Schedule syntax: `"HH:MM"`, `"HH:MM weekdays|weekends|mon,wed"`, `"HH:MM YYYY-MM-DD"`
- Each event has either `say:` (verbatim TTS, fast) or `prompt:` (LLM-generated in character)
- Events fire only when state is IDLE and never interrupt a conversation. An event that finds the system busy is dropped, not retried.
- Scheduler thread ticks every 30 s at minute granularity; events run serially on that thread via the non-streaming LLM path
- `try_transition(IDLE, SPEAKING)` is an atomic CAS that closes the TOCTOU window with the wake-word detector
- Quiet hours suppress events whose scheduled minute falls in the window; warned at load time
- Globally toggle with `SCHEDULER_ENABLED`; `QUIET_HOURS_START`/`QUIET_HOURS_END` env vars override the YAML atomically

### PPM Control Signal Generation
Precise ~60Hz PPM (Pulse Position Modulation) for animatronic motor control:
- Sample rate: 44.1kHz for precise timing
- Frame period: 16.6ms (~60Hz)
- 8 channel slots per frame; each is a 400µs negative pulse (-30% amplitude) followed by a 630-1590µs gap whose length encodes the 0-255 position
- Channel numbers are the zero-based column indices in `ppm_generator.py`: channel 1 = eyes (sentiment-based, inverted command), channel 2 = upper jaw (70% of lower), channel 3 = lower jaw (syllable-based lip sync); channels 0 and 4-7 are unused
- Control track is low-pass filtered at 5kHz and scaled by `CONTROL_GAIN`
- Output: RIGHT channel contains PPM pulses, LEFT channel contains voice

## Critical Implementation Details

### Audio Processing
- All audio operations use 16kHz sample rate by default (configurable: 16000, 22050, 44100, 48000)
- Stereo WAV format for all output
- LEFT channel: Voice audio
- RIGHT channel: PPM control signals (Teddy Ruxpin only)
- FFmpeg required for MP3→PCM conversion

### Multi-Stage Silence Detection
The system uses a **defense-in-depth approach** to filter out silence and background noise before processing, preventing unnecessary Whisper API calls and avoiding hallucinations (false transcriptions like "Thank you", "Goodbye", etc.):

**Stage 1: Audio Length Check** (`main.py:_on_speech_end`)
- Validates minimum audio duration (MIN_LISTEN_SECONDS * 16000 * 2 bytes; the 16 kHz rate is hardcoded here)
- Filters recordings that ended too quickly (likely timeouts)
- Returns to IDLE if audio too short

**Stage 2: RMS Amplitude Check** (`main.py:_on_speech_end` → `utils/audio_utils.py:calculate_rms`)
- Analyzes peak RMS (Root Mean Square) amplitude using 100ms sliding windows (50% overlap)
- Detects if ANY portion of the audio has sufficient volume
- Configurable threshold: `MIN_AUDIO_RMS` (default: 60, typical speech: 1500-5000)
- Filters: Pure silence, very quiet audio
- Returns to IDLE if RMS below threshold

**Stage 3: VAD Speech Content Analysis** (`main.py:_on_speech_end` → `utils/audio_utils.py:contains_speech` → `utils/vad.py`)
- Runs Silero VAD segmentation (`get_speech_timestamps`) over the whole buffer
- Calculates the ratio of speech duration to total duration
- Configurable threshold: `MIN_SPEECH_RATIO` (default: 0.3 = 30% of the audio must be speech)
- Filters: Background noise, music, rustling, humming - anything with volume but no speech
- Returns to IDLE if speech ratio below threshold
- This is the **primary defense** against Whisper hallucinations

**Stage 4: Whisper Hallucination Detection** (`main.py:_process_and_speak`)
- After transcription, checks transcript against known Whisper hallucination phrases
- Common hallucinations: "Thank you", "Goodbye", "Bye", "Thanks for watching", etc.
- Also validates transcript isn't too short or just punctuation
- Returns to IDLE if hallucination detected
- This is a **backup safety net** for edge cases that slip through VAD

**Execution Order:**
1. Stages 1-3 run **before** selecting filler phrase
2. Stages 1-3 run **before** calling Whisper API (saves API quota)
3. Only if all stages pass: filler phrase selected, then filler playback and the Whisper call **kick off in parallel** (the filler covers transcribe + GPT + TTS latency)
4. Stage 4 validates the **returned transcript**. Because the filler is already playing by then, Stage 4 no longer prevents a filler from playing on a hallucination; it stops the hallucinated text from reaching GPT/TTS and returns to IDLE

**Benefits:**
- Eliminates 95%+ of false Whisper API calls
- Prevents filler phrases from playing on silence/noise
- Saves API costs by filtering before transcription
- Multi-layered validation ensures robustness

**Tuning Guide:**
- Increase `MIN_AUDIO_RMS` if transcribing too much quiet noise (typical speech: 1500-5000)
- Increase `MIN_SPEECH_RATIO` (0.4-0.5) if still getting hallucinations
- Decrease `MIN_SPEECH_RATIO` (0.2-0.25) if valid speech being rejected
- Use `VAD_THRESHOLD` (0.0-1.0, default 0.5) to control Silero sensitivity (higher = stricter)

### RVC Voice Conversion
- Optional feature requiring Python 3.10.x specifically
- Warmup performed on startup to eliminate first-use delay; also re-warmed before each scheduled event so idle-period cold starts don't stall the first chunk
- Conversion is attempted up to 3 times with backoff (0.5 s, then 1.5 s) on transient CUDA allocator failures (relevant on memory-constrained Jetson devices)
- `VOICE_GAIN` is applied to RVC-converted audio in addition to the raw TTS path
- The RVCProcessor is created lazily by `AudioProcessor` on first use; if RVC is unavailable or a conversion fails, the raw TTS audio is used
- Per-personality enable/disable in `personality.yaml`. `rvc_enabled` is tri-state: `true`, `false` (authoritative), or omitted (auto: on if a model resolves from `rvc_model` or the `<dirname>.pth` convention). `RVC_ENABLED=false` disables RVC globally.
- Core RVC settings: `rvc_enabled`, `rvc_model`, `rvc_index_file`, `rvc_pitch_shift`
- Per-personality tuning knobs (see `personalities/jarvis/personality.yaml` for a fully-tuned example): `rvc_index_rate`, `rvc_f0_method` (`pm` is fast, `rmvpe` is higher quality), `rvc_filter_radius`, `rvc_rms_mix_rate`, `rvc_protect`

### Low-Latency Filler System
Pre-generated personality-specific audio fills the response gap:
1. User speaks; VAD detects speech end
2. Audio passes Stages 1-3 validation (length, RMS, speech ratio)
3. Filler playback and Whisper transcription kick off **in parallel** (filler is no longer gated on the Whisper response), so the filler covers the full transcribe + GPT + TTS latency
4. GPT response streams back in word-based chunks while the filler is still playing; TTS (and optional RVC) generates each chunk
5. Real response seamlessly transitions from filler as soon as the first chunk's audio is ready
6. Filler files are only catalogued at startup; the selected file is decoded from disk on demand, which keeps startup fast
7. Creates perceived instant response despite 4-6s actual processing

### Configuration Management
- Environment-based configuration via `.env` file
- Settings class in `jf_sebastian/config/settings.py` loads with validation
- Most tunables are configurable; a few constants are hardcoded in modules (wake word debounce, scheduler tick, cache TTL for weather, tool timeouts)
- Per-personality settings in `personalities/{name}/personality.yaml`
- **Layered env overlays** (highest precedence first): `personalities/{PERSONALITY}/.env` → `jf_sebastian/devices/{OUTPUT_DEVICE_TYPE}/.env` → `.env`. Loaded once at import in `config/settings.py`; loaded overlay paths are exposed as `settings.LOADED_ENV_OVERLAYS` and logged at startup. Overlay files are `.gitignore`-d by the existing `.env` rule. Don't put `PERSONALITY` or `OUTPUT_DEVICE_TYPE` inside an overlay; they're the selection keys.
- Weather context uses a pluggable provider selected by `WEATHER_PROVIDER` (`wttr`, `homeassistant`, `manual`, `none`, or `auto`/unset). Auto-selection picks the first configured provider in order: `homeassistant > wttr > manual`. Existing `ZIPCODE`-only setups keep working unchanged. Cached 30 minutes; failed fetches negative-cache for 60s.

## File Locations and Conventions

### Important Paths
- Main entry: `jf_sebastian/main.py`
- Configuration: `.env` (created from `.env.example`)
- Personalities: `personalities/{name}/personality.yaml`
- Wake word models: `personalities/{name}/*.onnx`
- Filler audio: `personalities/{name}/filler_audio/{device_type}/filler_*.wav`
- RVC models: `personalities/{name}/*.pth` and `*.index`
- Tests: `tests/` (mirrors `jf_sebastian/` structure)
- Debug audio: `debug_audio/` (when SAVE_DEBUG_AUDIO=true)

### Testing Structure
- `tests/conftest.py`: Test fixtures and configuration
- `tests/config/`: Settings and configuration tests
- `tests/modules/`: Core module tests (state machine, PPM, sentiment, etc.)
- `tests/devices/`: Device factory and implementation tests
- `tests/personalities/`: Personality loading and validation tests
- `tests/utils/`: Context provider, weather, news, heartbeat, and file/device utility tests
- `tests/scripts/`: Supervisor unit and integration tests
- `tests/test_resiliency_fixes.py`: Regression tests for resiliency fixes
- Test markers: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.unit`, `@pytest.mark.audio`, `@pytest.mark.hardware`

## Development Guidelines

### Adding New Personalities
1. Create folder in `personalities/{name}/`
2. Create `personality.yaml` with required fields (see docs/CREATING_PERSONALITIES.md)
3. Train wake word model using OpenWakeWord (see docs/TRAIN_WAKE_WORDS.md)
4. Place `hey_{name}.onnx` in personality folder
5. Optional: Add RVC models (`{name}.pth`, `{name}.index`)
6. Generate filler audio: `python scripts/generate_fillers.py --personality {name}`
7. Set in `.env`: `PERSONALITY={name}`

### Adding New Output Devices
1. Create new file in `jf_sebastian/devices/{device_name}.py`
2. Inherit from `OutputDevice` base class
3. Implement `create_output(voice_audio_mp3: bytes, response_text: str, personality: Optional[Personality] = None) -> Optional[Tuple[np.ndarray, int]]` (returns `(audio_array, sample_rate)`, or `None` on error) plus the `device_name` / `requires_ppm` properties and `get_output_channels()`
4. Register with `@register_device('device_name')` decorator
5. Device automatically available in `OUTPUT_DEVICE_TYPE` setting (any module or subpackage in `devices/` is imported at startup)

### Modifying Audio Pipeline
- Audio input: Modify `jf_sebastian/modules/audio_input.py` (AudioRecorder class)
- VAD settings: Adjust in `.env` (VAD_THRESHOLD, SPEECH_END_SILENCE_SECONDS)
- PPM generation: Modify `jf_sebastian/modules/ppm_generator.py` (PPMGenerator class)
- Lip sync: Adjust syllable detection in PPMGenerator
- Eye control: Modify the sentiment-to-eye mapping in `PPMGenerator.audio_to_channel_values()` (base 0.9, `sentiment * 0.03`, blink logic); `sentiment_analyzer.py` only returns the VADER compound score. `SENTIMENT_POSITIVE_THRESHOLD` / `SENTIMENT_NEGATIVE_THRESHOLD` are defined in settings but not currently read by any module.

### Common Gotchas
- Python 3.10.x specifically required for RVC (not 3.11+)
- OpenWakeWord preprocessing models must be downloaded separately
- PortAudio and FFmpeg system dependencies required
- RVC installation requires pip downgrade to 24.0, then upgrade back
- Filler audio must be regenerated when personality settings change
- Wake word debouncing is 2 seconds minimum (hardcoded in wake_word.py)
- `SILENCE_TIMEOUT` (default 5.0 s) is a cap on each listening window measured from when the window opens, not a pure silence timer
- `SAMPLE_RATE` must be 16000 in practice: Silero VAD only supports 16 kHz (or 8 kHz). The validator still accepts 22050/44100/48000 but VAD silently rejects those windows with a warning in the log.

### Performance Optimization
- RVC warmup on startup eliminates first-use delay
- Lazy import of openwakeword (heavy ML library)
- Streaming response chunking enables parallel processing
- Async file I/O for audio saves
- Word-based sentence chunking (MIN_CHUNK_WORDS) balances latency vs. naturalness

## Debugging

### Enable Debug Mode
Set in `.env`:
```bash
DEBUG_MODE=true
SAVE_DEBUG_AUDIO=true
DEBUG_AUDIO_PATH=./debug_audio/
LOG_LEVEL=DEBUG
```

### Debug Audio Analysis
1. Saved files: `debug_audio/input_YYYYMMDD_HHMMSS.wav` and `output_YYYYMMDD_HHMMSS.wav`
2. Open in Audacity and split stereo to mono
3. LEFT channel: Voice audio
4. RIGHT channel: PPM control signal (should show regular 60Hz negative pulses)

### Common Issues
- **Wake word not detecting**: Check microphone selection, speak louder/clearer, verify wake word model exists
- **No audio output**: Run device enumeration, verify Bluetooth connection, check device name in `.env`
- **Teddy not moving**: Verify stereo output, check PPM signals in debug audio, test motor batteries
- **API errors**: Verify OpenAI API key, check credits, review `jf_sebastian.log`
- **Latency**: Use faster models (tts-1 not tts-1-hd), reduce MAX_HISTORY_LENGTH, check internet speed

## Reference Documentation

- `docs/ARCHITECTURE.md`: Detailed system design and component specifications
- `docs/CREATING_PERSONALITIES.md`: Step-by-step guide for adding personalities
- `docs/QUICKSTART.md`: 5-minute getting started guide
- `docs/TRAIN_WAKE_WORDS.md`: Custom wake word training instructions
- `docs/JETSON_DEPLOYMENT.md`: Jetson Orin Nano deployment notes (system packages, power tuning, mic AGC, AEC rationale)
- `docs/SPOTIFY_SETUP.md`: Spotify playback control setup (app registration, PKCE auth, speaker naming)
- `docs/HUE_SETUP.md`: Philips Hue light control setup (Bridge pairing, target resolution, colour/capability rules)
- `personalities/README.md`: Technical personality system reference
