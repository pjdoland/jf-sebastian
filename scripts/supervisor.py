#!/usr/bin/env python3
"""
Supervisor for J.F. Sebastian.

Wraps `python -m jf_sebastian.main` and:
- Restarts the child on unexpected exit, with exponential backoff (capped).
- Detects a hung child via heartbeat-file staleness; SIGTERMs (then SIGKILLs) it.
- Writes a crash report to CRASH_REPORT_DIR with the last N lines of jf_sebastian.log.
- After N consecutive non-healthy crashes, switches to a longer "permanent failure"
  backoff and logs CRITICAL once so a museum SRE can see something is wrong.
- Prunes old crash reports so a stuck deployment can't fill the disk.
- Forwards SIGTERM/SIGINT cleanly to the child and exits without restarting.

Designed to be run by launchd (macOS) or systemd (Linux); see scripts/jf-sebastian.plist
and scripts/jf-sebastian.service for sample unit files.

Configurable via env (sensible defaults are baked in):
- HEARTBEAT_FILE              path to the heartbeat file the child touches (also passed to child)
- HEARTBEAT_INTERVAL          seconds between child heartbeats (default 10.0; passed to child)
- WATCHDOG_TIMEOUT            seconds without heartbeat before the child is considered hung (default 60.0)
- RESTART_BACKOFF_INITIAL     initial restart delay (default 1.0)
- RESTART_BACKOFF_MAX          cap on restart delay (default 60.0)
- HEALTHY_RUNTIME_SECS        if the child runs at least this long, reset backoff to initial (default 60.0)
- PERMANENT_FAILURE_THRESHOLD consecutive crash count after which we slow restarts (default 5)
- PERMANENT_FAILURE_BACKOFF   slow-restart delay in permanent-failure mode (default 600.0 s = 10 min)
- CRASH_REPORT_DIR            directory for crash reports (default ./crash_reports)
- CRASH_REPORT_TAIL           lines of jf_sebastian.log to include in each report (default 100)
- CRASH_REPORT_KEEP           max number of crash reports to retain (default 200; older are pruned)
- LOG_PATH                    path to jf_sebastian.log to tail (default jf_sebastian.log, relative to CWD)
- SUPERVISOR_LOG_PATH         path to the supervisor's own rotating log (default supervisor.log relative to CWD)
- SHUTDOWN_GRACE_SECS         SIGTERM-to-SIGKILL grace period (default 10.0)
- FIRST_HEARTBEAT_GRACE       seconds to allow for child startup before enforcing watchdog (default 60.0)
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

# Make jf_sebastian importable when running this script directly.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from jf_sebastian.utils.heartbeat import heartbeat_age  # noqa: E402


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


def _setup_logging(log_path: Path) -> None:
    """Configure supervisor logging: stdout (for launchd/journal capture) + rotating file."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                str(log_path), maxBytes=10 * 1024 * 1024, backupCount=5
            )
        )
    except OSError as e:
        # Non-fatal: keep stdout-only logging if file can't be opened.
        sys.stderr.write(f"[supervisor] could not open {log_path} for logging: {e}\n")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [supervisor] %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


# Logger initialized after _setup_logging is called from main(); module-level
# default lets early helpers (e.g. _env_float on import) emit warnings sanely.
logger = logging.getLogger("jfs.supervisor")


class SupervisorConfig:
    def __init__(self) -> None:
        self.heartbeat_file = Path(os.environ.get("HEARTBEAT_FILE", "/tmp/jf_sebastian.heartbeat"))
        self.heartbeat_interval = _env_float("HEARTBEAT_INTERVAL", 10.0)
        self.watchdog_timeout = _env_float("WATCHDOG_TIMEOUT", 60.0)
        self.first_heartbeat_grace = _env_float("FIRST_HEARTBEAT_GRACE", 60.0)
        self.backoff_initial = _env_float("RESTART_BACKOFF_INITIAL", 1.0)
        self.backoff_max = _env_float("RESTART_BACKOFF_MAX", 60.0)
        self.healthy_runtime = _env_float("HEALTHY_RUNTIME_SECS", 60.0)
        self.permanent_failure_threshold = _env_int("PERMANENT_FAILURE_THRESHOLD", 5)
        self.permanent_failure_backoff = _env_float("PERMANENT_FAILURE_BACKOFF", 600.0)
        self.crash_report_dir = Path(os.environ.get("CRASH_REPORT_DIR", "./crash_reports"))
        self.crash_report_tail = _env_int("CRASH_REPORT_TAIL", 100)
        self.crash_report_keep = _env_int("CRASH_REPORT_KEEP", 200)
        self.log_path = Path(os.environ.get("LOG_PATH", "jf_sebastian.log"))
        self.supervisor_log_path = Path(
            os.environ.get("SUPERVISOR_LOG_PATH", "supervisor.log")
        )
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


def _prune_crash_reports(report_dir: Path, keep: int) -> None:
    """Keep only the `keep` most recent crash reports. Filename timestamps are
    `%Y%m%d-%H%M%S-%f` so lexicographic sort is chronological."""
    if keep <= 0:
        return
    try:
        files = sorted(report_dir.glob("jfs-crash-*.log"))
    except OSError:
        return
    for old in files[:-keep]:
        try:
            old.unlink()
        except OSError as e:
            logger.warning("Could not prune crash report %s: %s", old, e)


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
    _prune_crash_reports(cfg.crash_report_dir, cfg.crash_report_keep)
    return report


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


def kill_process_tree(proc: subprocess.Popen, grace: float) -> bool:
    """SIGTERM the child's process group; SIGKILL after `grace` if still alive.

    Returns True if the child is dead by the time we return, False if SIGKILL
    failed to reap it within the grace period (very rare — usually a kernel-
    level uninterruptible sleep). The caller should treat False as a failure
    to clean up: don't immediately respawn, since two children would now race
    on the same heartbeat file and audio device.
    """
    if proc.poll() is not None:
        return True
    _terminate_group(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=grace)
        return True
    except subprocess.TimeoutExpired:
        pass
    logger.warning("Child still alive after %.1fs; sending SIGKILL", grace)
    _terminate_group(proc, signal.SIGKILL)
    try:
        proc.wait(timeout=grace)
        return True
    except subprocess.TimeoutExpired:
        logger.error("Child did not die after SIGKILL")
        return False
    except OSError:
        return True  # already reaped


class Supervisor:
    def __init__(self, cfg: Optional[SupervisorConfig] = None) -> None:
        self.cfg = cfg or SupervisorConfig()
        # Event-based shutdown wakes the polling loop immediately on SIGTERM
        # instead of waiting up to ~1s for the next sleep tick.
        self._shutdown_event = threading.Event()
        self._proc: Optional[subprocess.Popen] = None

    @property
    def _shutdown(self) -> bool:
        return self._shutdown_event.is_set()

    def request_shutdown(self) -> None:
        """Request the supervisor to exit cleanly. Safe from any context including signal handlers."""
        self._shutdown_event.set()

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
        poll_interval = min(1.0, self.cfg.heartbeat_interval / 2)

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

            # Event-based wait: returns immediately if shutdown is requested.
            self._shutdown_event.wait(timeout=poll_interval)

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
        # Single Event.wait — wakes the moment SIGTERM/SIGINT calls request_shutdown().
        self._shutdown_event.wait(timeout=seconds)

    def run(self) -> int:
        self._install_signal_handlers()
        backoff = self.cfg.backoff_initial
        consecutive_failures = 0
        permanent_failure_announced = False

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

            if reason in ("clean_exit", "shutdown") or self._shutdown:
                return 0

            if not kill_dead_or_zero(self._proc):
                # Defensive: kill_process_tree may have been called inside _watch
                # already, but if SIGKILL failed there, abort the respawn so we
                # don't end up with two children fighting over the heartbeat file.
                logger.critical(
                    "Child %s could not be reaped after SIGKILL; refusing to respawn. "
                    "Check `ps` for orphans and restart the supervisor manually.",
                    self._proc.pid,
                )
                return 2

            write_crash_report(
                self.cfg, reason, exit_code, signal_num,
                pid=self._proc.pid,
                ran_for=ran_for,
                heartbeat_age_at_exit=hb_age,
            )

            # Track health for permanent-failure detection.
            if ran_for >= self.cfg.healthy_runtime:
                if consecutive_failures > 0:
                    logger.info(
                        "Child ran healthy for %.1fs; resetting failure counter", ran_for
                    )
                consecutive_failures = 0
                permanent_failure_announced = False
                backoff = self.cfg.backoff_initial
            else:
                consecutive_failures += 1
                if (
                    consecutive_failures >= self.cfg.permanent_failure_threshold
                    and not permanent_failure_announced
                ):
                    logger.critical(
                        "Child has failed %d times in a row without becoming healthy "
                        "(last reason=%s exit=%s). Switching to permanent-failure "
                        "backoff (%.1fs between attempts) until things improve.",
                        consecutive_failures, reason, exit_code,
                        self.cfg.permanent_failure_backoff,
                    )
                    permanent_failure_announced = True

            sleep_for = (
                self.cfg.permanent_failure_backoff
                if consecutive_failures >= self.cfg.permanent_failure_threshold
                else backoff
            )
            logger.info("Restarting in %.1fs", sleep_for)
            self._interruptible_sleep(sleep_for)
            if consecutive_failures < self.cfg.permanent_failure_threshold:
                backoff = self._next_backoff(backoff)

        return 0


def kill_dead_or_zero(proc: Optional[subprocess.Popen]) -> bool:
    """True if the process is already terminated (whatever the exit code).

    Used to detect whether a child we *thought* we killed via kill_process_tree
    actually died. A False return means kill_process_tree timed out at SIGKILL
    and we have an orphan situation we can't safely respawn around.
    """
    if proc is None:
        return True
    return proc.poll() is not None


def main(argv: Optional[list[str]] = None) -> int:
    cfg = SupervisorConfig()
    _setup_logging(cfg.supervisor_log_path)
    return Supervisor(cfg).run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
