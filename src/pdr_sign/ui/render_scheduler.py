"""Background tile rendering: a QThreadPool worker renders, the UI thread caches.

Each consumer (a page view, a thumbnail list) registers what it currently *wants*.
Wants are replaced wholesale on every scroll or zoom change, so stale work is dropped
instead of piling up. Only one job runs at a time because MuPDF calls are serialised by
``MUPDF_LOCK`` anyway.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from pdr_sign.services.document import Document, DocumentError, Rect
from pdr_sign.services.render_cache import RenderCache


@dataclass(frozen=True)
class RenderRequest:
    key: Hashable
    doc: Document
    page: int
    zoom: float
    dpr: float
    clip: Rect | None = None


class _Bridge(QObject):
    done = Signal(object, object)  # key, QImage | None


class _Job(QRunnable):
    def __init__(self, request: RenderRequest, bridge: _Bridge) -> None:
        super().__init__()
        self.request = request
        self.bridge = bridge

    def run(self) -> None:
        r = self.request
        image: QImage | None
        try:
            tile = r.doc.render_tile(r.page, r.zoom, r.dpr, r.clip)
            image = QImage(
                tile.data, tile.width, tile.height, tile.stride, QImage.Format.Format_RGB888
            ).copy()  # copy: the QImage must own its pixels once ``tile`` is gone
        except (DocumentError, RuntimeError, ValueError):
            image = None  # e.g. the document was closed while this job was queued
        self.bridge.done.emit(r.key, image)


class RenderScheduler(QObject):
    """Owns the pixmap cache and the render queue for the whole app."""

    tile_ready = Signal(object)  # key

    def __init__(self, cache: RenderCache[QPixmap] | None = None) -> None:
        super().__init__()
        self.cache: RenderCache[QPixmap] = cache or RenderCache()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._on_done)
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
        return bool(self._pool.waitForDone(msecs))

    def _next(self) -> RenderRequest | None:
        for owner in sorted(self._wants, key=lambda o: self._priority.get(o, 0)):
            wants = self._wants[owner]
            while wants:
                request = wants.pop(0)
                if request.key not in self.cache and request.key not in self._in_flight:
                    return request
        return None

    def _dispatch(self) -> None:
        while len(self._in_flight) < self._pool.maxThreadCount():
            request = self._next()
            if request is None:
                return
            self._in_flight.add(request.key)
            self._pool.start(_Job(request, self._bridge))

    def _on_done(self, key: Hashable, image: QImage | None) -> None:
        self._in_flight.discard(key)
        if image is not None:
            pixmap = QPixmap.fromImage(image)
            # Pixmaps are stored 32 bits per pixel whatever the source format.
            self.cache.put(key, pixmap, pixmap.width() * pixmap.height() * 4)
            self.tile_ready.emit(key)
        self._dispatch()
