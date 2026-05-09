"""Tests for the heartbeat utility."""

import os
import time
from pathlib import Path

from jf_sebastian.utils.heartbeat import Heartbeat, heartbeat_age


def test_touch_creates_file(tmp_path):
    path = tmp_path / "hb"
    Heartbeat(path).touch()
    assert path.exists()


def test_touch_updates_mtime(tmp_path):
    path = tmp_path / "hb"
    hb = Heartbeat(path)
    hb.touch()
    first = path.stat().st_mtime
    time.sleep(0.05)
    hb.touch()
    second = path.stat().st_mtime
    assert second >= first


def test_start_creates_parent_directory(tmp_path):
    """start() creates intermediate dirs so touch() can stay cheap on the hot path."""
    path = tmp_path / "deeply" / "nested" / "hb"
    hb = Heartbeat(path, interval=0.1)
    hb.start()
    try:
        assert path.exists()
    finally:
        hb.stop()


def test_thread_updates_periodically(tmp_path):
    path = tmp_path / "hb"
    hb = Heartbeat(path, interval=0.05)
    hb.start()
    try:
        # Wait long enough for at least one beat after start (start does an
        # initial touch synchronously, then the thread waits `interval` before
        # touching again).
        time.sleep(0.2)
        first = path.stat().st_mtime
        time.sleep(0.15)
        second = path.stat().st_mtime
        assert second > first, "heartbeat thread should update mtime over time"
    finally:
        hb.stop()


def test_stop_halts_thread(tmp_path):
    path = tmp_path / "hb"
    hb = Heartbeat(path, interval=0.05)
    hb.start()
    time.sleep(0.1)
    hb.stop()
    frozen = path.stat().st_mtime
    time.sleep(0.2)
    assert path.stat().st_mtime == frozen, "no further updates after stop()"


def test_start_is_idempotent(tmp_path):
    path = tmp_path / "hb"
    hb = Heartbeat(path, interval=0.1)
    hb.start()
    thread1 = hb._thread
    hb.start()
    thread2 = hb._thread
    assert thread1 is thread2
    hb.stop()


def test_minimum_interval_clamped():
    """A negative or zero interval should still produce a valid heartbeat."""
    hb = Heartbeat(Path("/tmp/_unused_test_hb"), interval=0)
    assert hb.interval >= 0.1


def test_heartbeat_age_missing_returns_none(tmp_path):
    assert heartbeat_age(tmp_path / "nope") is None


def test_heartbeat_age_recent_file(tmp_path):
    path = tmp_path / "hb"
    path.touch()
    age = heartbeat_age(path)
    assert age is not None
    assert age >= 0
    assert age < 5  # touch was just now


def test_heartbeat_age_clamps_negative_to_zero(tmp_path):
    """Future-dated mtime (NTP step backwards) should clamp at 0."""
    path = tmp_path / "hb"
    path.touch()
    future = time.time() + 60
    os.utime(path, (future, future))
    assert heartbeat_age(path) == 0.0
