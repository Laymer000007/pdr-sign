"""Background tile rendering: a worker renders, the UI thread caches.

Each consumer (a page view, a thumbnail list) registers what it currently *wants*.
Wants are replaced wholesale on every scroll or zoom change, so stale work is dropped
instead of piling up. Only one job runs at a time because MuPDF calls are serialised by
``MUPDF_LOCK`` anyway.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from functools import partial

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

from pdr_sign.services.document import Document, DocumentError, Rect
from pdr_sign.services.render_cache import RenderCache
from pdr_sign.ui.worker import Runner


@dataclass(frozen=True)
class RenderRequest:
    key: Hashable
    doc: Document
    page: int
    zoom: float
    dpr: float
    clip: Rect | None = None


def render(r: RenderRequest) -> QImage | None:
    """Worker side: pixels for one request (QImage is safe off the UI thread)."""
    try:
        tile = r.doc.render_tile(r.page, r.zoom, r.dpr, r.clip)
    except (DocumentError, RuntimeError, ValueError):
        return None  # e.g. the document was closed while this job was queued
    return QImage(
        tile.data, tile.width, tile.height, tile.stride, QImage.Format.Format_RGB888
    ).copy()  # copy: the QImage must own its pixels once ``tile`` is gone


class RenderScheduler(QObject):
    """Owns the pixmap cache and the render queue for the whole app."""

    tile_ready = Signal(object)  # key

    def __init__(self, cache: RenderCache[QPixmap] | None = None) -> None:
        super().__init__()
        self.cache: RenderCache[QPixmap] = cache or RenderCache()
        self._runner = Runner(threads=1, parent=self)
        self._wants: dict[str, list[RenderRequest]] = {}
        self._priority: dict[str, int] = {}
        self._in_flight: set[Hashable] = set()

    def pixmap(self, key: Hashable) -> QPixmap | None:
        return self.cache.get(key)

    def set_wanted(self, owner: str, requests: list[RenderRequest], priority: int = 0) -> None:
        """Replace everything ``owner`` wants, most important first. Lower runs first."""
        self._wants[owner] = [r for r in requests if r.key not in self.cache]
        self._priority[owner] = priority
        self._dispatch()

    def forget(self, owner: str) -> None:
        self._wants.pop(owner, None)
        self._priority.pop(owner, None)

    def drop_document(self, doc: Document) -> None:
        for owner, wants in self._wants.items():
            self._wants[owner] = [r for r in wants if r.doc is not doc]
        self.cache.discard_where(lambda k: isinstance(k, tuple) and k[:1] == (doc.id,))

    def wait_idle(self, msecs: int = 5000) -> bool:
        """Block until queued work finishes (tests only)."""
        return self._runner.wait_idle(msecs)

    def _next(self) -> RenderRequest | None:
        for owner in sorted(self._wants, key=lambda o: self._priority.get(o, 0)):
            wants = self._wants[owner]
            while wants:
                request = wants.pop(0)
                if request.key not in self.cache and request.key not in self._in_flight:
                    return request
        return None

    def _dispatch(self) -> None:
        while len(self._in_flight) < 1:
            request = self._next()
            if request is None:
                return
            self._in_flight.add(request.key)
            self._runner.submit(partial(render, request), partial(self._on_done, request.key))

    def _on_done(self, key: Hashable, image: object) -> None:
        self._in_flight.discard(key)
        if isinstance(image, QImage):
            pixmap = QPixmap.fromImage(image)
            # Pixmaps are stored 32 bits per pixel whatever the source format.
            self.cache.put(key, pixmap, pixmap.width() * pixmap.height() * 4)
            self.tile_ready.emit(key)
        self._dispatch()
