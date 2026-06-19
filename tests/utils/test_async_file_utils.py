"""Tests for the single background-writer save queue."""

import threading

from jf_sebastian.utils.async_file_utils import save_async, _BackgroundWriter


def test_save_runs_on_worker():
    done = threading.Event()
    save_async(done.set)                         # queued onto the shared writer
    assert done.wait(timeout=2)


def test_worker_survives_a_failing_save():
    save_async(lambda: (_ for _ in ()).throw(RuntimeError("boom")))  # swallowed
    done = threading.Event()
    save_async(done.set)                         # worker still alive, runs this
    assert done.wait(timeout=2)


def test_overflow_drops_without_blocking_or_raising():
    w = _BackgroundWriter(maxsize=2)
    started, release = threading.Event(), threading.Event()
    calls = []

    def blocking():
        started.set()
        release.wait(timeout=2)
        calls.append("blocked")

    def record(n):
        calls.append(n)

    w.submit(blocking, (), {})                   # worker picks this up and parks
    assert started.wait(timeout=2)               # queue now empty, worker busy

    for n in range(2):                           # fill the queue (maxsize=2)
        w.submit(record, (n,), {})
    for n in range(2, 10):                       # overflow: dropped, must not raise
        w.submit(record, (n,), {})

    release.set()
    w._queue.join()                              # wait until all queued items ran

    assert "blocked" in calls
    assert {0, 1}.issubset(set(calls))           # the two that fit ran
    assert not any(n in calls for n in range(2, 10))  # the rest were dropped
    assert w._dropped == 8
