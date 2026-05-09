# J.F. Sebastian Roadmap

This roadmap was synthesized from a seven-persona codebase review. Seven distinct user personas
each produced ten high-impact enhancement ideas, then peer-reviewed each others' suggestions.
Items here all received 6-of-7 or 7-of-7 approval across the panel.

## Personas

- **Mike** — Hobbyist Maker (multiple animatronics, Plex-style management)
- **Sam** — Sound Engineer (theater installs, latency-obsessed)
- **Linda** — Teacher / Parent (storytime, kids 6 & 9)
- **Carlos** — Caregiver (memory-care home, dementia residents)
- **Aria** — Personality Author (Patreon character creator)
- **Pat** — Privacy Advocate (homelab self-hoster)
- **Riley** — Reliability Engineer (30-exhibit museum fleet)

## Borda Count — Top Suggestions

Score = total YAY votes including originator (max 7/7).

| ID | Title | Score | YAY | NAY |
|----|-------|-------|-----|-----|
| M9 | Local/Offline Mode With Fallback Models | 7/7 | M, S, L, C, A, P, R | — |
| S2 | Local Streaming TTS with Sub-200ms First-Audio | 7/7 | M, S, L, C, A, P, R | — |
| P1 | Pluggable STT Backend Architecture | 7/7 | M, S, L, C, A, P, R | — |
| P2 | Pluggable LLM Backend (Ollama / llama.cpp) | 7/7 | M, S, L, C, A, P, R | — |
| P3 | Pluggable TTS Backend (Piper / Coqui) | 7/7 | M, S, L, C, A, P, R | — |
| P8 | Local Weather & Context Provider | 7/7 | M, S, L, C, A, P, R | — |
| R3 | OTA Personality & Wake-Word Model Updates | 7/7 | M, S, L, C, A, P, R | — |
| M2 | Web-Based Personality Manager Dashboard | 6/7 | M, L, C, A, P, R | S |
| M6 | Auto Lip-Sync Calibration Wizard | 6/7 | M, S, L, C, A, P | R |
| M10 | Scheduled Behaviors & Ambient Mode | 6/7 | M, S, L, C, P, R | A |
| A5 | Emotion & Mood State Engine | 6/7 | M, S, L, C, A, P | R |
| A6 | Multi-Modal Soundscape Layer | 6/7 | M, S, L, C, A, P | R |
| R7 | Supervisor Daemon with Crash-Loop Backoff | 6/7 | M, S, L, C, P, R | A |

After deduplication (M9 collapses into P1+P2+P3 as the umbrella), this yields 10 distinct
enhancements grouped by implementation difficulty.

---

## Tier 1 — Easiest to Implement

### 1. Local & Pluggable Weather/Context Provider (P8 — 7/7)

Refactor `utils/context_provider.py` from a hard-wired `wttr.in` HTTP call into a pluggable
interface with adapters for Home Assistant, manual overrides, and local weather stations
alongside the existing wttr.in adapter. Today every conversation makes a silent third-party
call; an interface change here removes the only non-OpenAI cloud dependency.

- **Difficulty:** Low — one module refactor, ~150 LOC, no new system surfaces.
- **Impact:** Medium — closes a small but universally-noticed privacy/observability gap,
  enables Home-Assistant-rich households.
- **Dependencies / risks:** None significant. Risk is bikeshedding the adapter interface;
  resist over-abstracting.

### 2. Supervisor Daemon with Crash-Loop Backoff (R7 — 6/7)

Wrap `python -m jf_sebastian.main` in a tiny supervisor (launchd plist on macOS, systemd
unit on Linux) that catches PortAudio/RVC segfaults, applies exponential backoff, kills
hung-PROCESSING workers via watchdog timer, and writes a crash report with the last N log
lines. Today a PortAudio crash silently takes the toy offline for hours.

- **Difficulty:** Low — mostly config files + a 100-LOC watchdog wrapper.
- **Impact:** High for unattended deployments (caregivers, museums, kids' rooms); also catches
  the long-tail of audio-stack flakes Mike sees in the garage.
- **Dependencies / risks:** Need a clean shutdown path; watchdog timeout must be tuned not to
  interrupt a legitimate long Whisper call.

### 3. Scheduled Behaviors & Ambient Mode (M10 — 6/7)

Cron-style scheduler integrated with the state machine that lets a personality proactively
initiate dialogue at scheduled times (greet at 7am, bedtime story at 9pm), respond to
webhook/HomeKit events, and trigger seasonal one-off behaviors. Currently the toy is purely
reactive — only wakes on wake word.

- **Difficulty:** Low–Moderate — APScheduler or similar + a new `scheduled_events.yaml` per
  personality + state machine entry point for proactive speech.
- **Impact:** High — turns a passive toy into an ambient companion; combos powerfully with R3
  (OTA) for time-sensitive content.
- **Dependencies / risks:** Must respect quiet hours and never speak over a user's active
  conversation; needs a mute/suppress mechanism. Trigger ergonomics matter (avoid yet another
  `.env` zoo).

---

## Tier 2 — Moderate Effort

### 4. Web-Based Personality Manager Dashboard (M2 — 6/7)

A local Flask/FastAPI web UI for browsing, hot-swapping, editing, previewing, and uploading
personalities, wake-word ONNX files, RVC bundles, and filler audio — replacing manual `.env`
edits and YAML hand-authoring. Plex-style polish for non-coders.

- **Difficulty:** Moderate — substantial new surface (HTTP server + frontend build chain +
  auth), but no algorithmic complexity.
- **Impact:** Very high for adoption; this is the single most-named feature across personas.
  Becomes the natural host for L4/A2/A5 if/when those land.
- **Dependencies / risks:** Auth/network exposure (especially with kids/elders in the house);
  pick a stack (htmx + jinja keeps it light, React adds maintenance burden). Sam's NAY is
  fair: this doesn't help his pro use case, but it doesn't hurt it either.

### 5. Auto Lip-Sync Calibration Wizard (M6 — 6/7)

A guided one-time-per-device routine that plays calibration sweeps, captures motor response
(mic, accelerometer, or webcam), and auto-tunes per-unit PPM pulse widths, gain, and syllable
timing. Today every Teddy unit needs hand-tuning by trial and error.

- **Difficulty:** Moderate — depends heavily on capture method. Mic-only version is ~weekend
  work; optical version is multi-week.
- **Impact:** High for hardware diversity — eliminates a setup cliff that prevents
  non-tinkerers from getting good lip sync.
- **Dependencies / risks:** Need to persist per-device tuning state (probably alongside
  personality config). Failure mode of mic-driven calibration in noisy environments.

### 6. Emotion & Mood State Engine (A5 — 6/7)

A persistent affective state vector (valence, arousal, trust, energy) that drifts across
turns, modulates TTS speed/style, RVC pitch shift, eye-position bias, and filler phrase
selection. Today characters feel emotionally flat between responses.

- **Difficulty:** Moderate — state machine adjunct + small modulators on existing
  TTS/RVC/sentiment paths. Real challenge is *tuning*, not coding.
- **Impact:** High for character believability — biggest qualitative win for personality-driven
  use cases. Aria/Carlos/Linda all see this as their #1 win.
- **Dependencies / risks:** Risk of the LLM "fighting" mood state when the system prompt
  overrides; need careful prompt-injection of mood. Privacy: state must not leak emotional
  inference into logs without consent.

### 7. Multi-Modal Soundscape Layer (A6 — 6/7)

YAML-defined ambient beds, music stingers, and SFX cues triggered by inline tags in LLM output
(`<sfx:thunder>`, `<music:tense:fade>`), mixed into the LEFT channel alongside voice. Today
the toy can only speak; soundscapes must be pre-baked into TTS.

- **Difficulty:** Moderate — needs an LLM output parser (treat tags as markup), an audio mixer
  chain in front of the device output, and a soundscape library directory structure.
- **Impact:** High for storytelling and creative use. Compounds with story mode, scene
  direction, and emotion engine.
- **Dependencies / risks:** Tag schema must be stable across personality versions. PPM-channel
  timing must not break when LEFT channel suddenly gets a music bed (may need a brief duck-out).
  LLM compliance with tag instructions varies.

### 8. OTA Personality & Wake-Word Model Updates (R3 — 7/7)

Signed delivery of `.personality` bundles (YAML + ONNX + RVC + filler audio) to a device with
checksum verification, atomic swap, automatic rollback if post-update health checks fail, and
a manifest server. Today personality updates are git pulls or manual file copies.

- **Difficulty:** Moderate — requires a small server (manifest + signed artifacts), a client
  that does atomic swaps, and a health-check definition. Code-signing is the hardest sub-problem.
- **Impact:** Very high — unlocks Mike's marketplace dream, Aria's distribution workflow,
  Riley's fleet, and lets non-coders actually upgrade their toys.
- **Dependencies / risks:** Trust model is everything. Self-hosted homelab signing needs a UX
  that doesn't terrify a non-technical user. Ties intimately to Tier-3 backend abstractions if
  a personality bundles a local LLM/TTS preference.

---

## Tier 3 — Most Difficult / Architectural

### 9. Pluggable Local-First STT/LLM/TTS Backends (M9 + P1 + P2 + P3 — 7/7 each)

Refactor `SpeechToText`, `ConversationEngine`, and `TextToSpeech` into provider abstractions
with implementations for: STT (whisper.cpp, faster-whisper, Vosk, OpenAI), LLM (Ollama,
llama.cpp, OpenAI-compatible endpoints, OpenAI), TTS (Piper, Coqui, OpenAI). Personalities
declare backend preferences in YAML; system can run fully on-device with no internet.

- **Difficulty:** High — three cross-cutting refactors, three new dependency families, RVC
  compatibility checks against Piper/Coqui output, streaming-pipeline preservation across
  backends, performance tuning per backend.
- **Impact:** Civilization-level — every persona ranked this 7/7. Enables genuine local-first
  operation, slashes recurring cost, removes a hard blocker for child/elder/medical
  deployment, and is a precondition for true offline ambient mode.
- **Dependencies / risks:** Quality regression risk (local Whisper/LLM/TTS often noticeably
  worse than OpenAI); need a graceful "best available" fallback policy. RAM/CPU/GPU footprint
  on a Mac mini may not fit all three local stacks simultaneously. Streaming token-by-token
  from local LLMs varies by backend.

### 10. Streaming Low-Latency TTS Architecture (S2 — 7/7)

Reengineer the TTS path to stream PCM at the chunk level, eliminating MP3 decode, the network
round-trip, and resampling stages — targeting sub-200ms first-audio. Today the pipeline is
OpenAI HTTP → MP3 → FFmpeg → PCM → device.

- **Difficulty:** High — requires switching to a backend that streams (Piper/StyleTTS2/XTTS),
  reworking the audio engine from blocking write to a sample-clock-driven mixer, and aligning
  PPM phase to the new timing. Closely related to #9 but a distinct engineering problem.
- **Impact:** Very high — the single biggest perceptible UX win after local backends; turns
  4–6s feel into <1s feel and obsoletes much of the filler-phrase complexity.
- **Dependencies / risks:** Hard dependency on #9 (streaming TTS needs a streaming-capable
  backend). PPM lip-sync is currently driven off completed audio; switching to a streaming
  source means re-deriving syllable timing on the fly. Bluetooth output adds non-deterministic
  100–300ms latency that fights the goal — wired output may be required for the full benefit.

---

## Excluded From Roadmap

The following received 1/7 or 2/7 and should live in downstream forks, plugins, or sister
projects rather than J.F. Sebastian core:

- Theatrical show-control (OSC/MIDI/DMX, AES67 audio, timeline-accurate engine)
- Education-specific narrow modes (curriculum YAMLs, storybook reading, homework helper)
- Eldercare-specific narrow modes (medication reminders, distress SMS alerts, reminiscence library)
- SRE-specific fleet tooling (Prometheus/OTLP telemetry, canary cohorts, anomaly detection,
  audit/replay vault)
- Personality marketplace with one-click import (privacy/safety risk to vulnerable users)
