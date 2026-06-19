"""Unit tests for the Spotify playback tool (spotipy fully mocked, no network)."""

import time

import pytest

from jf_sebastian.modules.spotify_tool import (
    SpotifyTool, SCOPES, OPENAI_TOOLS, _parse_aliases, _classify, _VOLUME_MAX,
)


class FakeSpotifyException(Exception):
    def __init__(self, http_status, reason=""):
        super().__init__("fake spotify error")
        self.http_status = http_status
        self.reason = reason


class FakeSpotify:
    """Minimal stand-in for spotipy.Spotify; records calls, can raise per-method."""

    def __init__(self, devices=None, search_result=None, playback=None, raise_on=None):
        self._devices = devices if devices is not None else [
            {"name": "Living Room", "id": "d1", "type": "Speaker", "is_active": True},
            {"name": "Kitchen Echo", "id": "d2", "type": "Speaker", "is_active": False},
        ]
        self._search = search_result
        self._playback = playback
        self._raise = raise_on or {}
        self.calls = []

    def _maybe(self, m):
        if m in self._raise:
            raise self._raise[m]

    def devices(self):
        self._maybe("devices")
        return {"devices": self._devices}

    def start_playback(self, device_id=None, uris=None, context_uri=None):
        self._maybe("start_playback")
        self.calls.append(("start_playback", device_id, uris, context_uri))

    def pause_playback(self, device_id=None):
        self.calls.append(("pause", device_id))

    def next_track(self, device_id=None):
        self.calls.append(("next", device_id))

    def previous_track(self, device_id=None):
        self.calls.append(("prev", device_id))

    def volume(self, pct, device_id=None):
        self.calls.append(("volume", pct, device_id))

    def transfer_playback(self, device_id, force_play=True):
        self.calls.append(("transfer", device_id))

    def current_playback(self, *a, **k):
        self._maybe("current_playback")
        return self._playback

    def search(self, q, type=None, limit=None):
        return self._search or {"tracks": {"items": []}, "playlists": {"items": []},
                                "artists": {"items": []}, "albums": {"items": []}}


def make_tool(fake, default=None, aliases=None):
    t = SpotifyTool()
    t._sp = fake               # bypass real auth
    t.default_device = default
    t.aliases = aliases or {}
    return t


# ----- device resolution ---------------------------------------------------

def test_resolve_exact_case_insensitive():
    t = make_tool(FakeSpotify())
    assert t._resolve_device("living room") == ("d1", "Living Room")


def test_resolve_substring():
    t = make_tool(FakeSpotify())
    assert t._resolve_device("kitchen") == ("d2", "Kitchen Echo")


def test_resolve_alias():
    t = make_tool(FakeSpotify(), aliases={"den": "Living Room"})
    assert t._resolve_device("den") == ("d1", "Living Room")


def test_resolve_default_when_unspecified():
    t = make_tool(FakeSpotify(), default="kitchen echo")
    assert t._resolve_device(None) == ("d2", "Kitchen Echo")


def test_resolve_active_when_no_preference():
    t = make_tool(FakeSpotify())  # no default; Living Room is_active
    assert t._resolve_device(None) == ("d1", "Living Room")


def test_resolve_no_match_lists_available():
    t = make_tool(FakeSpotify())
    res = t.dispatch("music_play", {"query": "x", "device": "garage"})
    assert not res.ok and res.kind == "device-not-found"
    assert "Living Room" in res.data["available"]


def test_resolve_no_devices_offline():
    res = make_tool(FakeSpotify(devices=[])).dispatch("music_pause", {})
    assert not res.ok and res.kind == "device-offline"


# ----- play / search selection ---------------------------------------------

def test_play_track_uses_uris():
    fake = FakeSpotify(search_result={
        "tracks": {"items": [{"name": "Quiet Village", "uri": "spotify:track:t1",
                              "artists": [{"name": "Martin Denny"}]}]},
        "playlists": {"items": []}, "artists": {"items": []}, "albums": {"items": []}})
    res = make_tool(fake).dispatch("music_play", {"query": "quiet village"})
    assert res.ok and res.suppress_followup  # play declares it started music
    assert ("start_playback", "d1", ["spotify:track:t1"], None) in fake.calls
    assert "Quiet Village" in res.spoken_hint


def test_play_prefers_named_playlist_for_vibe():
    fake = FakeSpotify(search_result={
        "playlists": {"items": [{"name": "Tiki Lounge", "uri": "spotify:playlist:p1"}]},
        "tracks": {"items": [{"name": "Some Song", "uri": "spotify:track:t1", "artists": []}]},
        "artists": {"items": []}, "albums": {"items": []}})
    res = make_tool(fake).dispatch("music_play", {"query": "tiki music"})
    assert res.ok
    assert ("start_playback", "d1", None, "spotify:playlist:p1") in fake.calls


def test_play_specific_song_beats_competing_playlist():
    # Regression: a named song must not lose to a playlist that merely shares a word.
    fake = FakeSpotify(search_result={
        "tracks": {"items": [{"name": "Quiet Village", "uri": "spotify:track:t1",
                              "artists": [{"name": "Martin Denny"}]}]},
        "playlists": {"items": [{"name": "Quiet Storm", "uri": "spotify:playlist:p9"}]},
        "artists": {"items": []}, "albums": {"items": []}})
    res = make_tool(fake).dispatch("music_play", {"query": "quiet village"})
    assert res.ok
    assert ("start_playback", "d1", ["spotify:track:t1"], None) in fake.calls


def test_play_empty_query_bad_args():
    res = make_tool(FakeSpotify()).dispatch("music_play", {"query": "  "})
    assert not res.ok and res.kind == "bad-args"


def test_play_no_match():
    res = make_tool(FakeSpotify()).dispatch("music_play", {"query": "zzz"})
    assert not res.ok and res.kind == "no-match"


# ----- controls ------------------------------------------------------------

def test_volume_clamped_to_max():
    fake = FakeSpotify()
    res = make_tool(fake).dispatch("music_set_volume", {"level": 100})
    assert res.ok and ("volume", _VOLUME_MAX, "d1") in fake.calls


def test_volume_non_numeric_bad_args():
    res = make_tool(FakeSpotify()).dispatch("music_set_volume", {"level": "loud"})
    assert not res.ok and res.kind == "bad-args"


def test_now_playing_idle():
    res = make_tool(FakeSpotify(playback=None)).dispatch("music_now_playing", {})
    assert res.ok and res.data["playing"] is False


def test_now_playing_active():
    pb = {"item": {"name": "Aloha Oe", "artists": [{"name": "Don Ho"}]}}
    res = make_tool(FakeSpotify(playback=pb)).dispatch("music_now_playing", {})
    assert res.ok and "Aloha Oe" in res.spoken_hint


def test_list_devices():
    res = make_tool(FakeSpotify()).dispatch("music_list_devices", {})
    assert res.ok and res.data["devices"] == ["Living Room", "Kitchen Echo"]


# ----- now-playing context (always-on, cached, non-blocking) ----------------

def _np(name="Quiet Village", artists=("Martin Denny",), album="Exotica", playing=True):
    return {"is_playing": playing,
            "item": {"name": name,
                     "artists": [{"name": a} for a in artists],
                     "album": {"name": album} if album else {}}}


def test_now_playing_context_fetch_playing():
    t = make_tool(FakeSpotify(playback=_np()))
    assert t._fetch_now_playing() == 'Now playing on Spotify: "Quiet Village" by Martin Denny (album: Exotica).'


def test_now_playing_context_paused():
    t = make_tool(FakeSpotify(playback=_np(playing=False)))
    assert t._fetch_now_playing().startswith("Paused on Spotify:")


def test_now_playing_context_no_album():
    t = make_tool(FakeSpotify(playback=_np(album=None)))
    assert t._fetch_now_playing() == 'Now playing on Spotify: "Quiet Village" by Martin Denny.'


def test_now_playing_context_nothing_playing():
    assert make_tool(FakeSpotify(playback=None))._fetch_now_playing() is None


def test_now_playing_context_error_returns_none():
    fake = FakeSpotify(raise_on={"current_playback": FakeSpotifyException(500)})
    assert make_tool(fake)._fetch_now_playing() is None


def test_now_playing_context_returns_fresh_cache():
    t = make_tool(FakeSpotify())
    t._np_value = 'Now playing on Spotify: "X" by A.'
    t._np_time = time.monotonic()
    assert t.now_playing_context() == 'Now playing on Spotify: "X" by A.'


def test_now_playing_context_cold_is_nonblocking_none():
    # cold read returns the cached value (None) immediately and refreshes in the bg
    assert make_tool(FakeSpotify(playback=None)).now_playing_context() is None


def test_transfer():
    fake = FakeSpotify()
    res = make_tool(fake).dispatch("music_transfer", {"device": "kitchen"})
    assert res.ok and ("transfer", "d2") in fake.calls


def test_unknown_tool():
    res = make_tool(FakeSpotify()).dispatch("music_explode", {})
    assert not res.ok and res.kind == "bad-args"


# ----- error taxonomy ------------------------------------------------------

@pytest.mark.parametrize("status,kind", [
    (403, "not-premium"), (404, "device-offline"), (429, "rate-limited"),
    (401, "auth-revoked"), (500, "network"),
])
def test_dispatch_error_taxonomy(status, kind):
    fake = FakeSpotify(raise_on={"devices": FakeSpotifyException(status)})
    res = make_tool(fake).dispatch("music_skip", {})
    assert not res.ok and res.kind == kind
    assert res.spoken_hint  # always something to say


def test_classify_no_active_device_reason():
    assert _classify(FakeSpotifyException(404, "NO_ACTIVE_DEVICE")) == "device-offline"


# ----- invariants ----------------------------------------------------------

def test_scopes_are_exactly_minimal():
    # Lock: a future edit must not silently widen account access.
    assert set(SCOPES.split()) == {"user-read-playback-state", "user-modify-playback-state"}


def test_schema_matches_handlers():
    tool_names = {t["function"]["name"] for t in OPENAI_TOOLS}
    assert tool_names == {
        "music_play", "music_pause", "music_resume", "music_skip", "music_previous",
        "music_set_volume", "music_transfer", "music_now_playing", "music_list_devices",
    }


def test_parse_aliases():
    assert _parse_aliases("kitchen=Kitchen Echo, den = Living Room") == {
        "kitchen": "Kitchen Echo", "den": "Living Room"}
    assert _parse_aliases(None) == {}
    assert _parse_aliases("garbage") == {}
