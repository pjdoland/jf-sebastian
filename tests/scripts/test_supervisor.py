"""Tests for the supervisor's pure-logic units.

The Supervisor class itself spawns subprocesses and runs against wall-clock
time, so we focus on the deterministic helpers and config parsing here.
End-to-end supervision is best validated by manual integration testing.
"""

import os
import sys
import time
from pathlib import Path

import pytest

# Make scripts/ importable as a module
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import supervisor  # noqa: E402


class TestConfig:
    def test_defaults(self, monkeypatch):
        for var in [
            "HEARTBEAT_FILE", "HEARTBEAT_INTERVAL", "WATCHDOG_TIMEOUT",
            "RESTART_BACKOFF_INITIAL", "RESTART_BACKOFF_MAX",
            "HEALTHY_RUNTIME_SECS", "CRASH_REPORT_DIR", "CRASH_REPORT_TAIL",
            "LOG_PATH", "SHUTDOWN_GRACE_SECS",
        ]:
            monkeypatch.delenv(var, raising=False)
        cfg = supervisor.SupervisorConfig()
        assert cfg.heartbeat_interval == 10.0
        assert cfg.watchdog_timeout == 60.0
        assert cfg.backoff_initial == 1.0
        assert cfg.backoff_max == 60.0
        assert cfg.crash_report_tail == 100

    def test_env_overrides(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HEARTBEAT_FILE", str(tmp_path / "hb"))
        monkeypatch.setenv("WATCHDOG_TIMEOUT", "5.0")
        monkeypatch.setenv("RESTART_BACKOFF_INITIAL", "0.5")
        monkeypatch.setenv("CRASH_REPORT_TAIL", "42")
        cfg = supervisor.SupervisorConfig()
        assert cfg.heartbeat_file == tmp_path / "hb"
        assert cfg.watchdog_timeout == 5.0
        assert cfg.backoff_initial == 0.5
        assert cfg.crash_report_tail == 42

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("WATCHDOG_TIMEOUT", "not-a-number")
        cfg = supervisor.SupervisorConfig()
        assert cfg.watchdog_timeout == 60.0


class TestTailLines:
    def test_missing_file(self, tmp_path):
        assert supervisor.tail_lines(tmp_path / "nope", 10) == []

    def test_returns_last_n(self, tmp_path):
        path = tmp_path / "log"
        path.write_text("\n".join(f"line {i}" for i in range(50)) + "\n")
        result = supervisor.tail_lines(path, 5)
        assert result == [f"line {i}\n" for i in range(45, 50)]

    def test_returns_all_when_fewer_than_n(self, tmp_path):
        path = tmp_path / "log"
        path.write_text("a\nb\nc\n")
        assert supervisor.tail_lines(path, 100) == ["a\n", "b\n", "c\n"]


class TestHeartbeatAge:
    def test_missing_returns_none(self, tmp_path):
        assert supervisor.heartbeat_age(tmp_path / "nope") is None

    def test_existing_returns_age(self, tmp_path):
        path = tmp_path / "hb"
        path.touch()
        # Backdate so age is reproducibly > 0
        os.utime(path, (1000.0, 1000.0))
        age = supervisor.heartbeat_age(path)
        assert age is not None
        assert age > 0


class TestCrashReport:
    def test_writes_report_with_tail(self, tmp_path, monkeypatch):
        log = tmp_path / "jfs.log"
        log.write_text("oldest\nmiddle\nnewest\n")
        report_dir = tmp_path / "crashes"

        monkeypatch.setenv("CRASH_REPORT_DIR", str(report_dir))
        monkeypatch.setenv("LOG_PATH", str(log))
        monkeypatch.setenv("CRASH_REPORT_TAIL", "2")
        cfg = supervisor.SupervisorConfig()

        report = supervisor.write_crash_report(cfg, reason="test", exit_code=1, signal_num=None)
        assert report is not None and report.exists()
        content = report.read_text()
        assert "Reason:      test" in content
        assert "Exit code:   1" in content
        # only last 2 lines should be in the report
        assert "oldest" not in content
        assert "middle" in content
        assert "newest" in content

    def test_handles_missing_log_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CRASH_REPORT_DIR", str(tmp_path / "crashes"))
        monkeypatch.setenv("LOG_PATH", str(tmp_path / "missing.log"))
        cfg = supervisor.SupervisorConfig()
        report = supervisor.write_crash_report(cfg, reason="test", exit_code=None, signal_num=11)
        assert report is not None
        content = report.read_text()
        assert "last 0 log lines" in content


class TestBackoff:
    def test_doubles_each_call(self):
        sup = supervisor.Supervisor(supervisor.SupervisorConfig())
        sup.cfg.backoff_max = 60.0
        assert sup._next_backoff(2.0) == 4.0
        assert sup._next_backoff(4.0) == 8.0

    def test_caps_at_max(self):
        sup = supervisor.Supervisor(supervisor.SupervisorConfig())
        sup.cfg.backoff_max = 10.0
        assert sup._next_backoff(8.0) == 10.0
        assert sup._next_backoff(10.0) == 10.0


class TestRequestShutdown:
    def test_request_shutdown_sets_flag(self):
        sup = supervisor.Supervisor(supervisor.SupervisorConfig())
        assert sup._shutdown is False
        sup.request_shutdown()
        assert sup._shutdown is True


class TestHeartbeatAgeClamp:
    def test_clamps_negative_to_zero(self, tmp_path, monkeypatch):
        """A heartbeat file with mtime in the future (NTP step) shouldn't return a negative age."""
        path = tmp_path / "hb"
        path.touch()
        # Set mtime ~1 minute in the future
        future = time.time() + 60.0
        os.utime(path, (future, future))
        age = supervisor.heartbeat_age(path)
        assert age == 0.0


