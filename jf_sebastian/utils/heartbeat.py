"""
Heartbeat: a tiny background thread that touches a file every N seconds
so an external supervisor can detect when the main process has hung
(e.g., a deadlocked PROCESSING state, a frozen RVC backend).

Use:
    hb = Heartbeat(Path("/tmp/jfs.heartbeat"), interval=10.0)
    hb.start()
    ...
    hb.stop()  # call before subsystems that can hang during shutdown
"""

import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Heartbeat:
    """Periodically updates the mtime of a file to signal liveness."""

    def __init__(self, path: Path, interval: float = 10.0):
        self.path = Path(path)
        self.interval = max(0.1, float(interval))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def touch(self) -> None:
        """Update the heartbeat file's mtime to now (creating it if needed).

        Catches a broad Exception family so that interpreter-shutdown garbage
        (e.g., NoneType module references) can never escape the thread.
        """
        try:
            self.path.touch()
        except Exception as e:  # noqa: BLE001 — see docstring
            logger.warning("Heartbeat touch failed for %s: %s", self.path, e)

    def start(self) -> None:
        """Start the background heartbeat thread (idempotent)."""
        if self._thread and self._thread.is_alive():
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Could not create heartbeat parent dir %s: %s", self.path.parent, e)
        self._stop.clear()
        self.touch()
        self._thread = threading.Thread(target=self._run, daemon=True, name="heartbeat")
        self._thread.start()
        logger.info("Heartbeat started: %s every %.1fs", self.path, self.interval)

    def stop(self, join_timeout: float = 1.0) -> None:
        """Signal the thread to stop and wait briefly for it to exit."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=join_timeout)
            self._thread = None

    def _run(self) -> None:
        # Use Event.wait() rather than time.sleep() so stop() returns promptly.
        while not self._stop.wait(self.interval):
            try:
                self.touch()
            except Exception:  # noqa: BLE001 — never let the thread die silently
                logger.exception("Heartbeat thread caught unexpected exception; continuing")
