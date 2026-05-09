"""Tests for the proactive scheduler."""

from datetime import datetime, time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jf_sebastian.modules.scheduler import (
    ProactiveScheduler,
    ScheduledEvent,
    Schedule,
    _is_quiet,
    _parse_when,
    _should_fire,
    load_scheduled_events,
    parse_time_or_none,
)


class TestParseWhen:
    def test_daily_time(self):
        sched = _parse_when("07:00")
        assert sched == Schedule(time(7, 0), None, None)

    def test_one_digit_hour(self):
        assert _parse_when("7:00").tod == time(7, 0)

    def test_weekdays_single(self):
        sched = _parse_when("21:00 mon")
        assert sched.tod == time(21, 0)
        assert sched.weekdays == {0}
        assert sched.one_shot_date is None

    def test_weekdays_multiple(self):
        assert _parse_when("17:00 mon,wed,fri").weekdays == {0, 2, 4}

    def test_weekday_case_insensitive(self):
        assert _parse_when("12:00 SAT,Sun").weekdays == {5, 6}

    def test_one_shot_date(self):
        sched = _parse_when("08:00 2026-12-25")
        assert sched.tod == time(8, 0)
        assert sched.weekdays is None
        assert sched.one_shot_date.year == 2026

    def test_weekdays_alias_expands_to_mon_fri(self):
        sched = _parse_when("07:00 weekdays")
        assert sched.weekdays == {0, 1, 2, 3, 4}

    def test_weekends_alias(self):
        sched = _parse_when("11:00 weekends")
        assert sched.weekdays == {5, 6}

    def test_alias_combined_with_explicit_day(self):
        # Allowed: union of all listed tokens
        sched = _parse_when("12:00 weekends,wed")
        assert sched.weekdays == {2, 5, 6}

    def test_weekdays_and_weekends_combined(self):
        """Pinned behavior: writing both aliases produces every day of the week."""
        assert _parse_when("07:00 weekdays,weekends").weekdays == {0, 1, 2, 3, 4, 5, 6}

    def test_empty_csv_token_gives_helpful_error(self):
        with pytest.raises(ValueError, match="empty weekday token"):
            _parse_when("07:00 mon,")
        with pytest.raises(ValueError, match="empty weekday token"):
            _parse_when("07:00 mon,,tue")

    def test_whitespace_in_token_gives_helpful_error(self):
        with pytest.raises(ValueError, match="comma-separated"):
            _parse_when("07:00 mon mon")

    def test_invalid_time(self):
        with pytest.raises(ValueError, match="HH:MM"):
            _parse_when("nope")

    def test_invalid_hour(self):
        with pytest.raises(ValueError, match="invalid time-of-day"):
            _parse_when("25:00")

    def test_invalid_minute(self):
        with pytest.raises(ValueError, match="invalid time-of-day"):
            _parse_when("12:99")

    def test_invalid_weekday(self):
        with pytest.raises(ValueError, match="unknown weekday"):
            _parse_when("12:00 funday")

    def test_invalid_date(self):
        with pytest.raises(ValueError, match="invalid date"):
            _parse_when("08:00 2026-13-99")


class TestIsQuiet:
    def test_no_quiet_window(self):
        assert _is_quiet(datetime(2026, 5, 1, 23, 0), None, None) is False

    def test_inside_simple_window(self):
        # quiet 09:00 → 17:00 ; 12:00 is inside
        assert _is_quiet(datetime(2026, 5, 1, 12, 0), time(9), time(17)) is True

    def test_outside_simple_window(self):
        assert _is_quiet(datetime(2026, 5, 1, 8, 0), time(9), time(17)) is False

    def test_at_window_start_is_quiet(self):
        assert _is_quiet(datetime(2026, 5, 1, 9, 0), time(9), time(17)) is True

    def test_at_window_end_is_not_quiet(self):
        # Half-open: [start, end)
        assert _is_quiet(datetime(2026, 5, 1, 17, 0), time(9), time(17)) is False

    def test_overnight_window_late_night(self):
        # quiet 22:00 → 07:00 ; 23:00 is inside
        assert _is_quiet(datetime(2026, 5, 1, 23, 0), time(22), time(7)) is True

    def test_overnight_window_early_morning(self):
        # 03:00 is inside the 22:00 → 07:00 window
        assert _is_quiet(datetime(2026, 5, 1, 3, 0), time(22), time(7)) is True

    def test_overnight_window_daytime(self):
        # 12:00 is outside 22:00 → 07:00
        assert _is_quiet(datetime(2026, 5, 1, 12, 0), time(22), time(7)) is False


class TestShouldFire:
    def test_daily_fires_at_exact_time(self):
        ev = ScheduledEvent(name="morning", when="07:00", say="hi")
        # Wednesday 7:00:30
        assert _should_fire(ev, datetime(2026, 5, 6, 7, 0, 30)) is True

    def test_daily_does_not_fire_at_other_minute(self):
        ev = ScheduledEvent(name="morning", when="07:00", say="hi")
        assert _should_fire(ev, datetime(2026, 5, 6, 7, 1, 0)) is False
        assert _should_fire(ev, datetime(2026, 5, 6, 6, 59, 59)) is False

    def test_weekday_filter(self):
        ev = ScheduledEvent(name="weekly", when="12:00 mon", say="hi")
        # 2026-05-04 is a Monday
        assert _should_fire(ev, datetime(2026, 5, 4, 12, 0)) is True
        # 2026-05-05 is a Tuesday
        assert _should_fire(ev, datetime(2026, 5, 5, 12, 0)) is False

    def test_one_shot_date(self):
        ev = ScheduledEvent(name="xmas", when="08:00 2026-12-25", say="hi")
        assert _should_fire(ev, datetime(2026, 12, 25, 8, 0)) is True
        assert _should_fire(ev, datetime(2026, 12, 26, 8, 0)) is False

    def test_does_not_double_fire_same_minute(self):
        ev = ScheduledEvent(name="morning", when="07:00", say="hi")
        now = datetime(2026, 5, 6, 7, 0, 5)
        assert _should_fire(ev, now) is True
        ev._last_fired = now
        # Same minute, later second
        assert _should_fire(ev, datetime(2026, 5, 6, 7, 0, 45)) is False

    def test_fires_again_next_day(self):
        ev = ScheduledEvent(name="morning", when="07:00", say="hi")
        ev._last_fired = datetime(2026, 5, 6, 7, 0, 5)
        # Next day, same time
        assert _should_fire(ev, datetime(2026, 5, 7, 7, 0, 5)) is True


class TestEventValidation:
    def test_requires_say_or_prompt(self):
        with pytest.raises(ValueError, match="say.*prompt"):
            ScheduledEvent(name="bad", when="07:00")

    def test_rejects_both_say_and_prompt(self):
        with pytest.raises(ValueError, match="cannot set both"):
            ScheduledEvent(name="bad", when="07:00", say="hi", prompt="hello")

    def test_rejects_invalid_when(self):
        with pytest.raises(ValueError):
            ScheduledEvent(name="bad", when="not-a-time", say="hi")


class TestLoadScheduledEvents:
    def test_missing_file_returns_empty(self, tmp_path):
        events, qs, qe = load_scheduled_events(tmp_path / "nope.yaml")
        assert events == []
        assert qs is None and qe is None

    def test_loads_full_yaml(self, tmp_path):
        path = tmp_path / "se.yaml"
        path.write_text(
            "quiet_hours:\n"
            "  start: '22:00'\n"
            "  end: '07:00'\n"
            "events:\n"
            "  - name: morning\n"
            "    when: '08:00'\n"
            "    say: 'hi'\n"
            "  - name: weekly\n"
            "    when: '12:00 mon,wed'\n"
            "    prompt: 'tell a joke'\n"
        )
        events, qs, qe = load_scheduled_events(path)
        assert len(events) == 2
        assert events[0].name == "morning"
        assert events[0].say == "hi"
        assert events[1].prompt == "tell a joke"
        assert qs == time(22, 0)
        assert qe == time(7, 0)

    def test_skips_invalid_event_keeps_valid(self, tmp_path):
        path = tmp_path / "se.yaml"
        path.write_text(
            "events:\n"
            "  - name: ok\n"
            "    when: '08:00'\n"
            "    say: 'hi'\n"
            "  - name: bad\n"
            "    when: 'not-a-time'\n"
            "    say: 'hi'\n"
        )
        events, _, _ = load_scheduled_events(path)
        assert len(events) == 1
        assert events[0].name == "ok"

    def test_invalid_yaml_returns_empty(self, tmp_path):
        path = tmp_path / "se.yaml"
        path.write_text("this is: not: valid: yaml: at all: [\n")
        events, qs, qe = load_scheduled_events(path)
        assert events == []
        assert qs is None and qe is None

    def test_personality_yaml_loads(self):
        """The Johnny sample bundled with the repo should parse cleanly."""
        path = Path(__file__).resolve().parents[2] / "personalities" / "johnny" / "scheduled_events.yaml"
        assert path.exists()
        events, qs, qe = load_scheduled_events(path)
        assert len(events) >= 1
        assert qs == time(22, 0)
        assert qe == time(7, 0)

    def test_past_one_shot_date_warns(self, tmp_path, caplog):
        path = tmp_path / "se.yaml"
        path.write_text(
            "events:\n"
            "  - name: long_ago\n"
            "    when: '08:00 2020-01-01'\n"
            "    say: 'hi'\n"
        )
        with caplog.at_level("WARNING"):
            events, _, _ = load_scheduled_events(path)
        # Event still loads (don't surprise users by silently dropping it),
        # but a warning is emitted so they can see the date is stale.
        assert len(events) == 1
        assert any("past one-shot date" in r.message for r in caplog.records)

    def test_invalid_event_warning_includes_event_name(self, tmp_path, caplog):
        path = tmp_path / "se.yaml"
        path.write_text(
            "events:\n"
            "  - name: my_typo\n"
            "    when: 'not-a-time'\n"
            "    say: 'hi'\n"
        )
        with caplog.at_level("WARNING"):
            load_scheduled_events(path)
        # Warning should name the event so the user can find it in the YAML.
        assert any("my_typo" in r.message for r in caplog.records)

    def test_event_inside_quiet_hours_warns_at_load(self, tmp_path, caplog):
        """Mike sets quiet hours and schedules inside them — must surface at load."""
        path = tmp_path / "se.yaml"
        path.write_text(
            "quiet_hours:\n"
            "  start: '22:00'\n"
            "  end: '07:00'\n"
            "events:\n"
            "  - name: too_early\n"
            "    when: '06:30'\n"
            "    say: 'hi'\n"
            "  - name: morning_ok\n"
            "    when: '08:30'\n"
            "    say: 'hi'\n"
        )
        with caplog.at_level("WARNING"):
            events, _, _ = load_scheduled_events(path)
        assert len(events) == 2  # both load
        warnings = [r.message for r in caplog.records if "quiet_hours" in r.message]
        assert any("too_early" in w for w in warnings)
        assert not any("morning_ok" in w for w in warnings)


class TestParseTimeOrNone:
    def test_valid(self):
        assert parse_time_or_none("07:30") == time(7, 30)

    def test_none(self):
        assert parse_time_or_none(None) is None

    def test_empty(self):
        assert parse_time_or_none("") is None

    def test_invalid_format(self, caplog):
        with caplog.at_level("WARNING"):
            assert parse_time_or_none("nope") is None
        assert any("Invalid HH:MM" in r.message for r in caplog.records)

    def test_out_of_range(self, caplog):
        with caplog.at_level("WARNING"):
            assert parse_time_or_none("25:00") is None


class TestProactiveScheduler:
    def test_tick_fires_event(self):
        ev = ScheduledEvent(name="morning", when="07:00", say="hi")
        callback = MagicMock()
        sched = ProactiveScheduler([ev], on_fire=callback)
        sched.tick(now=datetime(2026, 5, 6, 7, 0))
        callback.assert_called_once_with(ev)

    def test_tick_respects_quiet_hours(self):
        ev = ScheduledEvent(name="morning", when="07:00", say="hi")
        callback = MagicMock()
        # Make 07:00 fall inside the quiet window 22:00 → 09:00
        sched = ProactiveScheduler(
            [ev], on_fire=callback, quiet_start=time(22), quiet_end=time(9),
        )
        sched.tick(now=datetime(2026, 5, 6, 7, 0))
        callback.assert_not_called()

    def test_tick_doesnt_fire_outside_window(self):
        ev = ScheduledEvent(name="morning", when="07:00", say="hi")
        callback = MagicMock()
        sched = ProactiveScheduler([ev], on_fire=callback)
        sched.tick(now=datetime(2026, 5, 6, 6, 59))
        callback.assert_not_called()

    def test_callback_exception_doesnt_kill_scheduler(self):
        ev = ScheduledEvent(name="morning", when="07:00", say="hi")
        ev2 = ScheduledEvent(name="afternoon", when="07:00", say="hello")
        callback = MagicMock(side_effect=[RuntimeError("boom"), None])
        sched = ProactiveScheduler([ev, ev2], on_fire=callback)
        # First event raises, second still gets called
        sched.tick(now=datetime(2026, 5, 6, 7, 0))
        assert callback.call_count == 2

    def test_start_no_op_when_no_events(self):
        sched = ProactiveScheduler([], on_fire=MagicMock())
        sched.start()
        # No thread should have started
        assert sched._thread is None

    def test_start_idempotent(self):
        ev = ScheduledEvent(name="x", when="00:00", say="x")
        sched = ProactiveScheduler([ev], on_fire=MagicMock(), tick_seconds=10)
        try:
            sched.start()
            t1 = sched._thread
            sched.start()
            t2 = sched._thread
            assert t1 is t2
        finally:
            sched.stop()

    def test_tick_seconds_clamped_to_59(self, caplog):
        ev = ScheduledEvent(name="x", when="00:00", say="x")
        with caplog.at_level("WARNING"):
            sched = ProactiveScheduler([ev], on_fire=MagicMock(), tick_seconds=120)
        assert sched.tick_seconds == 59.0
        assert any("clamping to 59" in r.message for r in caplog.records)

    def test_start_logs_each_event(self, caplog):
        ev1 = ScheduledEvent(name="alpha", when="00:00", say="hi")
        ev2 = ScheduledEvent(name="beta", when="01:00", prompt="tell me")
        sched = ProactiveScheduler([ev1, ev2], on_fire=MagicMock(), tick_seconds=10)
        with caplog.at_level("INFO"):
            try:
                sched.start()
            finally:
                sched.stop()
        messages = [r.message for r in caplog.records]
        # Each event itemized in the start() log so a user watching can verify.
        assert any("alpha" in m and "say" in m for m in messages)
        assert any("beta" in m and "prompt" in m for m in messages)
