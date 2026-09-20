"""
Shared scaffolding for LLM tool providers (Spotify playback, Hue lights, ...).

The conversation engine holds a list of providers; each one advertises OpenAI
function schemas, claims a tool-name namespace, and turns every failure into a
neutral spoken hint. Everything in this module is the part of that contract
which is genuinely identical across providers:

- `ToolResult` / `ToolError` -- the result and failure types the engine reads.
- `tool_schema()` -- the OpenAI function-tool envelope.
- `resolve_by_name()` -- the exact -> containment -> fuzzy ladder used to map a
  spoken name ("the kitchen", "nightstand") onto a device, room, or bulb.
- `ToolProvider` -- namespace claim plus the dispatch try/except that keeps a
  flaky backend from raising into a conversation turn.

Each provider still owns its own transport, auth, and vocabulary; only the
shape is shared. This module exists because the second provider was built by
hand-copying the first: the result types and schema helper were byte-identical,
and the two name resolvers were the same ladder maintained twice. Two copies of
matching logic drift, and a resolver bug has to be found and fixed in both --
so the ladder, with its tier and containment rules, now lives in one place.
"""

import copy
import logging
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from difflib import SequenceMatcher
from typing import Callable, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_FUZZY_FLOOR = 0.5

# Ordered candidate tiers: ((kind, [(id, name), ...]), ...)
Tier = Tuple[str, Sequence[Tuple[str, str]]]


@dataclass
class ToolResult:
    """Outcome of a tool call.

    `spoken_hint` is a short, neutral phrase the caller hands to the personality
    to voice in character -- we never speak raw API data or errors. `kind` is the
    error taxonomy, used for logging. `suppress_followup` lets a tool declare
    "this started music" so the caller can go idle instead of listening over it;
    the tool owns that fact, not the conversation engine. `data` carries
    structured detail and is NOT logged at INFO.
    """
    ok: bool
    spoken_hint: str
    kind: str = "ok"
    suppress_followup: bool = False
    data: dict = field(default_factory=dict)


class ToolError(Exception):
    """A failure carrying both a taxonomy `kind` and a speakable hint.

    Providers raise this internally; `ToolProvider.dispatch` converts it to a
    `ToolResult` so nothing escapes into the conversation turn.
    """

    def __init__(self, kind: str, spoken_hint: str, data: Optional[dict] = None):
        super().__init__(spoken_hint)
        self.kind = kind
        self.spoken_hint = spoken_hint
        self.data = data or {}


def tool_schema(name: str, description: str,
                properties: Optional[dict] = None,
                required: Optional[Sequence[str]] = None) -> dict:
    """Build one OpenAI function-tool envelope.

    `properties` is deep-copied: providers build several schemas from a shared
    constant (a reusable `target`/`device` property), and a shallow copy would
    leave the nested property dicts aliased, so editing one schema in place
    would silently change every other schema built from the same constant.
    """
    fn = {"name": name, "description": description,
          "parameters": {"type": "object",
                         "properties": copy.deepcopy(dict(properties or {}))}}
    if required is not None:
        if isinstance(required, str):
            # list("query") would become ['q','u','e','r','y'] -- a valid-looking
            # schema declaring five properties that don't exist.
            raise TypeError("required must be a sequence of names, not a string")
        if required:
            fn["parameters"]["required"] = list(required)
    return {"type": "function", "function": fn}


def fold(text: Optional[str]) -> str:
    """Normalize a spoken or stored name for comparison.

    Folds case, collapses whitespace, and maps curly apostrophes to ASCII --
    vendor apps commonly store U+2019 ("Kid's Room") while the model emits the
    straight form, which would otherwise fail exact and containment matching.
    """
    squashed = re.sub(r"\s+", " ", (text or "")).strip().lower()
    return squashed.replace("’", "'").replace("‘", "'")


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _contains_word(haystack: str, needle: str) -> bool:
    """Whole-word containment, so a short stored name can't match inside a longer
    one: a zone called "Up" must not answer "the cupboard light"."""
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def resolve_by_name(tiers: Sequence[Tier], spoken: Optional[str], *,
                    normalize: Callable[[Optional[str]], str] = fold,
                    fuzzy_floor: float = _DEFAULT_FUZZY_FLOOR):
    """Map a spoken name onto one of several ordered candidate tiers.

    `tiers` is an ordered sequence of `(kind, [(id, name), ...])`. Earlier tiers
    win, which is how a caller expresses "rooms before individual bulbs".
    Returns `(kind, id, name)`, or None when nothing clears the fuzzy floor.

    The ladder is exact -> containment -> fuzzy. Containment is resolved WITHIN
    a tier: when several names in one tier match, the best of them is returned
    rather than discarding the tier and letting a later one answer. Dropping an
    ambiguous tier would invert the caller's priority -- in a house with three
    bedrooms, "bedroom" would skip every room and be answered by a lamp.

    Containment is asymmetric on purpose. Forward ("living" inside "Living
    Room") is a plain substring, because the speaker naming part of a name is
    the common case. Reverse (a stored name inside a longer spoken phrase) must
    match on word boundaries, or any short name swallows unrelated requests.
    Candidates that normalize to nothing are skipped entirely -- an empty string
    is contained in every target and would otherwise answer everything.
    """
    target = normalize(spoken)
    if not target:
        return None

    # Fold each candidate once: the three passes below would otherwise re-run
    # normalize up to four times per candidate, and any disagreement between
    # passes would be a silent inconsistency.
    folded = []
    for kind, pool in tiers:
        entries = []
        for rid, name in pool:
            fname = normalize(name)
            if fname:
                entries.append((rid, name, fname))
        folded.append((kind, entries))

    for kind, pool in folded:
        for rid, name, fname in pool:
            if fname == target:
                return (kind, rid, name)

    for kind, pool in folded:
        hits = [(rid, name, fname) for rid, name, fname in pool
                if target in fname or _contains_word(target, fname)]
        if hits:
            rid, name, _ = max(hits, key=lambda h: _ratio(target, h[2]))
            return (kind, rid, name)

    best_score, best = 0.0, None
    for kind, pool in folded:
        for rid, name, fname in pool:
            score = _ratio(target, fname)
            if score > best_score:
                best_score, best = score, (kind, rid, name)
    return best if best_score >= fuzzy_floor else None


class ToolProvider:
    """Base for a provider: namespace claim + a dispatch that never raises.

    Subclasses set `namespace`, provide `handlers()`, and may set `error_hints`
    (taxonomy `kind` -> spoken phrase) and override `classify()` to map their
    own backend exceptions onto that taxonomy.
    """

    namespace: str = ""
    # Read-only so the shared default can't be mutated through a subclass that
    # never declares its own.
    error_hints = MappingProxyType({})
    unknown_tool_hint: str = "I can't do that"
    fallback_hint: str = "that isn't responding right now"
    fallback_kind: str = "network"

    def handles(self, name: Optional[str]) -> bool:
        """Claim a tool name. The engine may hold several providers, so each one
        owns a distinct prefix and answers only for its own."""
        return bool(self.namespace) and (name or "").startswith(self.namespace)

    def handlers(self) -> dict:
        """Map tool name -> callable taking the parsed argument dict."""
        raise NotImplementedError

    def classify(self, exc: Exception) -> str:
        """Map an unexpected backend exception onto the error taxonomy.

        Deliberately receives the exception without logging it: transport
        exceptions can carry Authorization headers or tokens in their string
        form, so only the resulting `kind` is ever logged.
        """
        return self.fallback_kind

    def dispatch(self, name: str, args: Optional[dict]) -> ToolResult:
        """Execute a tool by name, converting every failure into a ToolResult.

        Building the handler table happens inside the guard too: a subclass whose
        `handlers()` raises must still not take down the conversation turn.
        """
        label = type(self).__name__
        try:
            handler = self.handlers().get(name)
            if handler is None:
                return ToolResult(False, self.unknown_tool_hint, kind="bad-args")
            return handler(args or {})
        except ToolError as e:
            logger.warning("%s tool %s failed (%s)", label, name, e.kind)
            return ToolResult(False, e.spoken_hint, kind=e.kind, data=e.data)
        except Exception as e:
            kind = self.classify(e)
            logger.warning("%s tool %s failed (%s)", label, name, kind)
            return ToolResult(False, self.error_hints.get(kind, self.fallback_hint), kind=kind)
