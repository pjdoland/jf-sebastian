"""Unit tests for the shared tool-provider scaffolding."""

import pytest

from jf_sebastian.modules.tool_provider import (
    ToolError, ToolProvider, ToolResult, fold, resolve_by_name, tool_schema,
)


# ----- fold --------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("Living Room", "living room"),
    ("  LIVING   Room  ", "living room"),      # case + collapsed whitespace
    ("Kid’s Room", "kid's room"),         # curly -> straight
    ("Kid‘s Room", "kid's room"),
    ("Kid's Room", "kid's room"),
    (None, ""),
    ("", ""),
])
def test_fold(raw, expected):
    assert fold(raw) == expected


@pytest.mark.unit
def test_fold_makes_apostrophe_variants_equal():
    assert fold("Kid’s Room") == fold("Kid's Room")


# ----- resolve_by_name ---------------------------------------------------

ROOMS = [("g1", "Living Room"), ("g2", "Study"), ("g3", "Kid’s Room")]
LIGHTS = [("l1", "Desk Lamp"), ("l2", "Living Room Lamp"), ("l3", "Kid's Room Lamp")]
TIERS = (("group", ROOMS), ("light", LIGHTS))


@pytest.mark.unit
@pytest.mark.parametrize("spoken,expected", [
    ("Living Room", ("group", "g1", "Living Room")),       # exact beats containment
    ("living room", ("group", "g1", "Living Room")),
    ("Desk Lamp", ("light", "l1", "Desk Lamp")),
    ("desk", ("light", "l1", "Desk Lamp")),                # containment, later tier
    ("Study", ("group", "g2", "Study")),
])
def test_resolve_basic_ladder(spoken, expected):
    assert resolve_by_name(TIERS, spoken) == expected


@pytest.mark.unit
def test_exact_in_a_later_tier_still_beats_containment_in_an_earlier_one():
    """The exact pass runs across all tiers before any containment pass, so a
    precise bulb name is not stolen by a room that merely contains it."""
    assert resolve_by_name(TIERS, "Living Room Lamp") == ("light", "l2", "Living Room Lamp")


@pytest.mark.unit
def test_ambiguous_earlier_tier_does_not_fall_through():
    """The regression this module exists to prevent: two rooms match 'room', so
    a resolver that discarded the ambiguous tier would let a bulb answer."""
    kind, _, _ = resolve_by_name(TIERS, "room")
    assert kind == "group"


@pytest.mark.unit
def test_curly_apostrophe_room_beats_straight_apostrophe_bulb():
    kind, rid, _ = resolve_by_name(TIERS, "Kid's Room")
    assert (kind, rid) == ("group", "g3")


@pytest.mark.unit
def test_tier_order_decides_otherwise_equal_matches():
    tiers_reversed = (("light", LIGHTS), ("group", ROOMS))
    assert resolve_by_name(tiers_reversed, "room")[0] == "light"


@pytest.mark.unit
@pytest.mark.parametrize("spoken", [None, "", "   "])
def test_empty_target_returns_none(spoken):
    assert resolve_by_name(TIERS, spoken) is None


@pytest.mark.unit
def test_unrelated_name_returns_none():
    assert resolve_by_name(TIERS, "helicopter") is None


@pytest.mark.unit
def test_fuzzy_floor_is_respected():
    tiers = (("device", [("d1", "Kitchen Echo")]),)
    assert resolve_by_name(tiers, "Kitchen Eco") is not None       # near miss clears
    assert resolve_by_name(tiers, "xyzzy", fuzzy_floor=0.99) is None


@pytest.mark.unit
def test_single_tier_matches_the_spotify_resolver_shape():
    """Spotify passes one tier; the ladder must behave as it did before the
    extraction: exact, then the best containment hit, then floored fuzzy."""
    devices = (("device", [("d1", "Living Room"), ("d2", "Kitchen Echo")]),)
    assert resolve_by_name(devices, "Living Room") == ("device", "d1", "Living Room")
    assert resolve_by_name(devices, "kitchen") == ("device", "d2", "Kitchen Echo")
    assert resolve_by_name(devices, "nowhere at all") is None


@pytest.mark.unit
def test_empty_tiers_are_safe():
    assert resolve_by_name((), "anything") is None
    assert resolve_by_name((("group", []),), "anything") is None


# ----- tool_schema -------------------------------------------------------

@pytest.mark.unit
def test_tool_schema_shape():
    spec = tool_schema("x_do", "Do the thing",
                       {"a": {"type": "string"}}, required=["a"])
    assert spec == {"type": "function", "function": {
        "name": "x_do", "description": "Do the thing",
        "parameters": {"type": "object",
                       "properties": {"a": {"type": "string"}},
                       "required": ["a"]}}}


@pytest.mark.unit
def test_tool_schema_omits_required_when_absent():
    assert "required" not in tool_schema("x_do", "d")["function"]["parameters"]


@pytest.mark.unit
def test_tool_schema_deep_copies_inputs():
    """A shared property constant reused across schemas must be isolated at
    every level. A shallow copy leaves the nested property dicts aliased, so
    editing one schema's description in place would change every schema built
    from the same constant -- and the constant itself."""
    props = {"a": {"type": "string", "description": "original"}}
    one, two = tool_schema("x_do", "d", props), tool_schema("y_do", "d", props)

    one["function"]["parameters"]["properties"]["b"] = {"type": "string"}
    assert "b" not in props                                  # top level

    one["function"]["parameters"]["properties"]["a"]["description"] = "edited"
    assert props["a"]["description"] == "original"           # nested constant
    assert two["function"]["parameters"]["properties"]["a"]["description"] == "original"


@pytest.mark.unit
def test_provider_schemas_do_not_share_property_objects():
    """The real shape this guards: both providers build several schemas from one
    shared target/device property constant."""
    from jf_sebastian.modules.hue_tool import OPENAI_TOOLS as HUE
    with_target = [s for s in HUE if "target" in s["function"]["parameters"]["properties"]]
    first = with_target[0]["function"]["parameters"]["properties"]["target"]
    for spec in with_target[1:]:
        assert spec["function"]["parameters"]["properties"]["target"] is not first


@pytest.mark.unit
def test_tool_schema_rejects_a_bare_string_required():
    """list("query") silently becomes ['q','u','e','r','y'] -- a valid-looking
    schema declaring five properties that don't exist."""
    with pytest.raises(TypeError):
        tool_schema("x_do", "d", {"query": {"type": "string"}}, required="query")


@pytest.mark.unit
def test_base_error_hints_cannot_be_mutated():
    with pytest.raises(TypeError):
        ToolProvider.error_hints["x"] = "y"


# ----- ToolProvider ------------------------------------------------------

class Boom(Exception):
    pass


class FakeProvider(ToolProvider):
    namespace = "fake_"
    unknown_tool_hint = "I can't do that with the fake"
    fallback_hint = "the fake isn't responding"
    error_hints = {"offline": "the fake is offline"}

    def handlers(self):
        return {
            "fake_ok": lambda a: ToolResult(True, f"did it with {a.get('x')}"),
            "fake_typed": lambda a: (_ for _ in ()).throw(
                ToolError("bad-args", "what exactly?", data={"k": 1})),
            "fake_boom": lambda a: (_ for _ in ()).throw(Boom("secret-token-abc")),
        }

    def classify(self, exc):
        return "offline" if isinstance(exc, Boom) else "network"


@pytest.mark.unit
@pytest.mark.parametrize("name,claimed", [
    ("fake_ok", True), ("fake_anything", True),
    ("music_play", False), ("", False), (None, False),
])
def test_handles_claims_only_its_namespace(name, claimed):
    assert FakeProvider().handles(name) is claimed


@pytest.mark.unit
def test_provider_without_a_namespace_claims_nothing():
    class Anon(ToolProvider):
        def handlers(self):
            return {}
    assert Anon().handles("anything") is False


@pytest.mark.unit
def test_dispatch_success():
    r = FakeProvider().dispatch("fake_ok", {"x": 7})
    assert (r.ok, r.kind, r.spoken_hint) == (True, "ok", "did it with 7")


@pytest.mark.unit
def test_dispatch_unknown_tool():
    r = FakeProvider().dispatch("fake_nope", {})
    assert not r.ok and r.kind == "bad-args"
    assert r.spoken_hint == "I can't do that with the fake"


@pytest.mark.unit
def test_dispatch_converts_typed_error():
    r = FakeProvider().dispatch("fake_typed", {})
    assert not r.ok and r.kind == "bad-args"
    assert r.spoken_hint == "what exactly?"
    assert r.data == {"k": 1}


@pytest.mark.unit
def test_dispatch_converts_unexpected_exception_via_classify():
    r = FakeProvider().dispatch("fake_boom", {})
    assert not r.ok and r.kind == "offline"
    assert r.spoken_hint == "the fake is offline"


@pytest.mark.unit
def test_unexpected_exception_text_never_reaches_the_spoken_hint():
    """Backend exceptions can carry tokens in their string form; only the
    taxonomy kind is surfaced."""
    r = FakeProvider().dispatch("fake_boom", {})
    assert "secret-token-abc" not in r.spoken_hint


@pytest.mark.unit
def test_unclassified_kind_falls_back_to_the_generic_hint():
    class Other(FakeProvider):
        def classify(self, exc):
            return "some-unmapped-kind"
    r = Other().dispatch("fake_boom", {})
    assert r.kind == "some-unmapped-kind"
    assert r.spoken_hint == "the fake isn't responding"


@pytest.mark.unit
@pytest.mark.parametrize("args", [None, {}])
def test_dispatch_tolerates_missing_args(args):
    assert FakeProvider().dispatch("fake_ok", args).ok


@pytest.mark.unit
def test_dispatch_never_raises_even_when_handlers_itself_fails():
    """Building the handler table is inside the guard, so a subclass with a
    broken handlers() loses its tool call rather than the whole turn."""
    class Broken(ToolProvider):
        namespace = "b_"

        def handlers(self):
            raise Boom("handler table blew up")

    r = Broken().dispatch("b_x", {})
    assert not r.ok and r.kind == "network"
    assert "handler table blew up" not in r.spoken_hint


@pytest.mark.unit
def test_base_handlers_is_abstract_but_dispatch_still_degrades():
    """A provider that forgets handlers() must not raise into the turn either."""
    with pytest.raises(NotImplementedError):
        ToolProvider().handlers()
    r = ToolProvider().dispatch("anything", {})
    assert not r.ok and r.kind == "network"


# ----- ToolResult --------------------------------------------------------

@pytest.mark.unit
def test_tool_result_defaults():
    r = ToolResult(True, "done")
    assert (r.kind, r.suppress_followup, r.data) == ("ok", False, {})


@pytest.mark.unit
def test_tool_result_data_is_not_shared_between_instances():
    a, b = ToolResult(True, "a"), ToolResult(True, "b")
    a.data["x"] = 1
    assert b.data == {}


# ----- containment guards (xhigh review) ---------------------------------

@pytest.mark.unit
def test_short_earlier_tier_name_does_not_swallow_a_longer_request():
    """Regression: reverse containment was a raw substring, so a zone called
    "Up" matched inside "the cupboard light" and answered for the bulb."""
    tiers = (("group", [("g1", "Up"), ("g2", "Kitchen")]),
             ("light", [("l1", "Cupboard Light"), ("l2", "Desk Lamp")]))
    assert resolve_by_name(tiers, "the cupboard light") == ("light", "l1", "Cupboard Light")
    assert resolve_by_name(tiers, "cupboard") == ("light", "l1", "Cupboard Light")


@pytest.mark.unit
def test_reverse_containment_still_works_on_word_boundaries():
    """The guard must not break the ordinary case it exists to serve."""
    tiers = (("group", [("g1", "Dining Room")]), ("light", [("l1", "Desk Lamp")]))
    assert resolve_by_name(tiers, "the dining room") == ("group", "g1", "Dining Room")


@pytest.mark.unit
@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_candidate_names_are_skipped(blank):
    """Regression: "" is contained in every target, so one unnamed group
    answered every non-exact request."""
    tiers = (("group", [("g1", blank), ("g2", "Kitchen")]),
             ("light", [("l1", "Desk Lamp")]))
    assert resolve_by_name(tiers, "desk") == ("light", "l1", "Desk Lamp")
    assert resolve_by_name(tiers, "kitchen") == ("group", "g2", "Kitchen")
    assert resolve_by_name(tiers, "bedside") is None


@pytest.mark.unit
def test_forward_containment_is_still_a_plain_substring():
    """Naming part of a name -- including a partial word -- must keep working."""
    tiers = (("group", [("g1", "Living Room")]),)
    assert resolve_by_name(tiers, "living")[1] == "g1"
    assert resolve_by_name(tiers, "livin")[1] == "g1"


@pytest.mark.unit
def test_normalize_is_applied_once_per_candidate():
    """The three passes share one folded form, so they cannot disagree."""
    calls = []

    def counting(text):
        calls.append(text)
        return fold(text)

    tiers = (("group", [("g1", "Alpha"), ("g2", "Beta")]),)
    resolve_by_name(tiers, "totally unrelated", normalize=counting)
    # One call for the target, one per candidate -- not one per pass.
    assert len(calls) == 3
