"""
Spotify playback control for J.F. Sebastian (optional, per-personality).

A self-contained, hardened wrapper around the Spotify Web API (via spotipy) that
exposes a small set of playback "tools" to the LLM. Phase 1: this module stands
on its own (the conversation engine wires it in later). You can exercise it
directly with scripts/spotify_auth.py.

Design notes (shaped by review):
- HARDENED like utils/weather.py: short request timeout, capped retries, every
  call wrapped so failures return a typed ToolResult instead of raising into the
  conversation turn. Lazy client: nothing connects until the first call.
- LEAST PRIVILEGE: exactly two scopes (read + modify playback). No account
  mutation surface. The scope list is asserted in tests so it can't silently widen.
- MULTI-SPEAKER: every action resolves a Spotify Connect device by spoken name
  (fuzzy match + an optional alias map + a configurable default), so you can say
  "play it in the kitchen" or "move it to the bedroom".
- PKCE auth (no client secret stored on the device); token cached to a private,
  0600 file outside any synced bundle.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from jf_sebastian.config import settings

logger = logging.getLogger(__name__)

# Least-privilege scopes. Read playback state + control playback. Nothing else.
# (A test asserts this exact set so a future edit can't widen account access.)
SCOPES = "user-read-playback-state user-modify-playback-state"

_REQUEST_TIMEOUT_S = 5          # hard per-call timeout (mirrors weather.py)
_VOLUME_MAX = 70                # clamp: a stray "max volume" utterance shouldn't blast the house
_SEARCH_TYPES = "track,artist,playlist,album"
_NOW_PLAYING_TTL_S = 5          # brief cache to coalesce rapid back-to-back turns (kept short so "what's playing" stays current)


@dataclass
class ToolResult:
    """Outcome of a tool call. `spoken_hint` is a short, neutral phrase the
    caller can hand to the personality to voice in character (we never speak
    raw API data or errors). `kind` is the error taxonomy for logging.
    `suppress_followup` lets a tool declare 'this started music' so the caller
    can go idle instead of listening over the music -- the tool owns that fact,
    not the conversation engine."""
    ok: bool
    spoken_hint: str
    kind: str = "ok"                       # ok | not-premium | device-offline | device-not-found
                                           #   | auth-revoked | rate-limited | network | no-match | bad-args
    suppress_followup: bool = False
    data: dict = field(default_factory=dict)  # structured detail (NOT for logging at INFO)


class SpotifyToolError(Exception):
    def __init__(self, kind: str, spoken_hint: str, data: Optional[dict] = None):
        super().__init__(spoken_hint)
        self.kind = kind
        self.spoken_hint = spoken_hint
        self.data = data or {}


def _parse_aliases(raw: Optional[str]) -> dict:
    """'kitchen=Kitchen Echo, den=Living Room' -> {'kitchen': 'Kitchen Echo', ...}"""
    out = {}
    for pair in (raw or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip().lower()] = v.strip()
    return out


def _join_artists(item: dict) -> str:
    """Comma-join a track/playback item's artist names (skips any without a name)."""
    return ", ".join(a["name"] for a in item.get("artists", []) if a.get("name"))


def build_spotify_client(cache_path: str, *, open_browser: bool = False,
                         requests_timeout: int = _REQUEST_TIMEOUT_S):
    """Build an authed spotipy client (PKCE -> no client secret on device).

    The single place that knows the auth shape: redirect URI, scopes, cache, and
    the timeout/retry caps. Shared by the runtime tool (open_browser=False,
    headless-safe) and the one-time auth script (open_browser=True). Raises
    ImportError if spotipy is absent, ValueError if SPOTIFY_CLIENT_ID is unset.
    """
    import spotipy
    from spotipy.oauth2 import SpotifyPKCE
    from spotipy.cache_handler import CacheFileHandler

    client_id = (settings.SPOTIFY_CLIENT_ID or "").strip()
    if not client_id:
        raise ValueError("SPOTIFY_CLIENT_ID is not set")
    auth = SpotifyPKCE(
        client_id=client_id,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope=SCOPES,
        open_browser=open_browser,
        cache_handler=CacheFileHandler(cache_path=os.path.expanduser(cache_path)),
    )
    # Capped timeout/retries so a slow/rate-limited API can never stall a turn
    # (a 429 Retry-After won't sleep us for long).
    return spotipy.Spotify(auth_manager=auth, requests_timeout=requests_timeout,
                           retries=1, status_retries=1, backoff_factor=0.1)


class SpotifyTool:
    def __init__(self) -> None:
        self.default_device = (settings.SPOTIFY_DEFAULT_DEVICE or "").strip() or None
        self.aliases = _parse_aliases(settings.SPOTIFY_DEVICE_ALIASES)
        self.token_cache = os.path.expanduser(settings.SPOTIFY_TOKEN_CACHE)
        self._sp = None  # lazy spotipy client
        # "Now playing" context: a short cache so rapid back-to-back turns don't
        # each hit the API; stale reads fetch live so the answer stays current.
        self._np_value: Optional[str] = None
        self._np_time = 0.0

    # ----- client (lazy, hardened) -----------------------------------------

    def _client(self):
        if self._sp is not None:
            return self._sp
        try:
            # headless-safe (open_browser=False); auth is bootstrapped by the script.
            self._sp = build_spotify_client(self.token_cache, open_browser=False)
        except ImportError as e:
            raise SpotifyToolError("network", "the music library is not installed") from e
        except ValueError as e:
            raise SpotifyToolError("auth-revoked", "the music is not set up yet") from e
        return self._sp

    # ----- device resolution (the multi-speaker piece) ---------------------

    def _live_devices(self) -> list:
        devices = self._client().devices().get("devices", [])
        if not devices:
            raise SpotifyToolError("device-offline", "I don't see any speakers awake right now")
        return devices

    def _resolve_device(self, spoken: Optional[str]) -> tuple:
        """Map a spoken speaker/room name to (device_id, device_name). Falls back
        to the configured default, then the currently-active device."""
        devices = self._live_devices()
        by_name = [(d["name"], d["id"]) for d in devices]

        target = (spoken or "").strip() or self.default_device
        if not target:
            active = next((d for d in devices if d.get("is_active")), devices[0])
            return active["id"], active["name"]

        target = self.aliases.get(target.lower(), target)
        tl = target.lower()

        # exact (case-insensitive)
        for name, did in by_name:
            if name.lower() == tl:
                return did, name
        # containment either direction
        contained = [(n, i) for n, i in by_name if tl in n.lower() or n.lower() in tl]
        if len(contained) == 1:
            name, did = contained[0]
            return did, name
        # Fuzzy match. Within multiple containment hits, rank among them; otherwise
        # rank all devices but require a floor so we don't grab something unrelated.
        pool = contained or by_name
        best_name, best_id, best = None, None, 0.0
        for name, did in pool:
            score = SequenceMatcher(None, tl, name.lower()).ratio()
            if score > best:
                best_name, best_id, best = name, did, score
        if contained or best >= 0.5:
            return best_id, best_name
        raise SpotifyToolError(
            "device-not-found",
            "I couldn't find a speaker called that",
            data={"requested": spoken, "available": [n for n, _ in by_name]},
        )

    # ----- the tools -------------------------------------------------------

    def play(self, query: str, device: Optional[str] = None) -> ToolResult:
        if not (query or "").strip():
            raise SpotifyToolError("bad-args", "what would you like me to play?")
        sp = self._client()
        did, dname = self._resolve_device(device)
        uri, label = self._best_match(sp, query)
        if uri is None:
            raise SpotifyToolError("no-match", "I couldn't find that one")
        if uri.startswith("spotify:track:"):
            sp.start_playback(device_id=did, uris=[uri])
        else:  # playlist / album / artist context
            sp.start_playback(device_id=did, context_uri=uri)
        return ToolResult(True, f"playing {label} on {dname}", suppress_followup=True,
                          data={"track": label, "device": dname})

    def pause(self, device: Optional[str] = None) -> ToolResult:
        did, _ = self._resolve_device(device)
        self._client().pause_playback(device_id=did)
        return ToolResult(True, "paused")

    def resume(self, device: Optional[str] = None) -> ToolResult:
        did, dname = self._resolve_device(device)
        self._client().start_playback(device_id=did)
        return ToolResult(True, f"back on in {dname}", suppress_followup=True)

    def skip(self, device: Optional[str] = None) -> ToolResult:
        did, _ = self._resolve_device(device)
        self._client().next_track(device_id=did)
        return ToolResult(True, "skipped ahead")

    def previous(self, device: Optional[str] = None) -> ToolResult:
        did, _ = self._resolve_device(device)
        self._client().previous_track(device_id=did)
        return ToolResult(True, "going back")

    def set_volume(self, level, device: Optional[str] = None) -> ToolResult:
        try:
            pct = int(level)
        except (TypeError, ValueError):
            raise SpotifyToolError("bad-args", "what volume would you like?")
        pct = max(0, min(_VOLUME_MAX, pct))
        did, _ = self._resolve_device(device)
        self._client().volume(pct, device_id=did)
        return ToolResult(True, f"volume set to {pct}", data={"volume": pct})

    def transfer(self, device: str) -> ToolResult:
        did, dname = self._resolve_device(device)
        self._client().transfer_playback(device_id=did, force_play=True)
        return ToolResult(True, f"moved the music to {dname}", suppress_followup=True,
                          data={"device": dname})

    def now_playing(self, device: Optional[str] = None) -> ToolResult:
        cur = self._client().current_playback()
        if not cur or not cur.get("item"):
            return ToolResult(True, "nothing is playing right now", data={"playing": False})
        item = cur["item"]
        artists = _join_artists(item)
        label = f"{item.get('name', 'something')}" + (f" by {artists}" if artists else "")
        return ToolResult(True, f"now playing {label}", data={"playing": True, "track": label})

    def list_devices(self) -> ToolResult:
        names = [d["name"] for d in self._live_devices()]
        return ToolResult(True, "available speakers: " + ", ".join(names), data={"devices": names})

    # ----- now-playing context (always-on, short-cache live fetch) ---------
    # This deliberately lives on the tool rather than in utils/context_provider
    # (which serves weather/news): now-playing is part of the Spotify capability,
    # reusing this instance's authed client/timeout/error handling, whereas the
    # context providers are env-keyed module singletons the engine doesn't own.

    def now_playing_context(self) -> Optional[str]:
        """A short 'now playing' line for the LLM context, or None when nothing is
        playing / Spotify isn't set up. Fetches live so the answer reflects the
        song that's actually playing; a brief cache only coalesces rapid
        back-to-back turns. The lookup is bounded by the client request timeout
        and is masked by the filler audio that plays during processing."""
        now = time.monotonic()
        if self._np_time and (now - self._np_time) < _NOW_PLAYING_TTL_S:
            return self._np_value              # within the coalescing window
        self._np_value = self._fetch_now_playing()
        self._np_time = now
        return self._np_value

    def _fetch_now_playing(self) -> Optional[str]:
        """Build the now-playing line from current_playback(), or None."""
        try:
            cur = self._client().current_playback()
        except Exception:
            return None
        if not cur or not cur.get("item"):
            return None
        item = cur["item"]
        name = item.get("name") or "something"
        artists = _join_artists(item)
        album = (item.get("album") or {}).get("name")
        parts = [f'"{name}"']
        if artists:
            parts.append(f"by {artists}")
        if album:
            parts.append(f"(album: {album})")
        state = "Now playing" if cur.get("is_playing") else "Paused"
        return f"{state} on Spotify: " + " ".join(parts) + "."

    # ----- helpers ---------------------------------------------------------

    # Words that signal the user wants a vibe/collection, not a specific song.
    _COLLECTION_CUES = ("playlist", "mix", "radio", "music", "songs", "tunes",
                        "vibes", "soundtrack", "station", "essentials")

    @classmethod
    def _best_match(cls, sp, query: str):
        """Search and pick the most apt result. A specific request ('Quiet Village')
        plays the TRACK; only an explicit collection/vibe request ('tiki music',
        'jazz playlist') reaches for a playlist. Returns (uri, label)."""
        res = sp.search(q=query, type=_SEARCH_TYPES, limit=5)
        ql = query.lower()

        def named(items):
            for it in items or []:
                if it and it.get("name"):
                    return it
            return None

        track = named(res.get("tracks", {}).get("items"))
        playlist = named(res.get("playlists", {}).get("items"))
        artist = named(res.get("artists", {}).get("items"))

        def track_choice():
            artists = _join_artists(track)
            return track["uri"], track["name"] + (f" by {artists}" if artists else "")

        wants_collection = any(cue in ql for cue in cls._COLLECTION_CUES)
        # Default to the song; only prefer a playlist for an explicit vibe request.
        if track and not wants_collection:
            return track_choice()
        if playlist:
            return playlist["uri"], f"the {playlist['name']} playlist"
        if track:                       # collection asked for, but no playlist found
            return track_choice()
        if artist:
            return artist["uri"], artist["name"]
        return None, None

    # ----- dispatch + schema (consumed by the conversation engine later) ---

    def dispatch(self, name: str, args: dict) -> ToolResult:
        """Execute a tool by name; convert every failure into a ToolResult."""
        handlers = {
            "music_play": lambda a: self.play(a.get("query", ""), a.get("device")),
            "music_pause": lambda a: self.pause(a.get("device")),
            "music_resume": lambda a: self.resume(a.get("device")),
            "music_skip": lambda a: self.skip(a.get("device")),
            "music_previous": lambda a: self.previous(a.get("device")),
            "music_set_volume": lambda a: self.set_volume(a.get("level"), a.get("device")),
            "music_transfer": lambda a: self.transfer(a.get("device", "")),
            "music_now_playing": lambda a: self.now_playing(a.get("device")),
            "music_list_devices": lambda a: self.list_devices(),
        }
        handler = handlers.get(name)
        if handler is None:
            return ToolResult(False, "I can't do that with the music", kind="bad-args")
        try:
            return handler(args or {})
        except SpotifyToolError as e:
            logger.warning("Spotify tool %s failed (%s)", name, e.kind)
            return ToolResult(False, e.spoken_hint, kind=e.kind, data=e.data)
        except Exception as e:  # spotipy/HTTP errors -> typed, sanitized (no token leakage)
            kind = _classify(e)
            logger.warning("Spotify tool %s failed (%s)", name, kind)
            return ToolResult(False, _SPOKEN.get(kind, "the music isn't responding"), kind=kind)


def _classify(exc: Exception) -> str:
    """Map a spotipy/requests exception to the error taxonomy WITHOUT logging the
    raw exception (which can carry Authorization headers)."""
    status = getattr(exc, "http_status", None)
    reason = (str(getattr(exc, "reason", "")) or "").upper()
    if status == 403:
        return "not-premium"
    if status == 404 or "NO_ACTIVE_DEVICE" in reason:
        return "device-offline"
    if status == 429:
        return "rate-limited"
    if status in (401,) or "invalid_grant" in str(exc).lower():
        return "auth-revoked"
    return "network"


_SPOKEN = {
    "not-premium": "the music needs a Premium account",
    "device-offline": "I don't see any speakers awake right now",
    "rate-limited": "the music is busy, try again in a moment",
    "auth-revoked": "I've lost my connection to the music",
    "network": "I can't reach the music right now",
}


# OpenAI tool schemas (consumed by the conversation engine). Built with a small
# helper so the repeated function envelope and the optional `device` property
# aren't copy-pasted nine times.
_DEVICE_PROP = {"device": {"type": "string", "description": "speaker/room (optional)"}}


def _tool(name, description, properties=None, required=None):
    fn = {"name": name, "description": description,
          "parameters": {"type": "object", "properties": properties or {}}}
    if required:
        fn["parameters"]["required"] = required
    return {"type": "function", "function": fn}


OPENAI_TOOLS = [
    _tool("music_play",
          "Play music on Spotify. Use for 'play <song/artist/playlist/genre>'. "
          "Optionally on a specific speaker/room.",
          {"query": {"type": "string", "description": "what to play, e.g. 'tiki music' or 'Quiet Village'"},
           **_DEVICE_PROP}, required=["query"]),
    _tool("music_pause", "Pause playback.", _DEVICE_PROP),
    _tool("music_resume", "Resume paused playback.", _DEVICE_PROP),
    _tool("music_skip", "Skip to the next track.", _DEVICE_PROP),
    _tool("music_previous", "Go to the previous track.", _DEVICE_PROP),
    _tool("music_set_volume", "Set the MUSIC volume (0-100), not the character's own voice.",
          {"level": {"type": "integer", "description": "0-100"}, **_DEVICE_PROP}, required=["level"]),
    _tool("music_transfer", "Move the current music to a different speaker/room.",
          {"device": {"type": "string", "description": "destination speaker/room"}}, required=["device"]),
    _tool("music_now_playing", "Ask what song is currently playing."),
    _tool("music_list_devices", "List the available Spotify speakers/rooms."),
]
