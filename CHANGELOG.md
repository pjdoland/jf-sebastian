# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.8.0] - 2026-09-20

### Added
- **Philips Hue light control** (optional, off by default). A personality can
  turn lights on and off, set brightness and colour, and activate stored scenes
  by voice. Talks to the Hue Bridge's local v1 API over the LAN via `requests`
  (no cloud account, no new dependency), so Alexa and the Hue app keep working
  alongside it. Six `lights_*` tools; see `docs/HUE_SETUP.md`.
- `scripts/hue_pair.py` for one-time Bridge pairing. Discovers the Bridge,
  handles the link-button handshake, caches the credential `0600` outside the
  repo, and prints an inventory of rooms, zones, lights and scenes.
- Capability-aware colour across Hue's three bulb tiers: full-colour bulbs take
  everything, White Ambiance bulbs keep their colour temperatures despite having
  no hue channel, and plain White bulbs report that they cannot change colour
  rather than erroring. A mixed room applies to only the bulbs that can.
- `jf_sebastian/modules/tool_provider.py`, the shared base every LLM tool
  provider builds on: `ToolResult`/`ToolError`, the OpenAI function-schema
  envelope, name normalization, the tiered name-resolution ladder, and a
  dispatch that converts any failure into a spoken hint rather than an
  exception in the conversation turn.
- `CHANGELOG.md`, linked from the README.

### Changed
- The conversation engine holds a **list** of tool providers instead of a single
  hardcoded Spotify tool. Each contributes its own schemas and claims a
  tool-name namespace; dispatch routes by name. Adding a provider is a
  `ToolProvider` subclass plus one constructor keyword argument.
- Spotify and Hue share one name resolver, which takes ordered tiers: Spotify
  passes one (Connect speakers), Hue passes two (rooms and zones, then bulbs).
  Spotify keeps its alias map, configured default and active-device fallback
  layered around it. `hue_tool.py` shrank by a net 67 lines and
  `spotify_tool.py` by 59.
- `.gitignore` now guards `hue.json`, matching the existing Spotify token guard,
  in case `HUE_TOKEN_CACHE` is pointed into the repo.

### Fixed
Reverse-substring matching, empty-name candidates and schema aliasing were
present in the Spotify tool as released in 2.7.0. The other items were caught
while the Hue provider was being built and never shipped in a release.
- A tool provider missing a contract method raised inside the streaming loop and
  aborted the **entire** conversation response rather than losing just its own
  tool call. The contract is validated once at construction, and a provider that
  fails validation never advertises its schemas.
- Name resolution matched a stored name inside a longer spoken phrase as a raw
  substring, so a short name swallowed unrelated requests: a zone called "Up"
  answered "the cupboard light". Reverse matching now requires word boundaries.
- A room or device whose name normalized to empty was contained in every target
  and answered every non-exact request.
- An ambiguous earlier tier fell through to a later one, so in a house with
  several bedrooms "bedroom" could be answered by a lamp instead of a room.
- Colour names matched as substrings, so "ultraviolet" silently resolved to
  violet.
- Scenes could be applied to a group they were not stored for, and naming a
  single bulb applied a scene to that bulb's whole room while reporting only the
  bulb. Both are now refused explicitly.
- The OpenAI schema helper shallow-copied its properties, so every schema built
  from a shared property constant aliased the same nested dictionaries.

### Configuration
New optional variables; no breaking changes.
```bash
HUE_ENABLED=true                  # global gate for the light tools
HUE_TOKEN_CACHE=~/.config/jf-sebastian/hue.json   # default; a credential, kept 0600
HUE_BRIDGE_HOST=192.168.1.42      # optional; overrides the paired-at address
```
Per-personality: `hue_enabled: false` excludes a character (default `true`).
An unpaired Bridge is a startup warning, not an error, so a missing light
credential cannot block unrelated work such as filler generation.

## [2.7.0] - 2026-06-22

### Added
- **Spotify voice control**: nine `music_*` tools (play, pause, resume, skip,
  previous, volume, transfer, now-playing, list devices). Resolves Connect
  speakers by name (exact, alias, substring or fuzzy) and speaks a templated
  confirmation with no second LLM round-trip. The currently-playing track is
  injected into conversation context so the character can talk about what is on.
  PKCE auth, no client secret; `scripts/spotify_auth.py` and an optional
  `setup.sh` walkthrough handle first login. See `docs/SPOTIFY_SETUP.md`.
- **Drop-in modular output devices**: devices are plugin packages that
  self-register the way personalities do. Drop one under
  `jf_sebastian/devices/<name>/` and it is auto-discovered; each owns its
  settings and ships its own `.env` overlay, loaded when that device is selected.
- **Optional visual seam**: `requires_visual` plus `visual_*` hooks on the device
  base class let a device drive an on-screen renderer. Audio-only devices are
  unaffected.
- `GPT_REASONING_EFFORT` knob for the GPT-5 family.

### Changed
- Recommended conversation model is now `gpt-5.4-mini`, the value shipped in
  `.env.example`. The code-level default when `GPT_MODEL` is unset stays
  `gpt-4o-mini` as the always-available safety net (there is no automatic
  runtime fallback between models). GPT-5 request semantics
  (`max_completion_tokens`, no `temperature`) were already handled since 2.3.0.
- The per-device `.env` overlay moved from
  `device_overrides/{OUTPUT_DEVICE_TYPE}/.env` to
  `jf_sebastian/devices/{OUTPUT_DEVICE_TYPE}/.env`, inside the device bundle.
  The old path is no longer read.
- Johnny and Teddy Ruxpin use `shimmer` as their RVC input voice; their distinct
  character comes from voice conversion.
- Sentence chunking extracted into `SentenceChunker`, now abbreviation-aware
  with a soft length cap.
- RVC is enabled by the presence of a model rather than a redundant flag.
- Debug audio writes dispatch through a single background writer queue.

### Fixed
- The personality's system prompt was stored inside the bounded history deque
  and got evicted after roughly ten exchanges, so the character drifted out of
  character and forgot its instructions. It is now pinned outside the history;
  `MAX_HISTORY_LENGTH` bounds only the user/assistant turns.
- `rvc_filter_radius`, `rvc_rms_mix_rate` and `rvc_protect` from
  `personality.yaml` were silently ignored; they are now read and applied.
- The chunker split decimals at the streaming edge, so "1.5 ounces" was spoken
  as "one point five".
- A gpt-5 400 error when function tools and `reasoning_effort` were combined.

### Configuration
Audio capture defaults were aligned to the values already shipped in
`.env.example`, so code, config and docs agree:
```bash
SAMPLE_RATE=16000                 # was 44100; Silero VAD requires 16000, so the old default silently disabled VAD
SILENCE_TIMEOUT=5.0               # was 10.0
SPEECH_END_SILENCE_SECONDS=1.0    # was 1.5
```
Installs that set these in `.env` (including the `setup.sh` path) are
unaffected; installs relying on bare code defaults will see them take effect.
Spotify support installs from `requirements-spotify.txt` (`spotipy`).

## [2.6.0] - 2026-05-23

### Added
- **Silero VAD replaces WebRTC VAD** for Stage 3 speech-content detection.
  Substantially harder to fool with non-speech sounds (TV chatter, AC hum,
  distant music) that previously slipped past and triggered Whisper
  hallucinations.
- **Parallel filler and Whisper**: the filler phrase no longer waits for the
  Whisper response. Both start as soon as Stages 1-3 pass, so the filler covers
  the full transcribe + GPT + TTS window rather than only GPT + TTS.
- **Layered `.env` overlays**: settings compose from
  `personalities/{PERSONALITY}/.env` → `device_overrides/{OUTPUT_DEVICE_TYPE}/.env`
  → root `.env`. Loaded paths are exposed as `settings.LOADED_ENV_OVERLAYS` and
  logged at startup.
- **Jetson deployment support** via `docs/JETSON_DEPLOYMENT.md`. RVC behaves
  better on memory-constrained devices: reduced CUDA allocator pressure,
  conversion retried up to three times with backoff on transient CUDA OOM, and
  re-warmed before each scheduled event so idle-period cold starts don't stall
  the first chunk.
- **Streaming wake-word inference** replaces `predict_clip`, lowering per-frame
  latency. Sub-threshold scores in `[0.5, threshold)` are logged once per second
  to make flakiness diagnosable.
- **Jarvis personality**, using OpenWakeWord's bundled `hey_jarvis` model (no
  custom training), the `fable` voice through RVC, and 30 in-character fillers.

### Changed
- `VOICE_GAIN` now applies to RVC-converted audio as well as the raw TTS path;
  RVC output previously bypassed the gain stage.
- Filler audio loads lazily on first use, so startup is faster.
- Debug audio writes are gated on `SAVE_DEBUG_AUDIO` rather than always writing
  when debug mode was on.
- Output stream buffer raised to 4096 frames to eliminate underruns on slower
  hardware.
- `SERVICE.md` operational notes are gitignored as per-deployment.

### Fixed
- The toy could wake itself with its own voice; the recorder is now paused
  during playback, with a post-playback tail guard so speaker reverb doesn't
  trigger a new VAD event.
- The PortAudio stream is actually stopped during recorder pause instead of just
  dropping frames, which had been leaking CPU across long IDLE stretches.
- Stray `test.py` removed from the repo root.

### Breaking
- `VAD_AGGRESSIVENESS` (0-3, WebRTC) is replaced by `VAD_THRESHOLD`
  (0.0-1.0 probability, Silero). **Update `.env` on upgrade**: rename
  `VAD_AGGRESSIVENESS=2` to `VAD_THRESHOLD=0.5`, raising it if Whisper still
  hallucinates on noise or lowering it if valid speech is rejected.
- New dependency `silero-vad`, replacing `webrtcvad`.

## [2.5.0] - 2026-05-11

### Added
- **Pluggable news headlines provider**, mirroring the 2.4.0 weather pattern, so
  personalities can reference current events. Three adapters: **RSS** (default;
  any RSS or Atom feed via `feedparser`, falling back to NPR Topics: News so
  headlines work with zero configuration), **Hacker News** (free public API,
  parallel fan-out), and **manual** (newline-separated env var, zero network
  egress). Cached 30 minutes, top 5 headlines per turn.

### Changed
- HTML markup is stripped from RSS titles, which would otherwise be read aloud
  by TTS. A polite identifying `User-Agent` is sent on every request, since BBC,
  NYT, Reuters and Cloudflare-fronted feeds frequently 403 the default
  `python-requests` UA. Feed URL scheme is validated (http/https only) and
  `allow_redirects=False` prevents a misconfigured feed chaining through
  arbitrary hosts.
- Hacker News fetches share a `requests.Session` with a `ThreadPoolExecutor` so
  cold-miss latency stays bounded at higher `NEWS_HEADLINE_LIMIT`, with a 2s
  per-item timeout and per-item `raise_for_status()` (the Firebase API can
  return Cloudflare HTML on a 200 during incidents).
- News provider startup log names the resolved feed and how to disable it.
- Documentation refresh: the README project tree was brought current with the
  actual filesystem, and `.env Settings` gained the Weather, News, Scheduler and
  Supervisor categories that were previously undocumented.

### Configuration
```bash
#NEWS_PROVIDER=rss              # or hackernews / manual / none / auto
#NEWS_RSS_URL=https://feeds.npr.org/1001/rss.xml
#MANUAL_NEWS=Headline one\nHeadline two
#NEWS_HEADLINE_LIMIT=5
#NEWS_CACHE_TTL_MINUTES=30
```
News is **on by default**. Existing installs will begin fetching NPR headlines
at next restart; add `NEWS_PROVIDER=none` to opt out. For child-facing
personalities, consider `none` or a kid-safe feed, since NPR Top News may
include violence or politics. New dependency: `feedparser>=6.0.10`.

## [2.4.1] - 2026-05-10

### Fixed
- **Scheduled events never fired.** `IDLE → SPEAKING` was missing from the state
  machine's `VALID_TRANSITIONS` table, so `try_transition` rejected every
  proactive event. In the wild the scheduler logged the event, synthesized TTS
  via OpenAI, then silently aborted with no audio. The transition is now allowed,
  because scheduled speech is server-initiated and legitimately bypasses the
  LISTENING and PROCESSING phases.
- Misleading log message for scheduled-event CAS failures: every failure read
  "lost race to another transition", including this hardcoded rejection. It now
  reads "could not enter SPEAKING (state=…)".

No configuration changes.

## [2.4.0] - 2026-05-09

### Added
- **Pluggable weather provider**: the hardwired wttr.in fetch becomes a
  `WeatherProvider` interface with three adapters: wttr.in (default, no API
  key), Home Assistant (local, no third-party egress) and manual (offline).
  Auto-selects when `WEATHER_PROVIDER` is unset; existing `ZIPCODE`-only setups
  keep working. `WEATHER_PROVIDER=none` disables weather entirely.
- **Process supervisor** (`scripts/supervisor.py`) for unattended deployments:
  exponential-backoff restart, watchdog kill of hung children via heartbeat-file
  staleness, enriched crash reports, and permanent-failure detection after N
  consecutive crashes. Ships launchd plist and systemd unit templates.
- **Proactive scheduler / ambient mode**: personalities define utterances in
  `personalities/<name>/scheduled_events.yaml`: morning greetings, bedtime
  stories, holiday surprises. Schedule syntax `HH:MM`, `HH:MM weekdays`,
  `HH:MM YYYY-MM-DD`; each event uses `say:` (verbatim TTS) or `prompt:` (LLM in
  character). Events fire only when IDLE, never interrupting a conversation.
  Quiet-hours suppression with load-time warnings.
- `StateMachine.try_transition(expected, target, trigger)`, a compare-and-swap
  that closes TOCTOU windows for callers gating on current state.
- `utils/heartbeat.py`, a liveness thread the supervisor reads to detect a hung
  PROCESSING state.
- `ROADMAP.md`, synthesized from a seven-persona codebase audit.

### Changed
- **Local-first weather security**: the Home Assistant bearer token is refused
  over plain HTTP to non-private hosts (loopback, RFC1918, link-local and
  `*.local` allowed); the entity ID is URL-quoted; `allow_redirects=False`
  prevents token leak via cross-host redirect.
- Hung children are killed with `os.killpg` on the child's process group, so
  ffmpeg and RVC subprocesses die too rather than being orphaned.
- Crash reports carry PID, personality, uptime, heartbeat age at exit, hostname,
  Python version and the last 100 log lines, pruned to the most recent 200 so a
  permanent-failure loop cannot fill the disk.
- `jf_sebastian.log` and `supervisor.log` rotate (10 MB × 5).
- SIGTERM/SIGINT use cooperative shutdown rather than `sys.exit()` from a signal
  handler.
- Schedule syntax gained `weekdays`/`weekends` aliases, friendlier parse errors,
  past-dated one-shot warnings, and a startup log listing loaded events.

### Fixed
- A malformed `HOME_ASSISTANT_URL` raised `ValueError` from `urlsplit` and broke
  the entire weather pipeline, including the auto-fallback to wttr.
- The `_refresh_in_flight` flag leaked `True` when the weather provider became
  unconfigured mid-refresh, suppressing all future refreshes.
- A weather cold-miss caused "I can't check the weather" on the first
  conversation. The first fetch is now synchronous, with a retried pre-warm at
  startup.
- numpy int16 overflow `RuntimeWarning` in RMS amplitude calculation.
- A race in the scheduled-event callback could re-init PyAudio after
  `audio_player.cleanup()` during shutdown.
- A wake-word detector race during scheduled-event TTS synthesis.
- `_pause_wake_for_playback` was set even when `pause()` raised, causing a
  missed resume.

### Configuration
All new variables optional with sensible defaults: `WEATHER_PROVIDER`,
`HOME_ASSISTANT_URL`/`_TOKEN`/`_WEATHER_ENTITY`, `MANUAL_WEATHER`,
`SCHEDULER_ENABLED`, `QUIET_HOURS_START`/`_END`, and the supervisor's
`HEARTBEAT_FILE`, `WATCHDOG_TIMEOUT`, `RESTART_BACKOFF_INITIAL`/`_MAX` and
`CRASH_REPORT_DIR`.

## [2.3.0] - 2026-03-25

### Added
- **Real-world context for conversations**: the LLM receives the current
  date/time and weather (via wttr.in), so personalities can answer "what time is
  it?" naturally. Configured with `ZIPCODE`.
- **Multi-stage silence detection**: a four-stage audio validation pipeline
  (length → RMS → VAD speech ratio → transcript hallucination check) that
  prevents Whisper hallucinations and unnecessary API calls.
- **Headless output device** for computer-only playback without hardware.
- **GPT-5 model compatibility**: automatic parameter adaptation for token limits
  and temperature constraints.
- **Cross-platform support**: Linux and Jetson compatibility for audio, GPU
  detection and setup.
- **Fred (Mister Rogers) personality**.
- `CLAUDE.md` for Claude Code guidance.

### Changed
- Codebase cleanup: Squawkers became a `HeadlessDevice` subclass, `AudioPlayer`
  helpers were extracted, and dead code (unused mock classes, commented-out
  blocks) removed.
- The pyphen dictionary is cached in `PPMGenerator`, and state-machine
  transition history is capped.
- RVC reliability: device validation, fail-fast on permanent errors, and
  Jetson-specific installation support.
- Updated wake word models for fred, johnny, kitt, leopold, mr_lincoln and
  teddy_ruxpin.

### Fixed
- A race in the audio recorder when `stop_recording` was called from the
  callback thread.
- An RVC crash when `vc_single` returned a tuple containing `None` audio.
- RVC audio playing too fast, by propagating the actual sample rate.

## [2.2.0] - 2026-01-16

### Added
- **Teddy Ruxpin personality**: the 1980s storytelling bear from Grundo, with
  friends Grubby, Princess Aruzia and Newton Gimmick, 30 adventure-themed filler
  phrases, the "Hey, Teddy Ruxpin" wake word, a warm Echo voice, and RVC support.

### Changed
- macOS audio stream delay reduced from 2.0s to 0.5s, saving 1.5 seconds between
  filler and response playback.
- RVC tuning aimed at 30-40% faster conversion (`rvc_filter_radius: 0`,
  `rvc_rms_mix_rate: 0.1`, `rvc_protect: 0.2`) added to the K.I.T.T. and Teddy
  Ruxpin YAML. The loader did not read these three keys until the 2.7.0 fix, so
  the tuning only took effect from that release.
- The RVC optimization script moved to `scripts/benchmark_rvc.py`; redundant
  per-personality READMEs removed.

## [2.1.1] - 2026-01-02

### Added
- **RMS amplitude silence filter** ahead of Whisper, so silence and very quiet
  audio are not transcribed. It measures **peak** RMS, using 100 ms sliding
  windows with 50% overlap and taking the maximum, so silence does not drag down
  the measurement and speech surrounded by quiet audio is still detected.
  Configured with the new `MIN_AUDIO_RMS` (default 60). An average-RMS version
  with a default of 800 existed only between 2.1.0 and this release.
- RMS logging shows both the peak value and the active threshold, to make
  tuning possible.

### Fixed
- Added "bye" to the meaningless-transcription filter, reducing false responses
  to background noise.
- A roughly 2-second delay before the wake-word detector resumed on returning to
  IDLE.

## [2.1.0] - 2026-01-02

### Added
- **Gapless audio playback** via persistent stream sessions, so filler audio
  flows into response chunks with no gap. Works at both 44.1 kHz (Teddy Ruxpin)
  and 48 kHz (Squawkers McCaw). New `AudioPlayer.start_playback_session()`,
  `write_session_chunk()` and `end_playback_session()`; the existing
  `play_stereo()` remains for single-shot playback.
- **Continuous conversation mode**: multi-turn dialogue without repeating the
  wake word, with a configurable timeout.
- **RVC warmup** at startup, eliminating the first-use conversion delay.
- **RVC voice conversion for K.I.T.T.**, with custom voice model integration.
- `ENABLE_FILLER_AUDIO` to disable filler phrases for faster responses.

### Changed
- RVC `index_rate` enabled for better voice quality, after resolving a
  faiss/PyTorch OpenMP conflict.
- Transcript validation prevents responding to empty or meaningless speech
  ("um", "uh").

### Fixed
- CoreAudio stream abandonment on macOS, plus audio playback hangs and stream
  timeouts.
- Audio recorder restart issues in continuous mode.
- Playback timing and buffer management issues, including buffer drain timing
  that caused stream close timeouts.

All changes are backwards compatible; no configuration or personality changes
are required.

## [2.0.0] - 2025-12-23

### Added
- **RVC voice conversion support**, integrated with the streaming TTS pipeline,
  with setup documentation and an automated pip 24.0 workaround for its
  dependencies.
- **K.I.T.T. personality** from Knight Rider, with a trained "Hey Kitt" wake
  word and a 0.92 speech rate tuned for character accuracy.
- **Modular device system**: refactored to support multiple device types (Teddy
  Ruxpin, Squawkers McCaw), each with its own filler audio and PPM
  configuration.
- Python 3.10 auto-detection and auto-installation via pyenv or Homebrew, plus a
  `.python-version` file and detection of a venv built on the wrong version.
- RVC installation integrated into `setup.sh`, handling the pip downgrade,
  install and upgrade automatically, with an import verification test.

### Changed
- **Sequential playback queue** replaces the previous architecture, eliminating
  race conditions. Audio writes in chunks so playback is interruptible, fixing
  blocking PyAudio calls that previously caused hangs.
- The system waits for all audio chunks to complete before transitioning to
  IDLE, and the recovery timeout is disabled during active sequential playback.
- PROCESSING timeout raised from 15s to 30s.
- All filler audio is pre-loaded at startup, eliminating 14-second conversation
  pauses; WAV parsing moved to `soundfile`.
- Audio is captured immediately after the wake word so the first words are not
  missed.
- Filler generation is now optional during setup, saving 2-3 minutes.

### Fixed
- `AttributeError` in the state machine (`state` rather than `current_state`).
- Filler playback timeout and flag management.
- Missing import for `find_audio_device_by_name`.
- Wake word detection during active interactions.
- Wake word filename references after model updates.

### Breaking
- **Python 3.10.x is required**; 3.11+ is not supported due to RVC dependency
  constraints. On upgrade, re-run `./setup.sh` to rebuild the venv on the right
  interpreter, and regenerate filler audio if it was skipped.

## [1.0.0] - 2025-12-14

First stable release.

### Added
- **Multi-personality system** with Johnny (tiki bartender), Mr. Lincoln and
  Leopold, plus an extensible framework for custom wake words, voices and
  knowledge.
- **Voice pipeline**: local wake word detection via OpenWakeWord (no cloud
  dependency), Whisper transcription, GPT-4o-mini conversation, and
  personality-specific TTS with voice, speed and tone control.
- **Low-latency filler phrases** for responsive interactions.
- **Animatronic control**: PPM signal generation, syllable-based lip sync,
  sentiment-based eye expressions with temporal smoothing, and multi-frame
  blinking. Stereo output with voice on the LEFT channel and control signals on
  the RIGHT; tested with Arsvita Bluetooth cassette adapters.
- Verified PPM channel mapping and eye-movement polarity for Teddy Ruxpin
  hardware, plus a channel testing script for verification.
- Automatic cleanup of existing instances on startup to prevent resource
  conflicts.
- Debug logging and audio capture, pytest coverage, and setup automation.

Requires Python 3.10+, macOS (tested on Apple Silicon), an OpenAI API key, and
optionally a Bluetooth cassette adapter.

[2.8.0]: https://github.com/pjdoland/jf-sebastian/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/pjdoland/jf-sebastian/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/pjdoland/jf-sebastian/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/pjdoland/jf-sebastian/compare/v2.4.1...v2.5.0
[2.4.1]: https://github.com/pjdoland/jf-sebastian/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/pjdoland/jf-sebastian/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/pjdoland/jf-sebastian/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/pjdoland/jf-sebastian/compare/v2.1.1...v2.2.0
[2.1.1]: https://github.com/pjdoland/jf-sebastian/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/pjdoland/jf-sebastian/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/pjdoland/jf-sebastian/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/pjdoland/jf-sebastian/releases/tag/v1.0.0
