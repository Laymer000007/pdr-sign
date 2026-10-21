"""Incremental document search on a worker thread.

Results stream in page by page, starting at the page you're reading and wrapping
round; the list is kept in document order.
"""

from __future__ import annotations

import bisect
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from pdr_sign.services.document import Document
from pdr_sign.services.search import MAX_HITS, SearchHit, page_order, search_page

_pool: QThreadPool | None = None


def search_pool() -> QThreadPool:
    global _pool
    if _pool is None:
        _pool = QThreadPool()
        _pool.setMaxThreadCount(1)
    return _pool


class _Bridge(QObject):
    page_done = Signal(int, int, object)  # token, page, list[SearchHit]
    finished = Signal(int)  # token


class _SearchJob(QRunnable):
    def __init__(self, doc: Document, query: str, start: int, token: int, bridge: _Bridge) -> None:
        super().__init__()
        self.doc, self.query, self.start, self.token = doc, query, start, token
        self.bridge = bridge
        self.cancelled = threading.Event()

    def run(self) -> None:
        found = 0
        for page in page_order(self.doc.page_count, self.start):
            if self.cancelled.is_set() or found >= MAX_HITS:
                break
            try:
                hits = search_page(self.doc, page, self.query)
            except (ValueError, RuntimeError):  # document closed underneath us
                return
            if hits:
                found += len(hits)
                self.bridge.page_done.emit(self.token, page, hits)
        self.bridge.finished.emit(self.token)


class SearchController(QObject):
    results_changed = Signal()
    current_changed = Signal(object)  # SearchHit | None
    finished = Signal()

    def __init__(self, doc: Document, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.query = ""
        self.hits: list[SearchHit] = []
        self.running = False
        self._pages: list[int] = []  # parallel to hits, for bisect
        self._current: SearchHit | None = None
        self._token = 0
        self._job: _SearchJob | None = None
        self._bridge = _Bridge(self)
        self._bridge.page_done.connect(self._on_page)
        self._bridge.finished.connect(self._on_finished)

    @property
    def current_index(self) -> int:
        return self.hits.index(self._current) if self._current in self.hits else -1

    @property
    def current(self) -> SearchHit | None:
        return self._current

    @property
    def capped(self) -> bool:
        return len(self.hits) >= MAX_HITS

    def start(self, query: str, from_page: int) -> None:
        self.cancel()
        self.query = query.strip()
        self.hits, self._pages, self._current = [], [], None
        self.results_changed.emit()
        self.current_changed.emit(None)
        if not self.query:
            self.finished.emit()
            return
        self._token += 1
        self.running = True
        self._job = _SearchJob(self.doc, self.query, from_page, self._token, self._bridge)
        search_pool().start(self._job)

    def cancel(self) -> None:
        if self._job is not None:
            self._job.cancelled.set()
            self._job = None
        self.running = False

    def clear(self) -> None:
        self.start("", 0)

    def step(self, delta: int) -> None:
        if not self.hits:
            return
        index = self.current_index
        index = 0 if index < 0 and delta > 0 else (index + delta) % len(self.hits)
        self.set_current(index)

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self.hits):
            self._current = self.hits[index]
            self.current_changed.emit(self._current)

    def _on_page(self, token: int, page: int, hits: list[SearchHit]) -> None:
        if token != self._token:
            return
        at = bisect.bisect_left(self._pages, page)
        self.hits[at:at] = hits
        self._pages[at:at] = [page] * len(hits)
        self.results_changed.emit()
        if self._current is None:  # the first page searched is the one being read
            self._current = hits[0]
            self.current_changed.emit(self._current)

    def _on_finished(self, token: int) -> None:
        if token == self._token:
            self.running = False
            self._job = None
            self.finished.emit()
