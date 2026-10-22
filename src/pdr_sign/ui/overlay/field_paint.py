"""What field editors share: theme colours, font sizing, and the "Sign here" box."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsSceneMouseEvent,
    QGraphicsWidget,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pdr_sign.services.forms import FieldInfo

if TYPE_CHECKING:
    from pdr_sign.ui.page_item import PageItem

FIELD_FONT = "Helvetica"  # what the saved appearance uses


class FieldColors:
    """Set from theme tokens (``Canvas.set_tokens``)."""

    fill = QColor("#E8EEFB")
    border = QColor("#9AA8D6")
    accent = QColor("#4F46E5")


def auto_font_px(field: FieldInfo) -> float:
    """The field's font size, or a size that fits its box when the PDF says "auto"."""
    if field.font_size > 0:
        return field.font_size
    height = field.rect[3] - field.rect[1]
    if field.multiline or field.kind == "list":
        return 10.0
    return max(6.0, min(12.0, height * 0.62))


def field_style(px: float) -> str:
    return (
        f"font-family: {FIELD_FONT}; font-size: {max(1, round(px))}px; color: black;"
        f"background: {FieldColors.fill.name()}; border: none; padding: 0 1px;"
        f"selection-background-color: {FieldColors.accent.name()}; selection-color: white;"
    )


class SignHere(QGraphicsWidget):
    """An empty signature field: a dashed "Sign here" box. Clicking it signs into it."""

    def __init__(
        self, field: FieldInfo, parent: PageItem, on_click: Callable[[FieldInfo], None]
    ) -> None:
        super().__init__(parent)
        self.field = field
        self.on_click = on_click
        x0, y0, x1, y1 = field.rect
        self.setGeometry(QRectF(x0, y0, x1 - x0, y1 - y0))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Sign here ({field.display_name})")
        self.setAcceptHoverEvents(True)
        self.setZValue(4)  # below placed items, so a placed signature stays grabbable

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tint = QColor(FieldColors.accent)
        tint.setAlpha(18)
        pen = QPen(FieldColors.accent, 0, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(tint)
        painter.drawRoundedRect(self.rect(), 3, 3)
        font = painter.font()
        font.setPixelSize(max(6, round(min(11.0, self.rect().height() * 0.3))))
        painter.setFont(font)
        painter.setPen(FieldColors.accent)
        painter.drawText(
            self.rect().adjusted(4, 2, -4, -2),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
            "Sign here",
        )

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.rect().contains(event.pos()):
            self.on_click(self.field)
        event.accept()
