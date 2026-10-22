"""Company stamps: an image item that also turns (free, or 90° steps) and fades.

The item's ``rect`` stays the *unrotated* box; the graphic turns about its centre.
That is exactly how saving bakes it (``sigimage.bake``), so the page matches the
screen. Corner handles resize in the stamp's own turned frame, keeping the opposite
corner where it is; the knob above the top edge turns it (Shift: 15° steps).
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pdr_sign.services.stamps import MIN_OPACITY, OverlayItem
from pdr_sign.ui.overlay.base import MIN_SIZE
from pdr_sign.ui.overlay.signature_item import SignatureGraphic
from pdr_sign.ui.page_item import PageItem

if TYPE_CHECKING:
    from pdr_sign.ui.fill_model import FillModel

KNOB_GAP_PX = 22  # how far above the top edge the rotate knob sits, on screen
SNAP_DEGREES = 15.0
OPPOSITE = {"tl": "br", "tr": "bl", "bl": "tr", "br": "tl"}


def normalise(degrees: float) -> float:
    value = degrees % 360
    return 0.0 if math.isclose(value, 360) or math.isclose(value, 0, abs_tol=1e-9) else value


def turn(angle: float) -> QTransform:
    return QTransform().rotate(angle)


class StampGraphic(SignatureGraphic):
    keep_aspect = True

    def __init__(self, item: OverlayItem, model: FillModel, parent: QGraphicsItem) -> None:
        super().__init__(item, model, parent, snap=None)
        self._rotating = False
        self._anchor: QPointF | None = None  # the fixed corner while resizing (parent coords)
        self._press_size = QPointF()
        self._sync_transform()

    # --- geometry ------------------------------------------------------------------

    def _centre(self) -> QPointF:
        return self.content_rect().center()

    def _sync_transform(self) -> None:
        self.setTransformOriginPoint(self._centre())
        self.setRotation(self.item.rotation)
        self.setOpacity(self.item.opacity)

    def set_size(self, width: float, height: float) -> None:
        super().set_size(width, height)
        self.setTransformOriginPoint(self._centre())

    def apply(self, item: OverlayItem) -> None:
        super().apply(item)
        self._sync_transform()

    def _knob(self) -> QRectF:
        h = self._handle_size()
        gap = KNOB_GAP_PX / self.deviceTransform_scale()
        centre = QPointF(self._centre().x(), -gap)
        return QRectF(centre.x() - h * 0.7, centre.y() - h * 0.7, h * 1.4, h * 1.4)

    def boundingRect(self) -> QRectF:
        return super().boundingRect().united(self._knob().adjusted(-2, -2, 2, 2))

    def _corner(self, name: str, size: QPointF | None = None) -> QPointF:
        w, h = (size.x(), size.y()) if size is not None else (self._size.x(), self._size.y())
        return QPointF(w if "r" in name else 0.0, h if "b" in name else 0.0)

    def _turned_extent(self, size: QPointF) -> QRectF:
        """Where the turned box sits relative to ``pos`` (for keeping it on the page)."""
        c = QPointF(size.x() / 2, size.y() / 2)
        t = turn(self.rotation())
        corners = [c + t.map(self._corner(n, size) - c) for n in ("tl", "tr", "bl", "br")]
        xs, ys = [p.x() for p in corners], [p.y() for p in corners]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    # --- painting ----------------------------------------------------------------------

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            knob = self._knob()
            painter.setPen(QPen(self.accent, 0))
            painter.drawLine(QPointF(self._centre().x(), 0), knob.center())
            painter.setBrush(QColor("white"))
            painter.drawEllipse(knob)

    # --- interaction ------------------------------------------------------------------

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        if self.isSelected() and self._knob().contains(event.pos()):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.isSelected() and self._knob().contains(event.pos()):
            self._rotating, self._moved = True, False
            event.accept()
            return
        super().mousePressEvent(event)
        if self._resizing:
            self._anchor = self.mapToParent(self._corner(OPPOSITE[self._resizing]))
            self._press_size = QPointF(self._size)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._rotating:
            self._moved = True
            centre = self.mapToParent(self._centre())
            pointer = self.mapToParent(event.pos())
            angle = (
                math.degrees(math.atan2(pointer.y() - centre.y(), pointer.x() - centre.x())) + 90
            )
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                angle = round(angle / SNAP_DEGREES) * SNAP_DEGREES
            self.setRotation(normalise(angle))
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._rotating:
            self._rotating = False
            if self._moved:
                self.commit()
            self._moved = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._anchor = None

    def _resize_to(self, point: QPointF) -> None:
        """Resize in the stamp's own (turned) frame; the opposite corner stays put."""
        handle, anchor = self._resizing, self._anchor
        if handle is None or anchor is None:
            return
        v = turn(-self.rotation()).map(point - anchor)
        w = v.x() if "r" in handle else -v.x()
        h = v.y() if "b" in handle else -v.y()
        w, h = max(w, MIN_SIZE), max(h, MIN_SIZE)
        start = self._press_size
        if start.y() > 0:  # keep the shape: follow whichever side moved further
            ratio = start.x() / start.y()
            if w / h > ratio:
                h = w / ratio
            else:
                w = h * ratio
        self.set_size(w, h)
        c = self._centre()
        fixed = self._corner(OPPOSITE[handle])
        self.setPos(anchor - c - turn(self.rotation()).map(fixed - c))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        parent = self.parentItem()
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and isinstance(
            parent, PageItem
        ):
            page = parent.page_rect()
            extent = self._turned_extent(self._size)
            p = QPointF(value)
            p.setX(max(-extent.left(), min(p.x(), page.width() - extent.right())))
            p.setY(max(-extent.top(), min(p.y(), page.height() - extent.bottom())))
            return p
        return QGraphicsItem.itemChange(self, change, value)

    # --- model ----------------------------------------------------------------------------

    def commit(self) -> None:
        new = replace(
            self.item, rect=self.scene_rect_in_page(), rotation=round(normalise(self.rotation()), 2)
        )
        if new != self.item:
            self.model.update_item(new)

    def rotate_by(self, degrees: float) -> None:
        """Panel ⟲/⟳ buttons: quarter turns from wherever it is now."""
        self.model.update_item(replace(self.item, rotation=normalise(self.item.rotation + degrees)))

    def set_stamp_opacity(self, opacity: float, merge: bool = True) -> None:
        value = round(max(MIN_OPACITY, min(1.0, opacity)), 2)
        if value != self.item.opacity:
            self.model.update_item(replace(self.item, opacity=value), merge=merge)
