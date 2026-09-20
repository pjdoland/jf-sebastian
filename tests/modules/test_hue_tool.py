"""Unit tests for the Philips Hue light tool (Bridge HTTP fully mocked, no network).

Fixture names here are deliberately generic ("Living Room", "Desk Lamp") rather
than any real installation's room names.
"""

import json

import pytest
import requests

from jf_sebastian.modules import hue_tool as hue_mod

from jf_sebastian.modules.hue_tool import (
    HueTool, HueToolError, OPENAI_TOOLS, _COLORS, _ALL_LIGHTS_GROUP,
    _clamp_brightness, _adapt_fragment, _is_noise_scene, _normalize,
)


# LWB014 is a White bulb: state has on/bri but no hue/sat.
# LCA003 is a White & Colour bulb: state includes hue/sat.
WHITE_STATE = {"on": True, "bri": 200, "reachable": True}
# White Ambiance: colour temperature but no hue channel.
AMBIANCE_STATE = {"on": True, "bri": 200, "ct": 300, "reachable": True}
COLOR_STATE = {"on": True, "bri": 200, "hue": 8000, "sat": 140, "ct": 300, "reachable": True}

LIGHTS = {
    "1": {"name": "Floor Lamp", "modelid": "LWB014", "state": dict(WHITE_STATE)},
    "2": {"name": "Desk Lamp", "modelid": "LWB014", "state": dict(WHITE_STATE)},
    "3": {"name": "Reading Lamp", "modelid": "LCA003", "state": dict(COLOR_STATE)},
    "4": {"name": "Corner Lamp", "modelid": "LCA003", "state": dict(COLOR_STATE)},
    "5": {"name": "Hall Ceiling", "modelid": "LTW010", "state": dict(AMBIANCE_STATE)},
    "6": {"name": "Kid's Room Lamp", "modelid": "LWB014", "state": dict(WHITE_STATE)},
}

GROUPS = {
    "1": {"name": "Living Room", "type": "Room", "class": "Living room", "lights": ["1", "3"]},
    "2": {"name": "Study", "type": "Room", "class": "Office", "lights": ["2"]},
    "3": {"name": "Downstairs", "type": "Zone", "lights": ["1", "2", "3"]},
    "4": {"name": "Hall", "type": "Room", "lights": ["5"]},
    "5": {"name": "Empty Room", "type": "Room", "lights": []},
    # Stored with a curly apostrophe, as the Hue app writes it.
    "6": {"name": "Kid\u2019s Room", "type": "Room", "lights": ["6"]},
}

SCENES = {
    "s1": {"name": "Relax", "group": "1"},
    "s2": {"name": "Concentrate", "group": "2"},
    "s3": {"name": "Relax", "group": "2"},
    # Hue app bookkeeping -- must never be offered to the model.
    "s4": {"name": "Scene scene0 ", "group": "1"},
    "s5": {"name": "Scene previous ", "group": "1"},
    "s6": {"name": "Scene storageScene ", "group": "1"},
    # Same bookkeeping, as other Hue app versions write it (no space).
    "s7": {"name": "storageScene", "group": "1"},
    "s8": {"name": "ScenePrevious", "group": "2"},
}


class FakeBridge:
    """Records writes; serves the inventory above. Can raise per-path."""

    def __init__(self, raise_on=None, error_payload=None):
        self.writes = []
        self.reads = []
        self._raise = raise_on or {}
        self._error_payload = error_payload

    def __call__(self, method, url, json=None, timeout=None):
        path = url.split("/api/")[1].split("/", 1)[1]
        if path in self._raise:
            raise self._raise[path]
        if method == "GET":
            self.reads.append(path)
            body = {"lights": LIGHTS, "groups": GROUPS, "scenes": SCENES}[path]
            return FakeResponse(body)
        self.writes.append((path, json))
        if self._error_payload is not None:
            return FakeResponse(self._error_payload)
        return FakeResponse([{"success": {path: json}}])


class FakeResponse:
    def __init__(self, payload, raise_http=None):
        self._payload = payload
        self._raise_http = raise_http

    def raise_for_status(self):
        if self._raise_http:
            raise self._raise_http

    def json(self):
        return self._payload


@pytest.fixture
def tool(tmp_path, monkeypatch):
    """A HueTool wired to a fake Bridge and a temp credential file."""
    creds = tmp_path / "hue.json"
    creds.write_text(json.dumps({"bridge_ip": "10.0.0.5", "username": "abc123"}))
    monkeypatch.setattr("jf_sebastian.config.settings.HUE_TOKEN_CACHE", str(creds))
    monkeypatch.setattr("jf_sebastian.config.settings.HUE_BRIDGE_HOST", None)
    t = HueTool()
    bridge = FakeBridge()
    monkeypatch.setattr(hue_mod._SESSION, "request", bridge)
    t.bridge = bridge          # test handle, not used by production code
    return t


# ----- target resolution -------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("spoken,expected", [
    ("Living Room", ("group", "1", "Living Room")),      # exact room
    ("living room", ("group", "1", "Living Room")),      # case-insensitive
    ("living", ("group", "1", "Living Room")),           # containment -> room
    ("Desk Lamp", ("light", "2", "Desk Lamp")),          # exact bulb
    ("desk", ("light", "2", "Desk Lamp")),               # containment -> bulb
    ("Downstairs", ("group", "3", "Downstairs")),        # zone
    ("study", ("group", "2", "Study")),
])
def test_resolve_target_matches(tool, spoken, expected):
    assert tool._resolve_target(spoken) == expected


@pytest.mark.unit
@pytest.mark.parametrize("spoken", [None, "", "  ", "all", "everything", "all the lights"])
def test_resolve_target_defaults_to_all_lights(tool, spoken):
    kind, rid, name = tool._resolve_target(spoken)
    assert (kind, rid) == ("group", _ALL_LIGHTS_GROUP)
    assert name == "all the lights"


@pytest.mark.unit
def test_rooms_are_searched_before_bulbs(tool):
    """A room must win over a bulb when both could match, so 'the study' doesn't
    lose to a lamp whose name happens to contain the word."""
    kind, _, name = tool._resolve_target("Study")
    assert (kind, name) == ("group", "Study")


@pytest.mark.unit
def test_resolve_target_unknown_raises_not_found(tool):
    with pytest.raises(HueToolError) as exc:
        tool._resolve_target("garage")
    assert exc.value.kind == "not-found"
    # The failure carries what IS available, for logging/debugging.
    assert "Living Room" in exc.value.data["rooms"]
    assert "Desk Lamp" in exc.value.data["lights"]


# ----- colour parsing ----------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("spoken,resolved", [
    ("red", "red"),
    ("RED", "red"),
    ("  blue  ", "blue"),
    ("bright red", "red"),                # adjective ignored
    ("warm white", "warm white"),
    ("a nice warm white", "warm white"),  # multi-word beats bare "white"
    ("cool white", "cool white"),
])
def test_color_resolves(tool, spoken, resolved):
    r = tool.dispatch("lights_color", {"color": spoken, "target": "Reading Lamp"})
    assert r.ok, r.spoken_hint
    assert r.data["color"] == resolved


@pytest.mark.unit
@pytest.mark.parametrize("spoken", ["ultraviolet", "greenish", "blueberry",
                                    "redacted", "chartreuse", "", "   "])
def test_color_rejects_non_colors(tool, spoken):
    """Regression: a substring test read 'ultraviolet' as violet and silently
    succeeded. Matching is whole-word, so these must all be rejected."""
    r = tool.dispatch("lights_color", {"color": spoken, "target": "Reading Lamp"})
    assert not r.ok
    assert r.kind == "bad-args"


@pytest.mark.unit
def test_color_writes_expected_state(tool):
    tool.dispatch("lights_color", {"color": "red", "target": "Reading Lamp"})
    path, body = tool.bridge.writes[-1]
    assert path == "lights/3/state"
    assert body == {"on": True, **_COLORS["red"]}


# ----- bulb capability ---------------------------------------------------

@pytest.mark.unit
def test_adapt_fragment_per_bulb_tier():
    hue_frag, ct_frag = _COLORS["red"], _COLORS["warm white"]
    # Full colour bulb takes both.
    assert _adapt_fragment({"state": COLOR_STATE}, hue_frag) == hue_frag
    assert _adapt_fragment({"state": COLOR_STATE}, ct_frag) == ct_frag
    # White Ambiance: no hue channel, but colour temperature works. The sat key
    # is dropped because a ct-only bulb rejects it.
    assert _adapt_fragment({"state": AMBIANCE_STATE}, hue_frag) is None
    assert _adapt_fragment({"state": AMBIANCE_STATE}, ct_frag) == {"ct": ct_frag["ct"]}
    # Plain White: neither.
    assert _adapt_fragment({"state": WHITE_STATE}, hue_frag) is None
    assert _adapt_fragment({"state": WHITE_STATE}, ct_frag) is None
    assert _adapt_fragment({}, hue_frag) is None


@pytest.mark.unit
def test_color_on_white_only_bulb_degrades(tool):
    r = tool.dispatch("lights_color", {"color": "blue", "target": "Desk Lamp"})
    assert not r.ok
    assert r.kind == "no-color"
    assert "can't change" in r.spoken_hint
    assert tool.bridge.writes == []          # nothing was sent to the Bridge


@pytest.mark.unit
def test_color_on_white_only_room_degrades(tool):
    """Study contains only the White Desk Lamp."""
    r = tool.dispatch("lights_color", {"color": "blue", "target": "Study"})
    assert not r.ok and r.kind == "no-color"


@pytest.mark.unit
def test_color_on_mixed_room_colors_only_capable_bulbs(tool):
    """Living Room holds White 'Floor Lamp' (1) and colour 'Reading Lamp' (3).
    Only the colour-capable one is written, and the result says so."""
    r = tool.dispatch("lights_color", {"color": "green", "target": "Living Room"})
    assert r.ok
    assert r.data["partial"] is True
    written = [p for p, _ in tool.bridge.writes]
    assert written == ["lights/3/state"]


@pytest.mark.unit
def test_color_on_all_capable_room_uses_group_action(tool):
    """A fully colour-capable target is written once as a group action rather
    than bulb-by-bulb."""
    GROUPS["9"] = {"name": "Lounge", "type": "Room", "lights": ["3", "4"]}
    try:
        r = tool.dispatch("lights_color", {"color": "purple", "target": "Lounge"})
        assert r.ok and r.data["partial"] is False
        assert tool.bridge.writes == [("groups/9/action", {"on": True, **_COLORS["purple"]})]
    finally:
        del GROUPS["9"]


# ----- brightness --------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("pct,expected", [(1, 3), (50, 127), (100, 254)])
def test_clamp_brightness_maps_percent_to_hue_range(pct, expected):
    assert _clamp_brightness(pct) == pytest.approx(expected, abs=2)


@pytest.mark.unit
@pytest.mark.parametrize("pct", [-50, 0, 150, 1000])
def test_clamp_brightness_stays_in_range(pct):
    assert 1 <= _clamp_brightness(pct) <= 254


@pytest.mark.unit
def test_brightness_zero_turns_off(tool):
    r = tool.dispatch("lights_brightness", {"level": 0, "target": "Desk Lamp"})
    assert r.ok and r.data["brightness"] == 0
    assert tool.bridge.writes[-1] == ("lights/2/state", {"on": False})


@pytest.mark.unit
def test_brightness_turns_on_and_sets_level(tool):
    r = tool.dispatch("lights_brightness", {"level": 40, "target": "Desk Lamp"})
    assert r.ok
    path, body = tool.bridge.writes[-1]
    assert path == "lights/2/state"
    assert body["on"] is True and 1 <= body["bri"] <= 254


@pytest.mark.unit
@pytest.mark.parametrize("level", ["loud", None, "", {}])
def test_brightness_bad_arg(tool, level):
    r = tool.dispatch("lights_brightness", {"level": level, "target": "Desk Lamp"})
    assert not r.ok and r.kind == "bad-args"


# ----- on / off ----------------------------------------------------------

@pytest.mark.unit
def test_on_off_write_group_action_for_rooms(tool):
    tool.dispatch("lights_on", {"target": "Living Room"})
    assert tool.bridge.writes[-1] == ("groups/1/action", {"on": True})
    tool.dispatch("lights_off", {"target": "Living Room"})
    assert tool.bridge.writes[-1] == ("groups/1/action", {"on": False})


@pytest.mark.unit
def test_on_with_no_target_hits_all_lights_group(tool):
    tool.dispatch("lights_on", {})
    assert tool.bridge.writes[-1] == (f"groups/{_ALL_LIGHTS_GROUP}/action", {"on": True})


# ----- scenes ------------------------------------------------------------

@pytest.mark.unit
def test_scene_noise_is_filtered(tool):
    names = tool._scene_names()
    assert names == ["Concentrate", "Relax"]
    assert not any("storageScene" in n or n.startswith("Scene ") for n in names)


@pytest.mark.unit
def test_scene_list_excludes_noise_from_tool_result(tool):
    r = tool.dispatch("lights_list", {})
    assert r.ok
    assert "Scene scene0 " not in r.data["scenes"]


@pytest.mark.unit
def test_scene_activates_by_name(tool):
    r = tool.dispatch("lights_scene", {"scene": "Concentrate"})
    assert r.ok
    path, body = tool.bridge.writes[-1]
    assert path == "groups/2/action" and body == {"scene": "s2"}


@pytest.mark.unit
def test_scene_prefers_the_copy_stored_for_the_named_room(tool):
    """'Relax' exists for both Living Room (s1) and Study (s3); naming the room
    must pick that room's stored copy."""
    r = tool.dispatch("lights_scene", {"scene": "Relax", "target": "Study"})
    assert r.ok
    assert tool.bridge.writes[-1] == ("groups/2/action", {"scene": "s3"})


@pytest.mark.unit
def test_scene_unknown(tool):
    r = tool.dispatch("lights_scene", {"scene": "Disco Inferno"})
    assert not r.ok and r.kind == "not-found"
    assert "Relax" in r.data["known"]


@pytest.mark.unit
def test_scene_requires_a_name(tool):
    assert tool.dispatch("lights_scene", {"scene": ""}).kind == "bad-args"


# ----- credentials + transport errors ------------------------------------

@pytest.mark.unit
def test_missing_credentials_is_not_paired(tmp_path, monkeypatch):
    monkeypatch.setattr("jf_sebastian.config.settings.HUE_TOKEN_CACHE",
                        str(tmp_path / "absent.json"))
    r = HueTool().dispatch("lights_on", {})
    assert not r.ok and r.kind == "not-paired"


@pytest.mark.unit
def test_credential_without_username_is_not_paired(tmp_path, monkeypatch):
    creds = tmp_path / "hue.json"
    creds.write_text(json.dumps({"bridge_ip": "10.0.0.5"}))
    monkeypatch.setattr("jf_sebastian.config.settings.HUE_TOKEN_CACHE", str(creds))
    r = HueTool().dispatch("lights_on", {})
    assert not r.ok and r.kind == "not-paired"


@pytest.mark.unit
def test_bridge_host_override_wins_over_cached_ip(tmp_path, monkeypatch):
    creds = tmp_path / "hue.json"
    creds.write_text(json.dumps({"bridge_ip": "10.0.0.5", "username": "abc"}))
    monkeypatch.setattr("jf_sebastian.config.settings.HUE_TOKEN_CACHE", str(creds))
    monkeypatch.setattr("jf_sebastian.config.settings.HUE_BRIDGE_HOST", "10.0.0.99")
    t = HueTool()
    assert "10.0.0.99" in t._url("lights")


@pytest.mark.unit
def test_unreachable_bridge_degrades(tool, monkeypatch):
    monkeypatch.setattr(hue_mod._SESSION, "request",
                        FakeBridge(raise_on={"lights": requests.ConnectionError("down")}))
    r = tool.dispatch("lights_on", {"target": "Living Room"})
    assert not r.ok and r.kind == "bridge-unreachable"


@pytest.mark.unit
def test_revoked_username_maps_to_not_paired(tool, monkeypatch):
    """Hue error type 1 is 'unauthorized user' -- the credential was deleted."""
    monkeypatch.setattr(hue_mod._SESSION, "request", FakeBridge(
        error_payload=[{"error": {"type": 1, "description": "unauthorized user"}}]))
    r = tool.dispatch("lights_on", {"target": "Living Room"})
    assert not r.ok and r.kind == "not-paired"


@pytest.mark.unit
def test_other_bridge_error_maps_to_network(tool, monkeypatch):
    monkeypatch.setattr(hue_mod._SESSION, "request", FakeBridge(
        error_payload=[{"error": {"type": 7, "description": "invalid value"}}]))
    r = tool.dispatch("lights_on", {"target": "Living Room"})
    assert not r.ok and r.kind == "network"


# ----- inventory caching -------------------------------------------------

@pytest.mark.unit
def test_inventory_is_cached_across_calls(tool):
    tool.dispatch("lights_on", {"target": "Living Room"})
    first = len(tool.bridge.reads)
    tool.dispatch("lights_off", {"target": "Living Room"})
    assert len(tool.bridge.reads) == first      # no re-read within the TTL


@pytest.mark.unit
def test_inventory_refetches_after_ttl(tool, monkeypatch):
    tool.dispatch("lights_on", {"target": "Living Room"})
    first = len(tool.bridge.reads)
    monkeypatch.setattr("jf_sebastian.modules.hue_tool._INVENTORY_TTL_S", -1)
    tool._inv_time = 0
    tool.dispatch("lights_on", {"target": "Living Room"})
    assert len(tool.bridge.reads) > first


# ----- dispatch + schema -------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("name,claimed", [
    ("lights_on", True), ("lights_color", True), ("lights_list", True),
    ("music_play", False), ("", False), (None, False),
])
def test_handles_claims_only_its_namespace(tool, name, claimed):
    assert tool.handles(name) is claimed


@pytest.mark.unit
def test_dispatch_unknown_tool_name(tool):
    r = tool.dispatch("lights_teleport", {})
    assert not r.ok and r.kind == "bad-args"


@pytest.mark.unit
def test_dispatch_tolerates_none_args(tool):
    assert tool.dispatch("lights_on", None).ok


@pytest.mark.unit
def test_every_schema_is_claimed_and_dispatchable(tool):
    """No schema may advertise a tool that dispatch doesn't implement. Calling
    with empty args may legitimately fail on a missing required argument, but it
    must never fall through to the unknown-tool branch."""
    unknown_hint = tool.dispatch("lights_does_not_exist", {}).spoken_hint
    for spec in OPENAI_TOOLS:
        name = spec["function"]["name"]
        assert tool.handles(name), f"{name} not claimed by handles()"
        assert tool.dispatch(name, {}).spoken_hint != unknown_hint, \
            f"{name} is advertised but has no handler"


@pytest.mark.unit
def test_schema_shape():
    names = {s["function"]["name"] for s in OPENAI_TOOLS}
    assert names == {"lights_on", "lights_off", "lights_brightness",
                     "lights_color", "lights_scene", "lights_list"}
    for spec in OPENAI_TOOLS:
        assert spec["type"] == "function"
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        for req in params.get("required", []):
            assert req in params["properties"], f"{spec['function']['name']}: {req}"


@pytest.mark.unit
def test_list_lights_reports_inventory(tool):
    r = tool.dispatch("lights_list", {})
    assert r.ok
    assert "Living Room" in r.data["rooms"]
    assert "Desk Lamp" in r.data["lights"]


# ----- regressions from the xhigh review ---------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("name,noise", [
    ("Scene storageScene ", True), ("storageScene", True),
    ("Scene previous ", True), ("ScenePrevious", True),
    ("Scene scene0 ", True), ("scenescene1", True),
    ("Relax", False), ("Concentrate", False),
    ("Scene Setter", False),       # a legitimately named scene must survive
    ("Previous", False), ("", False),
])
def test_noise_scene_matches_both_app_spellings(name, noise):
    assert _is_noise_scene(name) is noise


@pytest.mark.unit
def test_scene_names_exclude_every_bookkeeping_form(tool):
    assert tool._scene_names() == ["Concentrate", "Relax"]


@pytest.mark.unit
def test_white_ambiance_bulb_keeps_color_temperature(tool):
    """LTW bulbs have ct but no hue channel. Rejecting them as 'can't change
    colour' would lose every white on a White Ambiance install."""
    r = tool.dispatch("lights_color", {"color": "warm white", "target": "Hall Ceiling"})
    assert r.ok, r.spoken_hint
    path, body = tool.bridge.writes[-1]
    assert path == "lights/5/state"
    assert body == {"on": True, "ct": _COLORS["warm white"]["ct"]}   # sat dropped
    assert "sat" not in body


@pytest.mark.unit
def test_white_ambiance_bulb_still_rejects_hues(tool):
    r = tool.dispatch("lights_color", {"color": "red", "target": "Hall Ceiling"})
    assert not r.ok and r.kind == "no-color"


@pytest.mark.unit
def test_empty_room_is_not_reported_as_colourless(tool):
    """An unassigned room must not tell the user their colour bulbs are
    white-only -- those are different conditions."""
    r = tool.dispatch("lights_color", {"color": "red", "target": "Empty Room"})
    assert not r.ok
    assert r.kind == "not-found"
    assert "no lights in" in r.spoken_hint


@pytest.mark.unit
def test_curly_apostrophe_room_beats_a_straight_apostrophe_bulb(tool):
    """The Hue app stores U+2019; the model emits '. Without folding, the room
    fails exact+containment and the bulb wins, breaking rooms-before-bulbs."""
    kind, rid, name = tool._resolve_target("Kid's Room")
    assert (kind, rid) == ("group", "6")
    assert name == "Kid’s Room"


@pytest.mark.unit
def test_ambiguous_room_does_not_fall_through_to_a_bulb(tool):
    """Two rooms contain 'room'; the tier must rank within its own hits rather
    than discard them and let the bulb tier answer."""
    kind, _, _ = tool._resolve_target("room")
    assert kind == "group"


@pytest.mark.unit
def test_scene_on_a_single_bulb_is_refused(tool):
    """A scene is whole-room state. Applying one because a bulb was named would
    change every other light in that room while reporting only the bulb."""
    r = tool.dispatch("lights_scene", {"scene": "Relax", "target": "Reading Lamp"})
    assert not r.ok and r.kind == "bad-args"
    assert tool.bridge.writes == []


@pytest.mark.unit
def test_scene_not_stored_for_the_named_room_is_refused(tool):
    """'Concentrate' exists only for Study. Asking for it in the Living Room
    must not write Study's scene id against the Living Room group."""
    r = tool.dispatch("lights_scene", {"scene": "Concentrate", "target": "Living Room"})
    assert not r.ok and r.kind == "not-found"
    assert tool.bridge.writes == []


@pytest.mark.unit
def test_brightness_data_records_what_was_applied(tool):
    r = tool.dispatch("lights_brightness", {"level": 500, "target": "Reading Lamp"})
    assert r.ok
    assert r.data["brightness"] == 100      # applied, not requested
    assert r.data["requested"] == 500
    assert tool.bridge.writes[-1][1]["bri"] == 254


@pytest.mark.unit
def test_list_lights_speaks_scenes_not_just_data(tool):
    """Only spoken_hint reaches the user; the engine discards `data`."""
    r = tool.dispatch("lights_list", {})
    assert "scenes:" in r.spoken_hint
    assert "Relax" in r.spoken_hint


@pytest.mark.unit
def test_list_lights_truncates_long_lists_for_tts(tool, monkeypatch):
    monkeypatch.setattr(hue_mod, "_MAX_SPOKEN_NAMES", 2)
    r = tool.dispatch("lights_list", {})
    assert "more" in r.spoken_hint
    assert len(r.data["lights"]) > 2          # full list still in data


@pytest.mark.unit
def test_revoked_credential_drops_caches_so_repair_takes_effect(tool, monkeypatch):
    tool._inventory()                                     # warm both caches
    assert tool._creds_cache is not None and tool._inv is not None
    monkeypatch.setattr(hue_mod._SESSION, "request", FakeBridge(
        error_payload=[{"error": {"type": 1, "description": "unauthorized user"}}]))
    r = tool.dispatch("lights_on", {"target": "Living Room"})
    assert not r.ok and r.kind == "not-paired"
    assert tool._creds_cache is None and tool._inv is None


@pytest.mark.unit
def test_normalize_folds_apostrophes_and_case():
    assert _normalize("Kid’s Room") == _normalize("KID'S ROOM") == "kid's room"
    assert _normalize(None) == ""
