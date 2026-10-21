"""Background jobs that never touch Qt from the worker thread.

Emitting a Qt signal from a worker means taking Qt's signal-slot locks *and* the
Python GIL; the UI thread takes the same pair in the other order when it connects
signals or creates timers. Under load that can deadlock (seen in the test suite on a
real X11 display). So workers here only put results on a ``queue.SimpleQueue``; the UI
thread drains it on a short timer that runs only while jobs are outstanding.
"""

from __future__ import annotations

import queue
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer

POLL_MS = 8


class _Job(QRunnable):
    def __init__(
        self, runner: Runner, work: Callable[[], Any], done: Callable[[Any], None]
    ) -> None:
        super().__init__()
        self.runner, self.work, self.done = runner, work, done

    def run(self) -> None:
        result: Any
        try:
            result = self.work()
        except Exception as exc:
            result = exc
        self.runner._queue.put((self.done, (result,), True))


class Runner(QObject):
    """A one-or-more-thread pool whose callbacks always run on the UI thread."""

    def __init__(self, threads: int = 1, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(threads)
        self._queue: queue.SimpleQueue[tuple[Callable[..., None], tuple[Any, ...], bool]] = (
            queue.SimpleQueue()
        )
        self._pending = 0
        self._timer = QTimer(self, interval=POLL_MS)
        self._timer.timeout.connect(self.drain)

    @property
    def busy(self) -> bool:
        return self._pending > 0

    def submit(self, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        """Run ``work()`` on the pool; ``done(result_or_exception)`` runs on the UI thread."""
        self._pending += 1
        if not self._timer.isActive():
            self._timer.start()
        self._pool.start(_Job(self, work, done))

    def post(self, callback: Callable[..., None], *args: Any) -> None:
        """From inside ``work``: deliver an intermediate result to the UI thread."""
        self._queue.put((callback, args, False))

    def drain(self) -> None:
        while True:
            try:
                callback, args, final = self._queue.get_nowait()
            except queue.Empty:
                break
            if final:
                self._pending -= 1
            callback(*args)
        if self._pending <= 0:
            self._pending = 0
            self._timer.stop()

    def wait_idle(self, msecs: int = 5000) -> bool:
        """Tests: wait for running jobs, then deliver their results."""
        done = bool(self._pool.waitForDone(msecs))
        self.drain()
        return done
