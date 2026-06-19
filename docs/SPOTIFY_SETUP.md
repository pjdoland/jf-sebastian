# Spotify Playback Control

Let a personality control Spotify by voice ("José, play some tiki music in the
kitchen"). Optional and off by default.

## How it works
- The LLM is given playback **tools** (function calling). On a normal turn nothing
  changes; when you ask for music it emits a tool call, the app runs it against the
  Spotify Web API (via `spotipy`), and the character speaks a short confirmation.
- Playback targets a **Spotify Connect device** (a separate speaker), not the
  animatronic's own output. You can name a room/speaker per command.
- Requires **Spotify Premium**. The API commands an existing Connect device; it
  doesn't produce audio itself, so a speaker (Echo, Sonos, desktop Spotify, a
  `raspotify` Pi, phone) must be online.

## 1. Install the dependency
```bash
pip install -r requirements-spotify.txt
```

## 2. Create a Spotify app (free)
1. Go to https://developer.spotify.com/dashboard → **Create app**.
2. Add a **Redirect URI**: `http://127.0.0.1:8888/callback` (loopback, not `localhost`).
3. Copy the **Client ID**. (No client secret needed; we use PKCE.)

## 3. Configure (.env)
```bash
SPOTIFY_ENABLED=true
SPOTIFY_CLIENT_ID=your_client_id
# SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback   # default
# SPOTIFY_TOKEN_CACHE=~/.config/jf-sebastian/spotify-token.json   # default (kept 0600)
SPOTIFY_DEFAULT_DEVICE=Living Room          # speaker for "play X" with no room named
# SPOTIFY_DEVICE_ALIASES=kitchen=Kitchen Echo,den=Living Room
```
With the master switch on, every personality can control playback by default.
To exclude a specific character, set this in its `personality.yaml`:
```yaml
spotify_enabled: false
```

## 4. Authorize once
On a machine **with a browser**:
```bash
python scripts/spotify_auth.py
```
This logs you in, caches a refresh token (chmod 0600), and **prints your available
Connect device names**; use those exact names for `SPOTIFY_DEFAULT_DEVICE` /
`SPOTIFY_DEVICE_ALIASES`. Re-list anytime with `python scripts/spotify_auth.py --devices`.

## Headless devices (e.g. Jetson)
The browser login can't run on a headless box. Authorize on your Mac (step 4),
then **copy the token cache file** to the same path on the device:
```bash
scp ~/.config/jf-sebastian/spotify-token.json  jetson:~/.config/jf-sebastian/
```
Use the same `SPOTIFY_CLIENT_ID` and redirect URI on both. spotipy auto-refreshes
the token thereafter. If the refresh token is ever revoked (password change,
"remove access" in Spotify settings), re-run step 4 and re-copy the file.

## What you can say
- "Play *Quiet Village*" / "play some tiki music" / "play it in the kitchen"
- "pause" / "resume" / "skip" / "go back"
- "turn up the music" (controls the **music** volume, capped at 70; "speak up"
  controls the character's own voice)
- "move the music to the bedroom"
- "what's playing?" / "what speakers can you play on?"
- "what is this song?" / "who's the artist?" / "what album is this from?" (the
  currently-playing track is kept in context, so these need no playback command)

## Now-playing context
When Spotify is enabled, the currently-playing track (title, artist, album) is
injected into the conversation context each turn, so the personality can discuss
it naturally without you asking it to look anything up. The lookup is cached and
refreshed in the background, so it adds no latency. Turn it off with
`SPOTIFY_NOW_PLAYING_CONTEXT=false` while keeping playback control.

## Notes
- A target speaker that's asleep/offline won't appear; the character says so.
- Scopes are minimal: `user-read-playback-state user-modify-playback-state` (no
  account-mutating access). The token cache is a credential; it's gitignored and
  kept out of any synced bundle by default.
