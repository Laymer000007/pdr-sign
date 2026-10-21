"""Incremental document search on a worker thread.

Results stream in page by page, starting at the page you're reading and wrapping
round; the list is kept in document order.
"""

from __future__ import annotations

import bisect
import threading
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QObject, Signal

from pdr_sign.services.document import Document
from pdr_sign.services.search import MAX_HITS, SearchHit, page_order, search_page
from pdr_sign.ui.worker import Runner


def _search(
    runner: Runner,
    on_page: Callable[[int, int, list[SearchHit]], None],
    doc: Document,
    query: str,
    start: int,
    token: int,
    cancelled: threading.Event,
) -> int:
    """Worker side: search page by page, posting each page's hits as they're found."""
    found = 0
    for page in page_order(doc.page_count, start):
        if cancelled.is_set() or found >= MAX_HITS:
            break
        try:
            hits = search_page(doc, page, query)
        except (ValueError, RuntimeError):  # document closed underneath us
            break
        if hits:
            found += len(hits)
            runner.post(on_page, token, page, hits)
    return token


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
        self._cancel: threading.Event | None = None
        self._runner = Runner(threads=1, parent=self)

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
        self._cancel = threading.Event()
        work = partial(
            _search,
            self._runner,
            self._on_page,
            self.doc,
            self.query,
            from_page,
            self._token,
            self._cancel,
        )
        self._runner.submit(work, self._on_finished)

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
            self._cancel = None
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

    def _on_finished(self, token: object) -> None:
        if token == self._token:
            self.running = False
            self._cancel = None
            self.finished.emit()
