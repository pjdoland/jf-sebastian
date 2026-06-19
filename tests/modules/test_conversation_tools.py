"""Tests for tool-calling in the streaming ConversationEngine (OpenAI mocked)."""

from types import SimpleNamespace

import pytest

from jf_sebastian.config import settings as _settings
from jf_sebastian.modules import conversation as conv
from jf_sebastian.modules.conversation import ConversationEngine
from jf_sebastian.modules.spotify_tool import ToolResult


# ----- fakes ---------------------------------------------------------------

def content_chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=text, tool_calls=None), finish_reason=None)])


def toolcall_chunk(index, name=None, args=None, tc_id=None):
    fn = SimpleNamespace(name=name, arguments=args)
    tc = SimpleNamespace(index=index, id=tc_id, function=fn)
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=None, tool_calls=[tc]), finish_reason=None)])


def final_chunk(reason):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=None, tool_calls=None), finish_reason=reason)])


class FakeCompletions:
    def __init__(self, chunks):
        self.chunks = chunks
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return iter(self.chunks)


class FakeClient:
    def __init__(self, chunks):
        self.chat = SimpleNamespace(completions=FakeCompletions(chunks))


class FakeTool:
    def __init__(self, result):
        self.result = result
        self.dispatched = []

    def dispatch(self, name, args):
        self.dispatched.append((name, args))
        return self.result


@pytest.fixture
def engine_factory(monkeypatch):
    monkeypatch.setattr(_settings, "OPENAI_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(conv, "get_realworld_context", lambda: "")

    def make(chunks, tool=None, enabled=False):
        eng = ConversationEngine("system", spotify_tool=tool, spotify_enabled=enabled)
        eng.client = FakeClient(chunks)
        return eng
    return make


def drain(engine):
    """Run the streaming generator; return (spoken_chunks, completed)."""
    spoken, completed = [], False
    for text, is_final in engine.generate_response_streaming("do it"):
        if is_final:
            completed = True
            break
        if text.strip():
            spoken.append(text)
    return spoken, completed


# ----- tests ---------------------------------------------------------------

def test_tool_turn_executes_confirms_and_sets_suppress(engine_factory):
    # arguments arrive split across two deltas -> must be concatenated
    chunks = [
        toolcall_chunk(0, name="music_play", args='{"query":"tiki', tc_id="c1"),
        toolcall_chunk(0, args=' music"}'),
        final_chunk("tool_calls"),
    ]
    tool = FakeTool(ToolResult(True, "playing the Tiki Lounge playlist on Living Room",
                               suppress_followup=True))
    eng = engine_factory(chunks, tool=tool, enabled=True)

    spoken, completed = drain(eng)

    assert completed
    assert tool.dispatched == [("music_play", {"query": "tiki music"})]   # split args reassembled
    assert spoken == ["playing the Tiki Lounge playlist on Living Room"]  # templated confirmation
    assert eng.suppress_followup is True  # result declared it started music -> go IDLE


def test_tool_turn_history_is_clean(engine_factory):
    chunks = [toolcall_chunk(0, name="music_pause", args="{}"), final_chunk("tool_calls")]
    tool = FakeTool(ToolResult(True, "paused"))
    eng = engine_factory(chunks, tool=tool, enabled=True)
    drain(eng)
    msgs = list(eng._messages)
    # No raw tool scaffolding persisted; only a clean assistant summary.
    assert not any(m.get("role") == "tool" for m in msgs)
    assert not any("tool_calls" in m for m in msgs)
    assert msgs[-1] == {"role": "assistant", "content": "paused"}
    assert eng.suppress_followup is False  # pause is not a "music started" action


def test_malformed_json_args_degrade_to_empty(engine_factory):
    chunks = [toolcall_chunk(0, name="music_play", args='{"query": "x"'),  # truncated JSON
              final_chunk("tool_calls")]
    tool = FakeTool(ToolResult(True, "ok"))
    eng = engine_factory(chunks, tool=tool, enabled=True)
    drain(eng)
    assert tool.dispatched == [("music_play", {})]  # graceful: empty args, no crash


def test_normal_turn_streams_content_no_tool(engine_factory):
    chunks = [content_chunk("Aloha there my friend. "), final_chunk("stop")]
    tool = FakeTool(ToolResult(True, "should not be used"))
    eng = engine_factory(chunks, tool=tool, enabled=True)
    spoken, completed = drain(eng)
    assert completed
    assert tool.dispatched == []                       # no tool fired
    assert "".join(spoken).strip().startswith("Aloha there")
    assert eng.suppress_followup is False
    assert list(eng._messages)[-1]["role"] == "assistant"


def test_tools_attached_only_when_enabled(engine_factory):
    chunks = [content_chunk("hi. "), final_chunk("stop")]
    on = engine_factory(list(chunks), tool=FakeTool(ToolResult(True, "x")), enabled=True)
    drain(on)
    assert "tools" in on.client.chat.completions.kwargs

    off = engine_factory(list(chunks), tool=FakeTool(ToolResult(True, "x")), enabled=False)
    drain(off)
    assert "tools" not in off.client.chat.completions.kwargs


def test_reasoning_effort_sent_for_gpt5(engine_factory, monkeypatch):
    monkeypatch.setattr(_settings, "GPT_MODEL", "gpt-5.4-mini", raising=False)
    monkeypatch.setattr(_settings, "GPT_REASONING_EFFORT", "low", raising=False)
    eng = engine_factory([content_chunk("hello there. "), final_chunk("stop")])
    drain(eng)
    kw = eng.client.chat.completions.kwargs
    assert kw["reasoning_effort"] == "low"
    assert "max_completion_tokens" in kw and "max_tokens" not in kw
    assert "temperature" not in kw  # GPT-5 forces the default temperature


def test_reasoning_effort_omitted_for_gpt4(engine_factory, monkeypatch):
    monkeypatch.setattr(_settings, "GPT_MODEL", "gpt-4o-mini", raising=False)
    monkeypatch.setattr(_settings, "GPT_REASONING_EFFORT", "low", raising=False)
    eng = engine_factory([content_chunk("hello there. "), final_chunk("stop")])
    drain(eng)
    kw = eng.client.chat.completions.kwargs
    assert "reasoning_effort" not in kw  # GPT-4 has no reasoning parameter
    assert "max_tokens" in kw


def test_reasoning_effort_empty_omitted_for_gpt5(engine_factory, monkeypatch):
    monkeypatch.setattr(_settings, "GPT_MODEL", "gpt-5.4-mini", raising=False)
    monkeypatch.setattr(_settings, "GPT_REASONING_EFFORT", None, raising=False)
    eng = engine_factory([content_chunk("hi. "), final_chunk("stop")])
    drain(eng)
    assert "reasoning_effort" not in eng.client.chat.completions.kwargs


def test_failed_tool_does_not_suppress_followup(engine_factory):
    chunks = [toolcall_chunk(0, name="music_play", args='{"query":"x"}'), final_chunk("tool_calls")]
    tool = FakeTool(ToolResult(False, "I can't reach the music", kind="network"))
    eng = engine_factory(chunks, tool=tool, enabled=True)
    spoken, _ = drain(eng)
    assert spoken == ["I can't reach the music"]
    assert eng.suppress_followup is False  # nothing started playing
