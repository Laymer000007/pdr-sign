"""Signature and initials items: a transparent image that keeps its aspect ratio."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsItem

from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.overlay.base import OverlayGraphic

if TYPE_CHECKING:
    from collections.abc import Callable

    from pdr_sign.ui.fill_model import FillModel

Rect = tuple[float, float, float, float]


class SignatureGraphic(OverlayGraphic):
    keep_aspect = True

    def __init__(
        self,
        item: OverlayItem,
        model: FillModel,
        parent: QGraphicsItem,
        snap: Callable[[int, Rect], Rect | None] | None = None,
    ) -> None:
        super().__init__(item, model, parent)
        self.snap = snap  # dropping near a signature field fits the image into it
        self.pixmap = QPixmap()
        if item.image:
            self.pixmap.loadFromData(item.image, "PNG")

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.pixmap.isNull():
            painter.drawPixmap(self.content_rect(), self.pixmap, QRectF(self.pixmap.rect()))

    def commit(self) -> None:
        rect = self.scene_rect_in_page()
        # Snap after a move, not a resize: shrinking it inside a field is deliberate.
        moving = self._resizing is None
        snapped = self.snap(self.item.page, rect) if self.snap and moving else None
        if snapped is not None and snapped != rect:
            self.setPos(snapped[0], snapped[1])
            self.set_size(snapped[2] - snapped[0], snapped[3] - snapped[1])
            rect = snapped
        new = self.item.moved_to(rect)
        if new != self.item:
            self.model.update_item(new)
