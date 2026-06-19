"""
Async file utilities for non-blocking debug file saves.

Debug saves (SAVE_DEBUG_AUDIO) are dispatched to a single long-lived background
writer thread via a bounded queue, rather than spawning a thread per file. This
keeps the producer (the audio pipeline) cost to a cheap enqueue, serializes disk
writes so they don't thrash under load, and drops saves (debug data is
disposable) instead of piling up without bound when the writer can't keep up.
"""

import logging
import queue
import threading
from typing import Callable

logger = logging.getLogger(__name__)

# Bounded so a slow disk / busy box can't grow the backlog (and the audio arrays
# it references) without limit; overflow drops the save instead of blocking. Kept
# small since each queued item can pin a full utterance's audio until it's written
# (memory matters on constrained hosts like the Jetson); the writer drains far
# faster than utterances arrive, so this depth is a safety ceiling, not occupancy.
_QUEUE_MAXSIZE = 16


class _BackgroundWriter:
    """One daemon thread draining a bounded queue of save callables. Producers
    enqueue and return immediately; overflow is dropped, not blocked on."""

    def __init__(self, maxsize: int = _QUEUE_MAXSIZE):
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._dropped = 0
        # An idle daemon parked on queue.get() is free, so just start it now.
        threading.Thread(target=self._run, name="debug-audio-writer", daemon=True).start()

    def submit(self, func: Callable, args: tuple, kwargs: dict) -> None:
        try:
            self._queue.put_nowait((func, args, kwargs))
        except queue.Full:
            self._dropped += 1
            # Log sparsely so a sustained overload doesn't spam the log.
            if self._dropped == 1 or self._dropped % 50 == 0:
                logger.warning("Debug-save queue full; dropped %d save(s)", self._dropped)

    def _run(self) -> None:
        while True:
            func, args, kwargs = self._queue.get()
            try:
                func(*args, **kwargs)
            except Exception as e:
                logger.warning("Async save failed: %s", e)
            finally:
                self._queue.task_done()


_writer = _BackgroundWriter()


def save_async(save_func: Callable, *args, **kwargs) -> None:
    """
    Queue a save to run on the shared background writer thread (non-blocking).

    Enqueues and returns immediately. If the writer can't keep up (slow disk,
    busy machine), the save is dropped rather than blocking the caller or growing
    the backlog without bound, since debug audio is disposable.

    Args:
        save_func: Function to call for saving (e.g., save_audio_to_wav)
        *args: Positional arguments to pass to save_func
        **kwargs: Keyword arguments to pass to save_func

    Example:
        save_async(save_audio_to_wav, audio_data, "debug.wav")
    """
    _writer.submit(save_func, args, kwargs)
