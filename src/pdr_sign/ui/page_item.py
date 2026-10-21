"""One page on the canvas, drawn from cached pixmap tiles.

Item coordinates are PDF points (visible orientation), origin at the page's top-left.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from pdr_sign.services.document import Document, LinkInfo, PageInfo, Rect

if TYPE_CHECKING:
    from pdr_sign.ui.render_scheduler import RenderScheduler

TILE_PX = 1024  # tile edge in device pixels

TileKey = tuple[int, int, float, float, int, int]


def zoom_key(zoom: float) -> float:
    return round(zoom, 4)


def tile_key(doc: Document, page: int, zoom: float, dpr: float, tx: int, ty: int) -> TileKey:
    return (doc.id, page, zoom_key(zoom), round(dpr, 2), tx, ty)


def tiles(
    width: float, height: float, zoom: float, dpr: float, area: QRectF | None = None
) -> Iterator[tuple[int, int, Rect]]:
    """Tiles ``(tx, ty, clip)`` covering a page, or only ``area`` of it (points)."""
    step = TILE_PX / (zoom * dpr)
    x0, y0, x1, y1 = 0.0, 0.0, width, height
    if area is not None:
        x0, y0 = max(0.0, area.left()), max(0.0, area.top())
        x1, y1 = min(width, area.right()), min(height, area.bottom())
        if x1 <= x0 or y1 <= y0:
            return
    for ty in range(int(y0 // step), math.ceil(y1 / step)):
        for tx in range(int(x0 // step), math.ceil(x1 / step)):
            clip = (tx * step, ty * step, min(width, (tx + 1) * step), min(height, (ty + 1) * step))
            if clip[2] > clip[0] and clip[3] > clip[1]:
                yield tx, ty, clip


def to_qrect(r: Rect) -> QRectF:
    return QRectF(r[0], r[1], r[2] - r[0], r[3] - r[1])


class PageItem(QGraphicsItem):
    SHADOW = QColor(0, 0, 0, 30)
    # Set from theme tokens by Canvas.set_tokens(); drawn translucently over the page.
    selection_color = QColor(79, 70, 229, 80)
    hit_color = QColor(252, 211, 77, 110)
    current_hit_color = QColor(245, 158, 11, 150)

    def __init__(self, doc: Document, info: PageInfo, scheduler: RenderScheduler) -> None:
        super().__init__()
        self.doc = doc
        self.info = info
        self.scheduler = scheduler
        self.render_zooms: tuple[float, ...] = ()  # fallback first, current last
        self.dpr = 1.0
        self._links: list[LinkInfo] | None = None
        self.search_rects: list[Rect] = []
        self.current_hit: Rect | None = None
        self.selection_rects: list[Rect] = []
        self._zoom = 1.0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)

    @property
    def index(self) -> int:
        return self.info.index

    def page_rect(self) -> QRectF:
        return QRectF(0, 0, self.info.width, self.info.height)

    def set_view_zoom(self, zoom: float) -> None:
        """The shadow is a fixed number of pixels, so the bounds depend on zoom."""
        self.prepareGeometryChange()
        self._zoom = zoom

    def boundingRect(self) -> QRectF:
        px = 3 / self._zoom
        return self.page_rect().adjusted(-px, -px, px, 2 * px)

    def links(self) -> list[LinkInfo]:
        if self._links is None:
            self._links = self.doc.links(self.index)
        return self._links

    def link_at(self, point: QPointF) -> LinkInfo | None:
        for link in self.links():
            x0, y0, x1, y1 = link.rect
            if x0 <= point.x() <= x1 and y0 <= point.y() <= y1:
                return link
        return None

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        page = self.page_rect()
        px = 1 / max(painter.worldTransform().m11(), 1e-6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillRect(page.translated(0, px), self.SHADOW)
        painter.fillRect(page.adjusted(-px / 2, 0, px / 2, 2 * px), QColor(0, 0, 0, 12))
        painter.fillRect(page, Qt.GlobalColor.white)

        exposed = option.exposedRect.intersected(page)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for zoom in self.render_zooms:
            for tx, ty, clip in tiles(page.width(), page.height(), zoom, self.dpr, exposed):
                key = tile_key(self.doc, self.index, zoom, self.dpr, tx, ty)
                pixmap = self.scheduler.pixmap(key)
                if pixmap is not None:
                    painter.drawPixmap(to_qrect(clip), pixmap, QRectF(pixmap.rect()))
        self._paint_highlights(painter)

    def _paint_highlights(self, painter: QPainter) -> None:
        pad = 1.0  # points of breathing room around glyph boxes
        for rect in self.search_rects:
            painter.fillRect(to_qrect(rect).adjusted(-pad, -pad, pad, pad), self.hit_color)
        if self.current_hit is not None:
            box = to_qrect(self.current_hit).adjusted(-pad, -pad, pad, pad)
            painter.fillRect(box, self.current_hit_color)
        for rect in self.selection_rects:
            painter.fillRect(to_qrect(rect).adjusted(0, -pad / 2, 0, pad / 2), self.selection_color)
