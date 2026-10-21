"""Line items: a straight stroke between two end points.

Lines are horizontal by default; hold Shift (while drawing or dragging an end point)
for any angle. The item's position is the top-left of the line's bounding box and its
end points are stored relative to that, so the base class's move and clamp-to-page
logic works unchanged.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pdr_sign.services.stamps import LINE_LENGTH, OverlayItem, line_width
from pdr_sign.ui.overlay.base import OverlayGraphic
from pdr_sign.ui.page_item import PageItem

if TYPE_CHECKING:
    from pdr_sign.ui.fill_model import FillModel

MIN_LENGTH = 3.0  # points; a shorter drag counts as a click
HIT_PX = 8  # how close (screen px) a click must be to select a thin line


class LineGraphic(OverlayGraphic):
    def __init__(
        self, item: OverlayItem, model: FillModel, parent: QGraphicsItem, pending: bool = False
    ) -> None:
        self._a = QPointF()
        self._b = QPointF()
        super().__init__(item, model, parent)
        self.pending = pending
        self._dragging_end: str | None = None
        x1, y1, x2, y2 = item.rect
        self.set_endpoints(QPointF(x1, y1), QPointF(x2, y2))

    # --- geometry --------------------------------------------------------------

    def endpoints(self) -> tuple[QPointF, QPointF]:
        """Both end points in page coordinates."""
        return self.pos() + self._a, self.pos() + self._b

    def set_endpoints(self, p1: QPointF, p2: QPointF) -> None:
        self.prepareGeometryChange()
        origin = QPointF(min(p1.x(), p2.x()), min(p1.y(), p2.y()))
        self._a, self._b = p1 - origin, p2 - origin
        # Bypass set_size's minimum: a horizontal line really is 0 pt tall.
        self._size = QPointF(abs(p2.x() - p1.x()), abs(p2.y() - p1.y()))
        self.setPos(origin)
        self.update()

    def length(self) -> float:
        return QLineF(self._a, self._b).length()

    def scene_rect_in_page(self) -> tuple[float, float, float, float]:
        p1, p2 = self.endpoints()
        return (p1.x(), p1.y(), p2.x(), p2.y())

    def _pen_width(self) -> float:
        return line_width(self.item.font_size)

    def boundingRect(self) -> QRectF:
        pad = max(self._handle_size(), self._pen_width()) + 1
        return QRectF(self._a, self._b).normalized().adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath(self._a)
        path.lineTo(self._b)
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._pen_width(), HIT_PX / self.deviceTransform_scale()))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        return stroker.createStroke(path)

    def apply(self, item: OverlayItem) -> None:
        self.item = item
        x1, y1, x2, y2 = item.rect
        self.set_endpoints(QPointF(x1, y1), QPointF(x2, y2))

    def commit(self) -> None:
        new = self.item.moved_to(self.scene_rect_in_page())
        if new != self.item and not self.pending:
            self.model.update_item(new)

    def restyle(self, font_size: float, color: str) -> None:
        new = replace(self.item, font_size=font_size, color=color)
        if new != self.item:
            self.prepareGeometryChange()
            self.item = new
            self.update()
            if not self.pending:
                self.model.update_item(new)

    # --- painting ------------------------------------------------------------------

    def paint_content(self, painter: QPainter) -> None:
        pen = QPen(QColor(self.item.color), self._pen_width())
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(self._a, self._b)

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint_content(painter)
        if self.isSelected():
            painter.setPen(QPen(self.accent, 0))
            painter.setBrush(QColor("white"))
            for rect in self._handles().values():
                painter.drawEllipse(rect)

    def _handles(self) -> dict[str, QRectF]:
        h = self._handle_size()
        return {
            name: QRectF(p.x() - h / 2, p.y() - h / 2, h, h)
            for name, p in (("a", self._a), ("b", self._b))
        }

    # --- interaction -----------------------------------------------------------------

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        on_handle = self._handle_at(event.pos()) is not None
        self.setCursor(Qt.CursorShape.CrossCursor if on_handle else Qt.CursorShape.SizeAllCursor)
        QGraphicsItem.hoverMoveEvent(self, event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._dragging_end = self._handle_at(event.pos())
        self._moved = False
        if self._dragging_end:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._dragging_end is None:
            super().mouseMoveEvent(event)
            return
        self._moved = True
        p1, p2 = self.endpoints()
        fixed = p2 if self._dragging_end == "a" else p1
        free = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        moving = self.constrain(fixed, self.mapToParent(event.pos()), free)
        if self._dragging_end == "a":
            self.set_endpoints(moving, fixed)
        else:
            self.set_endpoints(fixed, moving)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._dragging_end is not None:
            if self._moved:
                self.commit()
            self._dragging_end = None
            self._moved = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def constrain(self, fixed: QPointF, point: QPointF, free: bool) -> QPointF:
        """Keep ``point`` on the page, and level with ``fixed`` unless ``free``."""
        parent = self.parentItem()
        page = parent.page_rect() if isinstance(parent, PageItem) else QRectF()
        x = min(max(point.x(), page.left()), page.right())
        y = min(max(point.y(), page.top()), page.bottom()) if free else fixed.y()
        return QPointF(x, y)


def default_end(start: QPointF, page_width: float) -> QPointF:
    """Where a clicked (not dragged) line ends: LINE_LENGTH to the right, or to the left
    when there's no room on the right."""
    if start.x() + LINE_LENGTH <= page_width:
        return QPointF(start.x() + LINE_LENGTH, start.y())
    return QPointF(max(0.0, start.x() - LINE_LENGTH), start.y())


def angle_degrees(item: OverlayItem) -> float:
    x1, y1, x2, y2 = item.rect
    return math.degrees(math.atan2(y2 - y1, x2 - x1))
