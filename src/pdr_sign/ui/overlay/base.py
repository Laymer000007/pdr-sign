"""Shared behaviour for Fill & Sign items on the canvas.

An overlay graphic is a child of its PageItem, so its coordinates are page points.
Its position is the item's top-left corner and its local rect starts at (0, 0).
Moving and resizing happen live; one model update (one undo step) is pushed when
the mouse is released.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.page_item import PageItem
from pdr_sign.ui.theme import ACCENT

if TYPE_CHECKING:
    from pdr_sign.ui.fill_model import FillModel

HANDLE_PX = 8  # handle size on screen, whatever the zoom
MIN_SIZE = 6.0  # points


class OverlayGraphic(QGraphicsObject):
    keep_aspect = False
    accent = QColor(ACCENT)  # set from theme tokens by Canvas.set_tokens()

    def __init__(self, item: OverlayItem, model: FillModel, parent: QGraphicsItem) -> None:
        super().__init__(parent)
        self.item = item
        self.model = model
        self._size = QPointF(item.rect[2] - item.rect[0], item.rect[3] - item.rect[1])
        self._resizing: str | None = None  # corner name while dragging a handle
        self._press_rect: QRectF | None = None
        self._moved = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setZValue(10)
        self.setPos(item.rect[0], item.rect[1])

    # --- geometry --------------------------------------------------------------

    def content_rect(self) -> QRectF:
        return QRectF(0, 0, self._size.x(), self._size.y())

    def scene_rect_in_page(self) -> tuple[float, float, float, float]:
        p = self.pos()
        return (p.x(), p.y(), p.x() + self._size.x(), p.y() + self._size.y())

    def _handle_size(self) -> float:
        scale = self.deviceTransform_scale()
        return HANDLE_PX / scale

    def deviceTransform_scale(self) -> float:
        views = self.scene().views() if self.scene() else []
        return views[0].transform().m11() if views else 1.0

    def boundingRect(self) -> QRectF:
        h = self._handle_size()
        return self.content_rect().adjusted(-h, -h, h, h)

    def set_size(self, width: float, height: float) -> None:
        self.prepareGeometryChange()
        self._size = QPointF(max(width, MIN_SIZE), max(height, MIN_SIZE))
        self.update()

    def apply(self, item: OverlayItem) -> None:
        """Show ``item`` (a model change, e.g. undo)."""
        self.item = item
        self.setPos(item.rect[0], item.rect[1])
        self.set_size(item.rect[2] - item.rect[0], item.rect[3] - item.rect[1])

    def commit(self) -> None:
        """Push the current geometry to the model as one undoable step."""
        new = self.item.moved_to(self.scene_rect_in_page())
        if new != self.item:
            self.model.update_item(new)

    # --- painting ------------------------------------------------------------------

    def paint_content(self, painter: QPainter) -> None:
        raise NotImplementedError

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint_content(painter)
        if self.isSelected():
            pen = QPen(self.accent, 0)  # cosmetic: 1 px at any zoom
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.content_rect())
            painter.setPen(QPen(self.accent, 0))
            painter.setBrush(QColor("white"))
            for rect in self._handles().values():
                painter.drawRect(rect)

    def _handles(self) -> dict[str, QRectF]:
        h = self._handle_size()
        r = self.content_rect()
        corners = {
            "tl": r.topLeft(),
            "tr": r.topRight(),
            "bl": r.bottomLeft(),
            "br": r.bottomRight(),
        }
        return {k: QRectF(p.x() - h / 2, p.y() - h / 2, h, h) for k, p in corners.items()}

    def _handle_at(self, pos: QPointF) -> str | None:
        if not self.isSelected():
            return None
        return next((k for k, r in self._handles().items() if r.contains(pos)), None)

    # --- interaction -----------------------------------------------------------------

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        handle = self._handle_at(event.pos())
        if handle in ("tl", "br"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in ("tr", "bl"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._resizing = self._handle_at(event.pos())
        self._press_rect = QRectF(self.pos(), self.content_rect().size())
        self._moved = False
        super().mousePressEvent(event)
        if self._resizing:
            event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._moved = True
        if self._resizing and self._press_rect is not None:
            self._resize_to(self.mapToParent(event.pos()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._moved:
            self.commit()
        self._resizing = None
        self._moved = False

    def _resize_to(self, point: QPointF) -> None:
        start = self._press_rect
        assert start is not None and self._resizing is not None
        left, top, right, bottom = start.left(), start.top(), start.right(), start.bottom()
        if "l" in self._resizing:
            left = min(point.x(), right - MIN_SIZE)
        if "r" in self._resizing:
            right = max(point.x(), left + MIN_SIZE)
        if "t" in self._resizing:
            top = min(point.y(), bottom - MIN_SIZE)
        if "b" in self._resizing:
            bottom = max(point.y(), top + MIN_SIZE)
        width, height = right - left, bottom - top
        if self.keep_aspect and start.height() > 0:
            ratio = start.width() / start.height()
            if width / max(height, 1e-6) > ratio:
                width = height * ratio
            else:
                height = width / ratio
            if "l" in self._resizing:
                left = right - width
            if "t" in self._resizing:
                top = bottom - height
        self.setPos(left, top)
        self.set_size(width, height)
        self.on_resized()

    def on_resized(self) -> None:
        """Hook for subclasses (text scales its font, marks redraw)."""

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        parent = self.parentItem()
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and isinstance(
            parent, PageItem
        ):
            page = parent.page_rect()
            p = QPointF(value)
            p.setX(max(0.0, min(p.x(), page.width() - self._size.x())))
            p.setY(max(0.0, min(p.y(), page.height() - self._size.y())))
            return p
        return super().itemChange(change, value)
