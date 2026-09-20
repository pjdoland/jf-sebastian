"""
Philips Hue light control for J.F. Sebastian (optional, per-personality).

A self-contained wrapper around the Hue Bridge local API that exposes a small
set of lighting "tools" to the LLM, shaped exactly like modules/spotify_tool.py.

Design notes:
- LOCAL ONLY: talks to the Bridge on the LAN over the v1 API. No cloud, no
  vendor account, no outbound dependency. Sub-100ms per call in practice.
- HARDENED like spotify_tool.py: short request timeout, every call wrapped so
  failures return a typed ToolResult instead of raising into the conversation
  turn. Lazy credentials: nothing touches the network until the first call.
- CAPABILITY-AWARE: Hue White bulbs (e.g. LWB014) have no colour channel. A
  colour request that lands on one degrades to a neutral spoken hint rather
  than a Bridge error, and a mixed group colours only the bulbs that can.
- NAME RESOLUTION: rooms/zones are searched before individual bulbs, so "the
  bedroom" beats a bulb that happens to contain the word. Same exact ->
  containment -> fuzzy ladder the Spotify device resolver uses.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

import requests

from jf_sebastian.config import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S = 4          # hard per-call timeout; the Bridge is on the LAN
_INVENTORY_TTL_S = 60           # names/ids/capabilities change rarely; state is never cached
_ALL_LIGHTS_GROUP = "0"         # Hue's built-in "every light" group
_MAX_SPOKEN_NAMES = 8           # cap what lights_list reads aloud; TTS shouldn't recite 30 bulbs

# One keep-alive session for every Bridge call. Colouring a mixed room writes
# per-bulb, so without connection reuse each bulb pays a fresh TCP setup (and,
# against an unreachable Bridge, its own full timeout).
_SESSION = requests.Session()

# Hue v1 ranges: bri 1-254, hue 0-65535, sat 0-254, ct 153-500 mireds.
_BRI_MIN, _BRI_MAX = 1, 254
_CT_WARM, _CT_NEUTRAL, _CT_COOL = 450, 300, 200

# Spoken colour -> Hue v1 state fragment.
_COLORS = {
    "red": {"hue": 0, "sat": 254},
    "orange": {"hue": 5000, "sat": 254},
    "amber": {"hue": 7000, "sat": 254},
    "yellow": {"hue": 10000, "sat": 254},
    "lime": {"hue": 18000, "sat": 254},
    "green": {"hue": 25500, "sat": 254},
    "teal": {"hue": 32000, "sat": 254},
    "cyan": {"hue": 35000, "sat": 254},
    "turquoise": {"hue": 35000, "sat": 254},
    "blue": {"hue": 46920, "sat": 254},
    "indigo": {"hue": 47500, "sat": 254},
    "violet": {"hue": 49000, "sat": 254},
    "purple": {"hue": 50000, "sat": 254},
    "magenta": {"hue": 56100, "sat": 254},
    "pink": {"hue": 56100, "sat": 180},
    "white": {"sat": 0, "ct": _CT_NEUTRAL},
    "warm white": {"sat": 0, "ct": _CT_WARM},
    "cool white": {"sat": 0, "ct": _CT_COOL},
    "daylight": {"sat": 0, "ct": _CT_COOL},
}

# Scene names the Hue app stores as bookkeeping; never offer these to the model.
# Different app versions write these with or without a separating space
# ("Scene storageScene " vs "storageScene"), so match on a space-stripped form.
_SCENE_NOISE_MARKERS = ("scenescene", "sceneprevious", "storagescene", "scenetmp")


def _is_noise_scene(name: str) -> bool:
    squashed = re.sub(r"\s+", "", (name or "")).lower()
    if not squashed:
        return False
    # Match both "storageScene" and "Scene storageScene", so the leading "Scene "
    # some app versions prepend is also considered with it stripped.
    forms = {squashed}
    if squashed.startswith("scene"):
        forms.add(squashed[len("scene"):])
    return any(f.startswith(m) for m in _SCENE_NOISE_MARKERS for f in forms)


def _normalize(text: str) -> str:
    """Fold a spoken or stored name for comparison. The Hue app stores curly
    apostrophes (U+2019) while the model emits straight ones, so a room called
    "Kid's Room" would otherwise fail exact/containment and lose to a bulb."""
    return (text or "").replace("’", "'").replace("‘", "'").strip().lower()


@dataclass
class ToolResult:
    """Mirrors spotify_tool.ToolResult so the conversation engine stays
    tool-agnostic. `spoken_hint` is a short neutral phrase the personality
    voices in character; `kind` is the error taxonomy for logging."""
    ok: bool
    spoken_hint: str
    kind: str = "ok"                       # ok | bridge-unreachable | not-paired | not-found
                                           #   | no-color | bad-args | network
    suppress_followup: bool = False
    data: dict = field(default_factory=dict)


class HueToolError(Exception):
    def __init__(self, kind: str, spoken_hint: str, data: Optional[dict] = None):
        super().__init__(spoken_hint)
        self.kind = kind
        self.spoken_hint = spoken_hint
        self.data = data or {}


def _clamp_brightness(pct: int) -> int:
    """0-100 spoken percentage -> Hue's 1-254 `bri`."""
    pct = max(0, min(100, pct))
    return max(_BRI_MIN, round(_BRI_MIN + (pct / 100) * (_BRI_MAX - _BRI_MIN)))


def _adapt_fragment(light: dict, fragment: dict):
    """Adapt a colour fragment to what this bulb actually supports, or None if it
    can't express the colour at all.

    Three bulb tiers matter: full colour (hue+sat+ct), White Ambiance (ct only,
    no hue channel), and plain White (bri only). A hue-based colour needs the hue
    channel; a colour-temperature white only needs ct, so White Ambiance bulbs
    keep their whites instead of being written off as "can't change colour".
    """
    state = light.get("state") or {}
    if "hue" in fragment:
        return dict(fragment) if "hue" in state else None
    if "ct" in fragment:
        if "ct" not in state:
            return None
        adapted = dict(fragment)
        if "sat" in adapted and "sat" not in state:
            adapted.pop("sat")      # ct-only bulbs reject a sat key
        return adapted
    return None


class HueTool:
    def __init__(self) -> None:
        self.cache_path = os.path.expanduser(settings.HUE_TOKEN_CACHE)
        self._creds_cache: Optional[dict] = None
        self._inv: Optional[dict] = None    # {"lights":…, "groups":…, "scenes":…}
        self._inv_time = 0.0

    # ----- credentials + transport (lazy, hardened) ------------------------

    def _creds(self) -> dict:
        if self._creds_cache is not None:
            return self._creds_cache
        try:
            with open(self.cache_path) as f:
                creds = json.load(f)
        except FileNotFoundError as e:
            raise HueToolError("not-paired", "the lights are not set up yet") from e
        except (OSError, ValueError) as e:
            raise HueToolError("not-paired", "I can't read the light settings") from e
        if not creds.get("username"):
            raise HueToolError("not-paired", "the lights are not set up yet")
        # An explicit HUE_BRIDGE_HOST wins over the paired-at address (DHCP moves).
        host = (settings.HUE_BRIDGE_HOST or "").strip()
        if host:
            creds["bridge_ip"] = host
        self._creds_cache = creds
        return creds

    def _url(self, path: str) -> str:
        c = self._creds()
        return f"http://{c['bridge_ip']}/api/{c['username']}/{path}"

    def _request(self, method: str, path: str, body: Optional[dict] = None):
        try:
            resp = _SESSION.request(method, self._url(path), json=body,
                                    timeout=_REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as e:
            raise HueToolError("bridge-unreachable", "I can't reach the lights right now") from e
        except ValueError as e:
            raise HueToolError("network", "the lights gave me a confusing answer") from e

        # v1 returns a list of per-key {"success":…} / {"error":…} envelopes on writes.
        if isinstance(payload, list):
            for entry in payload:
                if "error" in entry:
                    err = entry["error"]
                    if err.get("type") == 1:  # unauthorised user
                        # The credential was revoked or the Bridge was reset. Drop
                        # the caches so re-running the pairing script takes effect
                        # without bouncing the whole supervised process.
                        self._creds_cache = None
                        self._inv = None
                        raise HueToolError("not-paired", "I've lost my connection to the lights")
                    raise HueToolError("network", "the lights refused that",
                                       data={"description": err.get("description")})
        return payload

    # ----- inventory (short cache; names/ids/capabilities only) ------------

    def _inventory(self) -> dict:
        now = time.monotonic()
        if self._inv is not None and (now - self._inv_time) < _INVENTORY_TTL_S:
            return self._inv
        self._inv = {
            "lights": self._request("GET", "lights"),
            "groups": self._request("GET", "groups"),
            "scenes": self._request("GET", "scenes"),
        }
        self._inv_time = now
        return self._inv

    def _light_names(self) -> list:
        return [info.get("name", "") for info in self._inventory()["lights"].values()]

    def _room_names(self) -> list:
        return [g.get("name", "") for g in self._inventory()["groups"].values()
                if g.get("type") in ("Room", "Zone")]

    def _scene_names(self) -> list:
        names = {s.get("name", "").strip() for s in self._inventory()["scenes"].values()}
        return sorted(n for n in names if n and not _is_noise_scene(n))

    # ----- target resolution ----------------------------------------------

    _ALL_CUES = ("all", "everything", "every light", "all lights", "the house",
                 "everywhere", "all the lights")

    def _resolve_target(self, spoken: Optional[str]) -> tuple:
        """Map a spoken room/bulb name to (kind, id, display_name) where kind is
        'group' or 'light'. Rooms and zones are searched before individual bulbs
        so 'the bedroom' doesn't lose to a bulb name. An empty target, or an
        'everything' cue, resolves to Hue's built-in all-lights group."""
        target = (spoken or "").strip()
        if not target or _normalize(target) in self._ALL_CUES:
            return ("group", _ALL_LIGHTS_GROUP, "all the lights")

        inv = self._inventory()
        tl = _normalize(target)

        groups = [(gid, g.get("name", "")) for gid, g in inv["groups"].items()
                  if g.get("type") in ("Room", "Zone")]
        lights = [(lid, l.get("name", "")) for lid, l in inv["lights"].items()]
        tiers = (("group", groups), ("light", lights))

        # Rooms/zones first, then bulbs. Within each tier: exact, then containment.
        for kind, pool in tiers:
            for rid, name in pool:
                if _normalize(name) == tl:
                    return (kind, rid, name)

        # Containment. When a tier yields several hits, rank WITHIN that tier
        # rather than discarding it -- otherwise an ambiguous room name ("bedroom"
        # in a house with three) would fall through and let a bulb win, breaking
        # the rooms-before-bulbs invariant.
        for kind, pool in tiers:
            hits = [(rid, n) for rid, n in pool
                    if tl in _normalize(n) or _normalize(n) in tl]
            if len(hits) == 1:
                return (kind, hits[0][0], hits[0][1])
            if hits:
                rid, name = max(hits, key=lambda h: SequenceMatcher(
                    None, tl, _normalize(h[1])).ratio())
                return (kind, rid, name)

        # Fuzzy across everything, with a floor so we don't grab something unrelated.
        best = (0.0, None, None, None)
        for kind, pool in tiers:
            for rid, name in pool:
                score = SequenceMatcher(None, tl, _normalize(name)).ratio()
                if score > best[0]:
                    best = (score, kind, rid, name)
        if best[0] >= 0.5:
            return (best[1], best[2], best[3])

        raise HueToolError(
            "not-found", f"I don't know a light called {target}",
            data={"requested": spoken,
                  "rooms": self._room_names(), "lights": self._light_names()},
        )

    def _apply(self, kind: str, rid: str, state: dict) -> None:
        """Write a state fragment to a group action or a single light."""
        if kind == "group":
            self._request("PUT", f"groups/{rid}/action", state)
        else:
            self._request("PUT", f"lights/{rid}/state", state)

    def _member_lights(self, kind: str, rid: str) -> list:
        """The light ids a target covers (group 0 == every light)."""
        inv = self._inventory()
        if kind == "light":
            return [rid]
        if rid == _ALL_LIGHTS_GROUP:
            return list(inv["lights"].keys())
        return list((inv["groups"].get(rid) or {}).get("lights", []))

    # ----- the tools -------------------------------------------------------

    def turn_on(self, target: Optional[str] = None) -> ToolResult:
        kind, rid, name = self._resolve_target(target)
        self._apply(kind, rid, {"on": True})
        return ToolResult(True, f"{name} on", data={"target": name})

    def turn_off(self, target: Optional[str] = None) -> ToolResult:
        kind, rid, name = self._resolve_target(target)
        self._apply(kind, rid, {"on": False})
        return ToolResult(True, f"{name} off", data={"target": name})

    def set_brightness(self, level, target: Optional[str] = None) -> ToolResult:
        try:
            pct = int(level)
        except (TypeError, ValueError):
            raise HueToolError("bad-args", "how bright would you like it?")
        kind, rid, name = self._resolve_target(target)
        if pct <= 0:
            self._apply(kind, rid, {"on": False})
            return ToolResult(True, f"{name} off", data={"target": name, "brightness": 0})
        # Report the level actually applied, not what was asked for: "set it to 500"
        # must not record a 500 that was never written.
        applied = max(1, min(100, pct))
        self._apply(kind, rid, {"on": True, "bri": _clamp_brightness(applied)})
        return ToolResult(True, f"{name} at {applied} percent",
                          data={"target": name, "brightness": applied,
                                "requested": pct})

    def set_color(self, color: str, target: Optional[str] = None) -> ToolResult:
        key = (color or "").strip().lower()
        if not key:
            raise HueToolError("bad-args", "what colour would you like?")
        fragment = _COLORS.get(key)
        if fragment is None:
            # Tolerate "bright red" / "a nice warm white", but match whole words
            # only -- a substring test would read "ultraviolet" as violet. Longest
            # name first so "warm white" wins over "white".
            words = set(re.findall(r"[a-z]+", key))
            for name in sorted(_COLORS, key=len, reverse=True):
                if all(part in words for part in name.split()):
                    fragment, key = _COLORS[name], name
                    break
        if fragment is None:
            raise HueToolError("bad-args", f"I don't know the colour {color}",
                               data={"known": sorted(_COLORS)})

        kind, rid, name = self._resolve_target(target)
        inv = self._inventory()
        members = [lid for lid in self._member_lights(kind, rid) if lid in inv["lights"]]
        if not members:
            # An empty or stale group is NOT the same as "these bulbs are white-only";
            # saying so would tell the user their colour bulbs can't do colour.
            raise HueToolError("not-found", f"there are no lights in {name}",
                               data={"target": name})

        adapted = {lid: frag for lid, frag in
                   ((lid, _adapt_fragment(inv["lights"][lid], fragment)) for lid in members)
                   if frag is not None}
        if not adapted:
            raise HueToolError("no-color", f"{name} can't change colour",
                               data={"target": name})

        # One group action when every member takes the identical write; otherwise
        # per-bulb, so a mixed room still colours the bulbs that can.
        distinct = {tuple(sorted(f.items())) for f in adapted.values()}
        if len(adapted) == len(members) and len(distinct) == 1:
            self._apply(kind, rid, {"on": True, **next(iter(adapted.values()))})
        else:
            for lid, frag in adapted.items():
                self._apply("light", lid, {"on": True, **frag})
        return ToolResult(True, f"{name} {key}",
                          data={"target": name, "color": key,
                                "partial": len(adapted) != len(members)})

    def activate_scene(self, scene: str, target: Optional[str] = None) -> ToolResult:
        wanted = (scene or "").strip().lower()
        if not wanted:
            raise HueToolError("bad-args", "which scene would you like?")
        inv = self._inventory()

        candidates = [(sid, s) for sid, s in inv["scenes"].items()
                      if s.get("name", "").strip() and not _is_noise_scene(s["name"])]
        exact = [(sid, s) for sid, s in candidates if _normalize(s["name"]) == wanted]
        pool = exact or [(sid, s) for sid, s in candidates if wanted in _normalize(s["name"])]
        if not pool:
            raise HueToolError("not-found", f"I don't know a scene called {scene}",
                               data={"known": self._scene_names()})

        display = pool[0][1]["name"].strip()

        if not target:
            # No room named: use the scene's own stored group.
            scene_id, chosen = pool[0]
            group_id = chosen.get("group")
            name = None
        else:
            kind, rid, name = self._resolve_target(target)
            if kind != "group":
                # A scene is a stored state for a whole room. Applying one because
                # a single bulb was named would silently change every other light
                # in that bulb's room while reporting only the bulb.
                raise HueToolError(
                    "bad-args", f"{display} is a room scene, not something I can set on {name}",
                    data={"scene": display, "target": name})
            # Only a copy stored FOR this room is valid -- a scene id belonging to
            # another group is not applicable here, and writing it would either
            # no-op or affect the wrong lights while reporting success.
            match = next(((sid, s) for sid, s in pool if s.get("group") == rid), None)
            if match is None:
                raise HueToolError("not-found", f"there's no {display} scene set up for {name}",
                                   data={"scene": display, "target": name})
            scene_id, group_id = match[0], rid

        if not group_id:
            raise HueToolError("not-found", f"I can't apply the {display} scene here",
                               data={"scene": display})
        self._request("PUT", f"groups/{group_id}/action", {"scene": scene_id})
        where = f" in {name}" if name else ""
        return ToolResult(True, f"{display} scene{where}",
                          data={"scene": display, "group": group_id})

    def list_lights(self) -> ToolResult:
        rooms, lights, scenes = self._room_names(), self._light_names(), self._scene_names()

        def spoken(label, names):
            """Only spoken_hint reaches the user -- the engine discards `data` --
            so scenes must appear here. Long lists are truncated because this is
            read aloud through TTS."""
            if not names:
                return None
            shown = names[:_MAX_SPOKEN_NAMES]
            more = len(names) - len(shown)
            return f"{label}: " + ", ".join(shown) + (f", and {more} more" if more else "")

        parts = [p for p in (spoken("rooms", rooms), spoken("lights", lights),
                             spoken("scenes", scenes)) if p]
        return ToolResult(True, "; ".join(parts) or "I don't see any lights",
                          data={"rooms": rooms, "lights": lights, "scenes": scenes})

    # ----- dispatch + schema ----------------------------------------------

    _HANDLED_PREFIX = "lights_"

    def handles(self, name: str) -> bool:
        return (name or "").startswith(self._HANDLED_PREFIX)

    def dispatch(self, name: str, args: dict) -> ToolResult:
        """Execute a tool by name; convert every failure into a ToolResult."""
        handlers = {
            "lights_on": lambda a: self.turn_on(a.get("target")),
            "lights_off": lambda a: self.turn_off(a.get("target")),
            "lights_brightness": lambda a: self.set_brightness(a.get("level"), a.get("target")),
            "lights_color": lambda a: self.set_color(a.get("color", ""), a.get("target")),
            "lights_scene": lambda a: self.activate_scene(a.get("scene", ""), a.get("target")),
            "lights_list": lambda a: self.list_lights(),
        }
        handler = handlers.get(name)
        if handler is None:
            return ToolResult(False, "I can't do that with the lights", kind="bad-args")
        try:
            return handler(args or {})
        except HueToolError as e:
            logger.warning("Hue tool %s failed (%s)", name, e.kind)
            return ToolResult(False, e.spoken_hint, kind=e.kind, data=e.data)
        except Exception:
            logger.warning("Hue tool %s failed (network)", name)
            return ToolResult(False, "I can't reach the lights right now", kind="network")


def _tool(name, description, properties=None, required=None):
    fn = {"name": name, "description": description,
          "parameters": {"type": "object", "properties": properties or {}}}
    if required:
        fn["parameters"]["required"] = required
    return {"type": "function", "function": fn}


_TARGET_PROP = {"target": {
    "type": "string",
    "description": "room or individual light name (optional; omit for every light)"}}


OPENAI_TOOLS = [
    _tool("lights_on", "Turn lights on. Omit target for every light in the house.",
          _TARGET_PROP),
    _tool("lights_off", "Turn lights off. Omit target for every light in the house.",
          _TARGET_PROP),
    _tool("lights_brightness",
          "Set light brightness as a percentage (0-100). 0 turns them off.",
          {"level": {"type": "integer", "description": "0-100"}, **_TARGET_PROP},
          required=["level"]),
    _tool("lights_color",
          "Set light colour by name, e.g. red, blue, warm white. Only some bulbs "
          "support colour; the tool reports when one cannot.",
          {"color": {"type": "string", "description": "colour name, e.g. 'red'"},
           **_TARGET_PROP}, required=["color"]),
    _tool("lights_scene",
          "Activate a stored Hue scene such as Relax, Concentrate, Nightlight or Energize.",
          {"scene": {"type": "string", "description": "scene name"}, **_TARGET_PROP},
          required=["scene"]),
    _tool("lights_list", "List the available rooms, lights and scenes."),
]
