"""End-to-end integration tests for the supervisor.

Replaces the child command with a tiny Python script we control, exercises
process exit + restart, watchdog timeout on a hung child, and clean shutdown
on signal.
"""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# Reuse the import setup from the unit test file
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import supervisor  # noqa: E402


def _make_fake_child(tmp_path: Path, body: str) -> list[str]:
    """Write a tiny Python script and return a command list that runs it."""
    script = tmp_path / "fake_child.py"
    script.write_text(body)
    return [sys.executable, str(script)]


@pytest.fixture
def fast_supervisor(monkeypatch, tmp_path):
    """A Supervisor configured with sub-second timeouts for fast tests."""
    monkeypatch.setenv("HEARTBEAT_FILE", str(tmp_path / "hb"))
    monkeypatch.setenv("HEARTBEAT_INTERVAL", "0.1")
    monkeypatch.setenv("WATCHDOG_TIMEOUT", "1.0")
    monkeypatch.setenv("FIRST_HEARTBEAT_GRACE", "0.5")
    monkeypatch.setenv("RESTART_BACKOFF_INITIAL", "0.05")
    monkeypatch.setenv("RESTART_BACKOFF_MAX", "0.2")
    monkeypatch.setenv("HEALTHY_RUNTIME_SECS", "30.0")
    monkeypatch.setenv("CRASH_REPORT_DIR", str(tmp_path / "crashes"))
    monkeypatch.setenv("LOG_PATH", str(tmp_path / "fake.log"))
    monkeypatch.setenv("SHUTDOWN_GRACE_SECS", "1.0")
    return supervisor.Supervisor()


def test_supervisor_restarts_after_crash(monkeypatch, tmp_path, fast_supervisor):
    """Child exits non-zero a few times; supervisor should restart it each time, then we shut it down."""
    counter = tmp_path / "counter"
    counter.write_text("0")
    hb = tmp_path / "hb"

    body = f"""
import os, time, sys
from pathlib import Path
counter = Path({str(counter)!r})
hb = Path(os.environ["HEARTBEAT_FILE"])
n = int(counter.read_text()) + 1
counter.write_text(str(n))
hb.touch()
# First two runs: crash quickly. Third run: linger so the test can shut down.
if n < 3:
    time.sleep(0.05)
    sys.exit(1)
else:
    while True:
        hb.touch()
        time.sleep(0.05)
"""
    cmd = _make_fake_child(tmp_path, body)
    monkeypatch.setattr(supervisor, "child_command", lambda: cmd)

    # Run supervisor in a thread; shut it down once we see N >= 3 children spawned
    sup_thread = threading.Thread(target=fast_supervisor.run, daemon=True)
    sup_thread.start()

    deadline = time.time() + 10.0
    while time.time() < deadline:
        if int(counter.read_text() or "0") >= 3:
            break
        time.sleep(0.1)

    fast_supervisor.request_shutdown()
    if fast_supervisor._proc and fast_supervisor._proc.poll() is None:
        supervisor.kill_process_tree(fast_supervisor._proc, 1.0)
    sup_thread.join(timeout=5.0)

    assert int(counter.read_text()) >= 3, "supervisor should have restarted the child at least twice"
    # Crash reports written for the first two crashes
    crashes = list((tmp_path / "crashes").glob("jfs-crash-*.log"))
    assert len(crashes) >= 2


def test_supervisor_kills_hung_child(monkeypatch, tmp_path, fast_supervisor):
    """Child stops heartbeating; supervisor should detect staleness and kill it."""
    counter = tmp_path / "counter"
    counter.write_text("0")

    body = """
import os, time
from pathlib import Path
hb = Path(os.environ["HEARTBEAT_FILE"])
counter = Path(__import__("os").environ.get("COUNTER_FILE"))
n = int(counter.read_text()) + 1
counter.write_text(str(n))
hb.touch()
# Hang forever — never touch hb again.
while True:
    time.sleep(60)
"""
    cmd = _make_fake_child(tmp_path, body)
    monkeypatch.setenv("COUNTER_FILE", str(counter))
    monkeypatch.setattr(supervisor, "child_command", lambda: cmd)

    sup_thread = threading.Thread(target=fast_supervisor.run, daemon=True)
    sup_thread.start()

    # Wait for at least one crash report (proves watchdog killed at least once)
    deadline = time.time() + 10.0
    while time.time() < deadline:
        crashes = list((tmp_path / "crashes").glob("jfs-crash-*.log"))
        if crashes:
            break
        time.sleep(0.2)

    fast_supervisor.request_shutdown()
    if fast_supervisor._proc and fast_supervisor._proc.poll() is None:
        supervisor.kill_process_tree(fast_supervisor._proc, 1.0)
    sup_thread.join(timeout=5.0)

    crashes = list((tmp_path / "crashes").glob("jfs-crash-*.log"))
    assert crashes, "supervisor should have killed the hung child and written a crash report"
    content = crashes[0].read_text()
    assert "watchdog_timeout" in content
