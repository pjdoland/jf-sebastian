"""
ProactiveScheduler — fires personality-defined events on a schedule so the
animatronic can initiate dialogue (greet at 7am, bedtime story at 9pm,
holiday surprises) instead of being purely reactive.

Schedule syntax is intentionally tiny — full cron is overkill for hobbyist use:
  "HH:MM"                 — daily at HH:MM
  "HH:MM mon,wed,fri"     — those weekdays at HH:MM (mon|tue|wed|thu|fri|sat|sun)
  "HH:MM weekdays"        — Mon–Fri (alias)
  "HH:MM weekends"        — Sat–Sun (alias)
  "HH:MM YYYY-MM-DD"      — single occurrence on that date

Each event has either:
  say:    "Verbatim text spoken via TTS, no LLM round-trip."
          Use for fixed announcements ("Happy birthday!", chime intros).
  prompt: "Sent to the LLM as if the user said this. Response goes through TTS."
          Use when you want variety — the LLM rewrites it differently each time.

Quiet-hours window is half-open: [start, end). The `start` minute IS quiet;
the `end` minute is NOT. Setting start == end disables the quiet window.

If you need cron-style features (intervals, ranges, last-day-of-month), use
system cron with a small helper script that POSTs to your device. This
scheduler is intentionally limited to the forms above.

Limitations:
- Naive local time. On a DST "spring forward" day, an event at 02:30 will
  not fire (that minute doesn't exist). Schedule outside 02:00–02:59 on
  transition days if this matters.
- Clock jumps forward (laptop sleep/wake, NTP step) skip events whose
  scheduled minute falls inside the gap — there is no catch-up on resume.
  For mission-critical schedules use system cron.
- No live reload — edits to scheduled_events.yaml require a process restart.
- Events fire serially on a single scheduler thread. Two events at the
  same minute run back-to-back; if the first uses `prompt:` and the LLM
  round-trip takes 6 s, the second fires ~6 s late.
- Scheduled `prompt:` events go through the conversation engine and are
  added to its history alongside user turns.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional

import yaml

logger = logging.getLogger(__name__)

_DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DAY_ALIASES = {"weekdays": {0, 1, 2, 3, 4}, "weekends": {5, 6}}
# Permissive regex; range validation happens in _parse_when below.
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class Schedule(NamedTuple):
    """Parsed `when` expression: time-of-day plus optional weekday set or one-shot date."""

    tod: time
    weekdays: Optional[set[int]]
    one_shot_date: Optional[date]


@dataclass
class ScheduledEvent:
    """A single scheduled behavior loaded from scheduled_events.yaml."""

    name: str
    when: str
    say: Optional[str] = None
    prompt: Optional[str] = None
    # Parsed schedule cached at construction so _should_fire doesn't redo
    # the regex/split work on every tick.
    _schedule: Schedule = field(init=False, repr=False)
    # Tracks the last datetime this event fired, so we don't double-fire
    # when the scheduler ticks within the same minute multiple times.
    _last_fired: Optional[datetime] = field(default=None, repr=False)

    def __post_init__(self):
        if not self.say and not self.prompt:
            raise ValueError(f"Event {self.name!r}: must set either 'say' or 'prompt'")
        if self.say and self.prompt:
            raise ValueError(f"Event {self.name!r}: cannot set both 'say' and 'prompt'")
        # Validate and cache the schedule expression at load time.
        self._schedule = _parse_when(self.when)


def _parse_when(expr: str) -> Schedule:
    """Parse a `when` expression. Raises ValueError on invalid input."""
    parts = expr.strip().split()
    if not parts:
        raise ValueError("empty schedule expression")

    m = _TIME_RE.match(parts[0])
    if not m:
        raise ValueError(f"expected HH:MM, got {parts[0]!r}")
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"invalid time-of-day {parts[0]!r}")
    tod = time(hour=hour, minute=minute)

    if len(parts) == 1:
        return Schedule(tod, None, None)

    rest = " ".join(parts[1:])

    # Single date?
    m_date = _DATE_RE.match(rest)
    if m_date:
        try:
            single = date(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
        except ValueError as e:
            raise ValueError(f"invalid date in {expr!r}: {e}")
        return Schedule(tod, None, single)

    # Weekdays (with aliases like "weekdays" / "weekends").
    days: set[int] = set()
    for token in rest.split(","):
        token = token.strip().lower()
        if not token:
            raise ValueError(
                f"empty weekday token in {expr!r} "
                f"(check for stray commas like 'mon,' or 'mon,,tue')"
            )
        if " " in token:
            raise ValueError(
                f"weekdays must be comma-separated, got {token!r} in {expr!r}"
            )
        if token in _DAY_ALIASES:
            days |= _DAY_ALIASES[token]
            continue
        if token not in _DAY_NAMES:
            raise ValueError(
                f"unknown weekday {token!r} in {expr!r} "
                f"(use mon/tue/.../sun, or 'weekdays'/'weekends')"
            )
        days.add(_DAY_NAMES.index(token))
    return Schedule(tod, days, None)


def _is_quiet(now: datetime, quiet_start: Optional[time], quiet_end: Optional[time]) -> bool:
    """True if `now`'s time-of-day falls within the quiet window [start, end)."""
    if quiet_start is None or quiet_end is None:
        return False
    if quiet_start == quiet_end:
        # Empty window — explicit no-op rather than "always quiet"
        return False
    t = now.time()
    if quiet_start <= quiet_end:
        return quiet_start <= t < quiet_end
    # Window wraps midnight (e.g., 22:00 → 07:00)
    return t >= quiet_start or t < quiet_end


def _should_fire(event: ScheduledEvent, now: datetime) -> bool:
    """Has this event reached its scheduled time-of-day in the current minute?"""
    sched = event._schedule

    # Same minute as a previous fire — already fired
    if event._last_fired is not None:
        last = event._last_fired
        if (
            last.year == now.year
            and last.month == now.month
            and last.day == now.day
            and last.hour == now.hour
            and last.minute == now.minute
        ):
            return False

    if now.hour != sched.tod.hour or now.minute != sched.tod.minute:
        return False

    if sched.one_shot_date is not None and now.date() != sched.one_shot_date:
        return False

    if sched.weekdays is not None and now.weekday() not in sched.weekdays:
        return False

    return True


def parse_time_or_none(value: Any) -> Optional[time]:
    """Parse an HH:MM string into a `time`, or return None for empty/invalid input."""
    if not value:
        return None
    m = _TIME_RE.match(str(value).strip())
    if not m:
        logger.warning("Invalid HH:MM time %r; ignoring", value)
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h < 24 and 0 <= mi < 60):
        logger.warning("HH:MM time out of range %r; ignoring", value)
        return None
    return time(hour=h, minute=mi)


def load_scheduled_events(
    path: Path,
) -> tuple[list[ScheduledEvent], Optional[time], Optional[time]]:
    """Load events + quiet-hours from a YAML file.

    Returns `([], None, None)` for missing or unparseable files. When the
    file exists but yields no valid events, logs INFO so the user can see
    that something was wrong with their configuration.
    """
    if not path.exists():
        return [], None, None

    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.warning("Failed to parse %s: %s", path, e)
        return [], None, None

    events: list[ScheduledEvent] = []
    today = date.today()
    for raw in data.get("events", []) or []:
        try:
            event = ScheduledEvent(
                name=raw["name"],
                when=raw["when"],
                say=raw.get("say"),
                prompt=raw.get("prompt"),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(
                "Skipping invalid event %r (when=%r) in %s: %s",
                raw.get("name", "<unnamed>") if isinstance(raw, dict) else "<unparseable>",
                raw.get("when") if isinstance(raw, dict) else None,
                path,
                e,
            )
            continue

        # Warn about one-shot dates that have already passed — they'll never fire.
        if event._schedule.one_shot_date and event._schedule.one_shot_date < today:
            logger.warning(
                "Event %r has a past one-shot date %s; it will never fire",
                event.name,
                event._schedule.one_shot_date,
            )

        events.append(event)

    if not events and data.get("events"):
        logger.info(
            "%s contained an 'events' section but no valid events were loaded; "
            "check the warnings above",
            path,
        )

    quiet = (data.get("quiet_hours") or {})
    quiet_start = parse_time_or_none(quiet.get("start"))
    quiet_end = parse_time_or_none(quiet.get("end"))

    # Warn at load time about events that will be silently suppressed every
    # day by quiet hours — the most common Mike-the-Maker confusion.
    if quiet_start is not None and quiet_end is not None and quiet_start != quiet_end:
        for ev in events:
            probe = datetime.combine(today, ev._schedule.tod)
            if _is_quiet(probe, quiet_start, quiet_end):
                logger.warning(
                    "Event %r at %s falls inside quiet_hours %s-%s; it will never fire",
                    ev.name, ev.when, quiet_start, quiet_end,
                )

    return events, quiet_start, quiet_end


class ProactiveScheduler:
    """Background thread that fires scheduled events when their time arrives.

    The on_fire callback is expected to perform its own state-machine guarding
    (e.g., suppress when not in IDLE) and to be reasonably fast — it runs on
    this thread, so anything blocking will delay subsequent ticks.
    """

    def __init__(
        self,
        events: list[ScheduledEvent],
        on_fire: Callable[[ScheduledEvent], None],
        quiet_start: Optional[time] = None,
        quiet_end: Optional[time] = None,
        tick_seconds: float = 30.0,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.events = list(events)
        self.on_fire = on_fire
        self.quiet_start = quiet_start
        self.quiet_end = quiet_end
        # Hard-clamp tick_seconds: minute-granularity matching means a tick
        # interval over 59s can entirely skip an event's firing minute.
        clamped = max(1.0, float(tick_seconds))
        if clamped > 59.0:
            logger.warning(
                "tick_seconds=%.1f > 59s would risk skipping events whose "
                "scheduled minute lands between ticks; clamping to 59.0s. "
                "Set 30.0 or less for reliable per-minute firing.",
                clamped,
            )
            clamped = 59.0
        self.tick_seconds = clamped
        self._clock = clock or datetime.now
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not self.events:
            logger.info("No scheduled events; scheduler not started")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="scheduler")
        self._thread.start()
        logger.info(
            "ProactiveScheduler started with %d event(s); quiet_hours=%s-%s",
            len(self.events), self.quiet_start, self.quiet_end,
        )
        # Itemize so a user watching the log can confirm their event loaded.
        for ev in self.events:
            kind = "say" if ev.say else "prompt"
            logger.info("  - %s (when=%r, %s)", ev.name, ev.when, kind)

    def stop(self, join_timeout: float = 5.0) -> None:
        """Stop the scheduler thread. Generous default join — callbacks can take
        several seconds (TTS round-trip), and shutdown can wait. If the join
        times out (callback still running), logs a warning so the user isn't
        surprised by an apparent hang."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=join_timeout)
            if self._thread.is_alive():
                logger.warning(
                    "Scheduler thread did not exit within %.1fs (likely mid-callback); "
                    "leaving as daemon for process termination.",
                    join_timeout,
                )
            self._thread = None

    def tick(self, now: Optional[datetime] = None) -> list[ScheduledEvent]:
        """Run one scheduling tick. Returns the events that fired this tick.

        Public for tests; production code uses start() / the background thread.
        """
        now = now or self._clock()
        if _is_quiet(now, self.quiet_start, self.quiet_end):
            return []

        fired = []
        for event in self.events:
            if _should_fire(event, now):
                event._last_fired = now
                logger.info("Firing scheduled event: %s (%s)", event.name, event.when)
                try:
                    self.on_fire(event)
                except Exception:
                    logger.exception("Scheduled event %s callback failed", event.name)
                fired.append(event)
        return fired

    def _run(self) -> None:
        while not self._stop.wait(self.tick_seconds):
            try:
                self.tick()
            except Exception:
                logger.exception("Scheduler tick failed; continuing")
