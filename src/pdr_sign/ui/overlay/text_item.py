"""Text and date items: editable in place, growing as you type."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFocusEvent, QFont, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
)

from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.overlay.base import OverlayGraphic

if TYPE_CHECKING:
    from pdr_sign.ui.fill_model import FillModel

# Saved text uses Helvetica, so edit in the closest local match.
TEXT_FAMILY = "Helvetica"
PAD = 2.0  # points between the box and the text


def text_font(size: float) -> QFont:
    font = QFont(TEXT_FAMILY)
    font.setPixelSize(max(1, round(size)))  # 1 scene unit = 1 pt
    font.setStyleHint(QFont.StyleHint.SansSerif)
    return font


class _Editor(QGraphicsTextItem):
    finished = Signal()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        if event.reason() != Qt.FocusReason.PopupFocusReason:
            self.finished.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            return
        super().keyPressEvent(event)


class TextGraphic(OverlayGraphic):
    """A text, date or initials item. ``pending`` items join the model once typed into."""

    def __init__(
        self, item: OverlayItem, model: FillModel, parent: QGraphicsItem, pending: bool = False
    ) -> None:
        super().__init__(item, model, parent)
        self.pending = pending
        self.editor = _Editor(self)
        self.editor.setPos(PAD, PAD / 2)
        self.editor.document().setDocumentMargin(0)
        self.editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.editor.document().contentsChanged.connect(self._fit)
        self.editor.finished.connect(self._finish_editing)
        self._show(item)

    def _show(self, item: OverlayItem) -> None:
        self.editor.setFont(text_font(item.font_size))
        self.editor.setDefaultTextColor(QColor(item.color))
        if self.editor.toPlainText() != item.text:
            self.editor.setPlainText(item.text)
        self._fit()

    def apply(self, item: OverlayItem) -> None:
        self.item = item
        self.setPos(item.rect[0], item.rect[1])
        self._show(item)

    def _fit(self) -> None:
        size = self.editor.document().size()
        min_width = self.item.font_size * 2
        self.set_size(max(size.width(), min_width) + 2 * PAD, size.height() + PAD)

    @property
    def editing(self) -> bool:
        return bool(
            self.editor.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction
        )

    def start_editing(self) -> None:
        self.editor.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.editor.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def _finish_editing(self) -> None:
        self.editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        text = self.editor.toPlainText().rstrip()
        new = replace(self.item, text=text, rect=self.scene_rect_in_page())
        if self.pending:
            if text:
                self.pending = False
                self.item = new
                self.model.add_item(new)
            else:
                self.scene_remove()  # an empty new box simply disappears
            return
        if not text:
            self.model.remove_item(self.item.id)
        elif new != self.item:
            self.model.update_item(new)

    def scene_remove(self) -> None:
        scene = self.scene()
        if scene is not None:
            scene.removeItem(self)

    def set_style(self, font_size: float | None = None, color: str | None = None) -> None:
        """Change size/colour from the panel; one undo step each."""
        new = replace(
            self.item,
            font_size=font_size if font_size is not None else self.item.font_size,
            color=color if color is not None else self.item.color,
        )
        if new == self.item:
            return
        self.item = new
        self._show(new)
        new = replace(new, rect=self.scene_rect_in_page())
        self.item = new
        if not self.pending:
            self.model.update_item(new)

    def commit(self) -> None:
        new = self.item.moved_to(self.scene_rect_in_page())
        if new != self.item and not self.pending:
            self.model.update_item(new)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.start_editing()
        event.accept()

    def paint_content(self, painter: QPainter) -> None:
        if self.editing or not self.editor.toPlainText():
            # A faint box while typing, so an empty field is visible.
            color = QColor(self.accent)
            color.setAlpha(20)
            painter.fillRect(self.content_rect(), color)
