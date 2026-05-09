#!/usr/bin/env python3
"""
Supervisor for J.F. Sebastian.

Wraps `python -m jf_sebastian.main` and:
- Restarts the child on unexpected exit, with exponential backoff (capped).
- Detects a hung child via heartbeat-file staleness; SIGTERMs (then SIGKILLs) it.
- Writes a crash report to CRASH_REPORT_DIR with the last N lines of jf_sebastian.log.
- Forwards SIGTERM/SIGINT cleanly to the child and exits without restarting.

Designed to be run by launchd (macOS) or systemd (Linux); see scripts/jf-sebastian.plist
and scripts/jf-sebastian.service for sample unit files.

Configurable via env (sensible defaults are baked in):
- HEARTBEAT_FILE         path to the heartbeat file the child touches (also passed to child)
- HEARTBEAT_INTERVAL     seconds between child heartbeats (default 10.0; passed to child)
- WATCHDOG_TIMEOUT       seconds without heartbeat before the child is considered hung (default 60.0)
- RESTART_BACKOFF_INITIAL  initial restart delay (default 1.0)
- RESTART_BACKOFF_MAX      cap on restart delay (default 60.0)
- HEALTHY_RUNTIME_SECS   if the child runs at least this long, reset backoff to initial (default 60.0)
- CRASH_REPORT_DIR       directory for crash reports (default ./crash_reports)
- CRASH_REPORT_TAIL      lines of jf_sebastian.log to include in each report (default 100)
- LOG_PATH               path to jf_sebastian.log to tail (default jf_sebastian.log)
- SHUTDOWN_GRACE_SECS    SIGTERM-to-SIGKILL grace period (default 10.0)
- FIRST_HEARTBEAT_GRACE  seconds to allow for child startup before enforcing watchdog (default 60.0)
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [supervisor] %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("jfs.supervisor")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, os.environ.get(name), default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, os.environ.get(name), default)
        return default


class SupervisorConfig:
    def __init__(self) -> None:
        self.heartbeat_file = Path(os.environ.get("HEARTBEAT_FILE", "/tmp/jf_sebastian.heartbeat"))
        self.heartbeat_interval = _env_float("HEARTBEAT_INTERVAL", 10.0)
        self.watchdog_timeout = _env_float("WATCHDOG_TIMEOUT", 60.0)
        self.first_heartbeat_grace = _env_float("FIRST_HEARTBEAT_GRACE", 60.0)
        self.backoff_initial = _env_float("RESTART_BACKOFF_INITIAL", 1.0)
        self.backoff_max = _env_float("RESTART_BACKOFF_MAX", 60.0)
        self.healthy_runtime = _env_float("HEALTHY_RUNTIME_SECS", 60.0)
        self.crash_report_dir = Path(os.environ.get("CRASH_REPORT_DIR", "./crash_reports"))
        self.crash_report_tail = _env_int("CRASH_REPORT_TAIL", 100)
        self.log_path = Path(os.environ.get("LOG_PATH", "jf_sebastian.log"))
        self.shutdown_grace = _env_float("SHUTDOWN_GRACE_SECS", 10.0)


def tail_lines(path: Path, n: int) -> list[str]:
    """Return the last n lines of a file. Streams via deque for O(n) memory."""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return list(deque(f, maxlen=n))
    except OSError as e:
        logger.warning("Could not read %s for crash report: %s", path, e)
        return []


def write_crash_report(
    cfg: SupervisorConfig,
    reason: str,
    exit_code: Optional[int],
    signal_num: Optional[int],
    pid: Optional[int] = None,
    ran_for: Optional[float] = None,
    heartbeat_age_at_exit: Optional[float] = None,
) -> Optional[Path]:
    """Persist a crash report and return its path."""
    try:
        cfg.crash_report_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("Could not create crash report dir %s: %s", cfg.crash_report_dir, e)
        return None

    # Microsecond suffix prevents two rapid crashes from clobbering each other.
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    report = cfg.crash_report_dir / f"jfs-crash-{timestamp}.log"
    log_tail = tail_lines(cfg.log_path, cfg.crash_report_tail)

    try:
        with report.open("w", encoding="utf-8") as f:
            f.write("J.F. Sebastian crash report\n")
            f.write(f"Generated:   {datetime.now().isoformat()}\n")
            f.write(f"Hostname:    {socket.gethostname()}\n")
            f.write(f"Reason:      {reason}\n")
            f.write(f"Exit code:   {exit_code}\n")
            f.write(f"Signal:      {signal_num}\n")
            f.write(f"PID:         {pid}\n")
            f.write(f"Personality: {os.environ.get('PERSONALITY', '?')}\n")
            f.write(f"Python:      {sys.version.splitlines()[0]}\n")
            if ran_for is not None:
                f.write(f"Ran for:     {ran_for:.1f}s\n")
            if heartbeat_age_at_exit is not None:
                f.write(f"Heartbeat age at exit: {heartbeat_age_at_exit:.1f}s\n")
            f.write(f"Log path:    {cfg.log_path}\n")
            f.write(f"\n--- last {len(log_tail)} log lines ---\n")
            f.writelines(log_tail)
    except OSError as e:
        logger.warning("Could not write crash report %s: %s", report, e)
        return None

    logger.info("Crash report written: %s", report)
    return report


def heartbeat_age(path: Path) -> Optional[float]:
    """Seconds since the heartbeat file was last touched, or None if missing.

    Clamped at 0 to tolerate small NTP backwards-jumps; large stale ages
    still flow through to trigger the watchdog as expected.
    """
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except (OSError, FileNotFoundError):
        return None


def child_command() -> list[str]:
    """The command to run as the child. Currently `python -m jf_sebastian.main`."""
    return [sys.executable, "-m", "jf_sebastian.main"]


def _terminate_group(proc: subprocess.Popen, sig: int) -> None:
    """Send `sig` to the child's process group; fall back to the immediate child."""
    try:
        os.killpg(os.getpgid(proc.pid), sig)
        return
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        if sig == signal.SIGKILL:
            proc.kill()
        else:
            proc.terminate()
    except ProcessLookupError:
        return


def kill_process_tree(proc: subprocess.Popen, grace: float) -> None:
    """SIGTERM the child's process group; SIGKILL after `grace` if still alive."""
    if proc.poll() is not None:
        return
    _terminate_group(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    logger.warning("Child still alive after %.1fs; sending SIGKILL", grace)
    _terminate_group(proc, signal.SIGKILL)
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        logger.error("Child did not die after SIGKILL")
    except OSError:
        pass


class Supervisor:
    def __init__(self, cfg: Optional[SupervisorConfig] = None) -> None:
        self.cfg = cfg or SupervisorConfig()
        self._shutdown = False
        self._proc: Optional[subprocess.Popen] = None

    def request_shutdown(self) -> None:
        """Request the supervisor to exit cleanly. Safe from any context including signal handlers."""
        self._shutdown = True

    def _install_signal_handlers(self) -> None:
        # Trivial handlers: only flip the shutdown flag. The main loop polls it
        # at ~1s cadence and tears down the child via kill_process_tree on its
        # own thread, where wait() / killpg() is safe.
        def handler(sig, _frame):
            logger.info("Received signal %s; requesting shutdown", sig)
            self.request_shutdown()

        try:
            signal.signal(signal.SIGTERM, handler)
            signal.signal(signal.SIGINT, handler)
        except ValueError:
            # signal.signal() only works on the main thread; skipping is fine
            # in test contexts where the supervisor runs from a worker thread.
            logger.debug("Skipping signal handler install (not on main thread)")

    def _spawn(self) -> subprocess.Popen:
        env = os.environ.copy()
        # Make sure the child knows where to heartbeat, even if user only set
        # supervisor-side env vars.
        env["HEARTBEAT_FILE"] = str(self.cfg.heartbeat_file)
        env.setdefault("HEARTBEAT_INTERVAL", str(self.cfg.heartbeat_interval))
        # Ensure the heartbeat directory exists; clear stale file from a prior run.
        try:
            self.cfg.heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            if self.cfg.heartbeat_file.exists():
                self.cfg.heartbeat_file.unlink()
        except OSError:
            pass
        logger.info("Starting child: %s", " ".join(child_command()))
        # start_new_session=True puts the child in its own process group so we
        # can SIGTERM/SIGKILL the whole tree (RVC, ffmpeg, anything else it forks).
        return subprocess.Popen(child_command(), env=env, start_new_session=True)

    def _watch(self, proc: subprocess.Popen) -> tuple[str, Optional[int], Optional[int], Optional[float]]:
        """Watch a child until it exits or hangs. Returns (reason, exit_code, signal_num, hb_age_at_exit)."""
        start_mono = time.monotonic()

        while not self._shutdown:
            rc = proc.poll()
            if rc is not None:
                hb = heartbeat_age(self.cfg.heartbeat_file)
                # Negative return code on POSIX = killed by signal -rc
                if rc < 0:
                    return ("signal", rc, -rc, hb)
                if rc == 0:
                    return ("clean_exit", 0, None, hb)
                return ("nonzero_exit", rc, None, hb)

            elapsed = time.monotonic() - start_mono
            age = heartbeat_age(self.cfg.heartbeat_file)
            # During the startup grace window, we don't enforce either branch;
            # the child may legitimately take time to write its first heartbeat
            # (RVC warmup, model loading, etc.).
            if elapsed >= self.cfg.first_heartbeat_grace:
                if age is None:
                    logger.warning(
                        "No heartbeat file after %.1fs (expected %s); treating as hung",
                        elapsed, self.cfg.heartbeat_file,
                    )
                    kill_process_tree(proc, self.cfg.shutdown_grace)
                    return ("no_heartbeat", proc.poll(), None, None)
                if age > self.cfg.watchdog_timeout:
                    logger.warning(
                        "Heartbeat is %.1fs stale (limit %.1fs); killing hung child",
                        age, self.cfg.watchdog_timeout,
                    )
                    kill_process_tree(proc, self.cfg.shutdown_grace)
                    return ("watchdog_timeout", proc.poll(), None, age)

            time.sleep(min(1.0, self.cfg.heartbeat_interval / 2))

        # Shutdown was requested. Tear the child down here on the main thread,
        # not from inside the signal handler.
        if proc.poll() is None:
            kill_process_tree(proc, self.cfg.shutdown_grace)
        return ("shutdown", proc.poll(), None, heartbeat_age(self.cfg.heartbeat_file))

    def _next_backoff(self, current: float) -> float:
        """Double the backoff, capped at max. (Reset-to-initial is computed separately.)"""
        return min(current * 2, self.cfg.backoff_max)

    def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep up to `seconds` total, breaking out promptly if shutdown is requested."""
        deadline = time.monotonic() + seconds
        while not self._shutdown:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.5, remaining))

    def run(self) -> int:
        self._install_signal_handlers()
        backoff = self.cfg.backoff_initial
        while not self._shutdown:
            start_mono = time.monotonic()
            try:
                self._proc = self._spawn()
            except OSError as e:
                logger.error("Failed to spawn child: %s", e)
                self._interruptible_sleep(backoff)
                backoff = self._next_backoff(backoff)
                continue

            reason, exit_code, signal_num, hb_age = self._watch(self._proc)
            ran_for = time.monotonic() - start_mono
            logger.info(
                "Child exited: reason=%s code=%s signal=%s after %.1fs",
                reason, exit_code, signal_num, ran_for,
            )

            if reason in ("clean_exit", "shutdown"):
                return 0

            write_crash_report(
                self.cfg, reason, exit_code, signal_num,
                pid=self._proc.pid if self._proc else None,
                ran_for=ran_for,
                heartbeat_age_at_exit=hb_age,
            )

            if self._shutdown:
                return 0

            # Reset backoff if the child ran long enough to be considered healthy,
            # *before* we sleep — otherwise we'd pay the pre-healthy backoff once
            # more before resetting on the next iteration.
            if ran_for >= self.cfg.healthy_runtime:
                backoff = self.cfg.backoff_initial

            logger.info("Restarting in %.1fs", backoff)
            self._interruptible_sleep(backoff)
            backoff = self._next_backoff(backoff)

        return 0


def main(argv: Optional[list[str]] = None) -> int:
    return Supervisor().run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
