"""What field editors share: theme colours, text layout, and the "Sign here" box."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QGraphicsSceneMouseEvent,
    QGraphicsWidget,
    QLineEdit,
    QStyleOptionGraphicsItem,
    QTextEdit,
    QWidget,
)

from pdr_sign.services.forms import FieldInfo
from pdr_sign.services.text_layout import field_text_layout
from pdr_sign.ui.theme import ACCENT, LIGHT

if TYPE_CHECKING:
    from pdr_sign.ui.page_item import PageItem

FIELD_FONT = "Helvetica"  # what the saved appearance uses


class FieldColors:
    """Set from theme tokens (``Canvas.set_tokens``)."""

    fill = QColor(LIGHT.field_fill)
    border = QColor(LIGHT.field_border)
    accent = QColor(ACCENT)


def auto_font_px(field: FieldInfo) -> float:
    """The field's font size, or a size that fits its box when the PDF says "auto"."""
    if field.font_size > 0:
        return field.font_size
    height = field.rect[3] - field.rect[1]
    if field.multiline or field.kind == "list":
        return 10.0
    return max(6.0, min(12.0, height * 0.62))


def field_style(px: float, padding: str = "0 1px") -> str:
    return (
        f"font-family: {FIELD_FONT}; font-size: {max(1, round(px))}px; color: black;"
        f"background: {FieldColors.fill.name()}; border: none; padding: {padding};"
        f"selection-background-color: {FieldColors.accent.name()}; selection-color: white;"
    )


def _font(size: float) -> QFont:
    font = QFont(FIELD_FONT)
    font.setPixelSize(max(1, round(size)))
    font.setKerning(False)  # as MuPDF draws the saved value
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


# QLineEdit insets its text by 2 px horizontally and 1 px vertically on its own.
_LINE_EDIT_INSET_X, _LINE_EDIT_INSET_Y = 2, 1


def lay_out_line(line: QLineEdit, field: FieldInfo) -> None:
    """Put a single-line field's text where MuPDF draws the saved value: same size
    (auto fields shrink to fit, like the saved appearance), same baseline."""
    layout = field_text_layout(field, line.text())
    font = _font(layout.font_size)
    line.setStyleSheet(field_style(layout.font_size, padding="0"))
    horizontal = Qt.AlignmentFlag.AlignHCenter if field.comb else Qt.AlignmentFlag.AlignLeft
    line.setAlignment(horizontal | Qt.AlignmentFlag.AlignTop)
    top = layout.baseline - _LINE_EDIT_INSET_Y - QFontMetricsF(font).ascent()
    left = 0 if field.comb else round(layout.left - _LINE_EDIT_INSET_X)
    line.setTextMargins(left, round(top), 0, 0)


def lay_out_area(area: QTextEdit, field: FieldInfo) -> None:
    """The same for a multi-line field: MuPDF's size, line spacing and first baseline."""
    layout = field_text_layout(field, area.toPlainText())
    area.setStyleSheet(field_style(layout.font_size, padding="0"))
    area.setFont(_font(layout.font_size))
    document = area.document()
    document.setDocumentMargin(0)
    block = QTextBlockFormat()
    block.setLineHeight(layout.line_height, QTextBlockFormat.LineHeightTypes.FixedHeight.value)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeBlockFormat(block)
    document.size()  # lay out, then measure where Qt put the first baseline
    line = document.firstBlock().layout().lineAt(0)
    offset = line.y() + line.ascent() if line.isValid() else QFontMetricsF(area.font()).ascent()
    margins = getattr(area, "set_text_margins", None)
    if callable(margins):
        margins(round(layout.left), round(layout.baseline - offset))


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
