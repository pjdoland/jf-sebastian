# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries before 2.7.0 are summarised from their release tags; see
`git log vX.Y.Z..vA.B.C` for the full detail of any release.

## [2.8.0] - 2026-09-20

### Added
- **Philips Hue light control** (optional, off by default). A personality can
  turn lights on and off, set brightness and colour, and activate stored scenes
  by voice. Talks to the Hue Bridge's local v1 API over the LAN via `requests`
  — no cloud account, no new dependency — so Alexa and the Hue app keep working
  alongside it. Six `lights_*` tools; see `docs/HUE_SETUP.md`.
- `scripts/hue_pair.py` for one-time Bridge pairing. Discovers the Bridge,
  handles the link-button handshake, caches the credential `0600` outside the
  repo, and prints an inventory of rooms, lights and scenes.
- `HUE_ENABLED`, `HUE_TOKEN_CACHE` and `HUE_BRIDGE_HOST` settings, plus a
  per-personality `hue_enabled` flag for excluding a character.
- `jf_sebastian/modules/tool_provider.py`, the shared base every LLM tool
  provider builds on: `ToolResult`/`ToolError`, the OpenAI function-schema
  envelope, name normalization, the tiered name-resolution ladder, and a
  dispatch that converts any failure into a spoken hint rather than an
  exception in the conversation turn.

### Changed
- The conversation engine now holds a **list** of tool providers instead of a
  single hardcoded Spotify tool. Each provider contributes its own schemas and
  claims a tool-name namespace; dispatch routes by name. Adding a provider is a
  `ToolProvider` subclass plus a constructor keyword argument.
- Spotify and Hue share one name resolver. It takes ordered tiers, so Spotify
  passes one (Connect devices) and Hue passes two (rooms and zones, then
  individual bulbs) through the same code path. Spotify keeps its own alias
  map, configured default and active-device fallback layered around it.
- A `.gitignore` guard for `hue.json`, matching the existing one for the
  Spotify token cache, in case `HUE_TOKEN_CACHE` is pointed into the repo.

### Fixed
- A tool provider missing a contract method raised inside the streaming loop
  and aborted the **entire** conversation response rather than losing just its
  own tool call. The contract is now validated once at construction, and a
  provider that fails validation is logged and never advertises its schemas.
- Name resolution matched a stored name inside a longer spoken phrase as a raw
  substring, so a short name could swallow unrelated requests — a zone called
  "Up" answered "the cupboard light". Reverse matching now requires word
  boundaries; naming part of a name still works as a plain substring.
- A room or device whose name normalized to empty was contained in every
  target and answered every non-exact request. Blank candidates are skipped.
- An ambiguous earlier tier fell through to a later one, so in a house with
  several bedrooms "bedroom" could be answered by a lamp instead of a room.
- Colour names matched as substrings, so "ultraviolet" silently resolved to
  violet. Matching is now on word boundaries.
- White Ambiance bulbs (colour temperature, no hue channel) were reported as
  unable to change colour, losing every white on those fixtures.
- Scenes could be applied to a group they were not stored for, and naming a
  single bulb applied a scene to that bulb's whole room while reporting only
  the bulb. Both are now refused explicitly.
- The OpenAI schema helper shallow-copied its properties, so every schema built
  from a shared property constant aliased the same nested dictionaries.

## [2.7.0] - 2026-06-22

### Added
- Optional **Spotify playback control** with PKCE auth, nine `music_*` tools,
  Connect-speaker resolution by spoken name, and now-playing context injection.
- Drop-in modular output devices: device packages self-register, carry their
  own settings, and load a per-device `.env` overlay from the bundle.
- An optional visual seam on the device base class for an on-screen renderer.

### Changed
- Default model is now `gpt-5.4-mini`, with a `GPT_REASONING_EFFORT` knob.
- The system prompt is pinned outside the bounded history deque, so a
  personality no longer drifts out of character as a conversation grows.
- Sentence chunking extracted into `SentenceChunker`; decimals no longer split
  at the streaming edge.
- Debug audio saves dispatch through a single background writer queue.

## [2.6.0] - 2026-05-23

Silero VAD, Jetson support and parallel filler playback.

## [2.5.0] - 2026-05-10

Pluggable news headlines.

## [2.4.1] - 2026-05-10

Fix scheduled events being rejected by the state machine.

## [2.4.0] - 2026-05-09

Pluggable weather providers, process supervisor and proactive scheduling.

## [2.3.0] - 2026-03-25

Improved real-world context injection for LLM conversations.

## [2.2.0] - 2026-01-16

RVC voice conversion for the Teddy Ruxpin personality.

## [2.1.1] - 2026-01-02

Improved RMS amplitude detection with peak windowing.

## [2.1.0] - 2026-01-02

## [2.0.0] - 2025-12-23

## [1.0.0] - 2025-12-14

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
