"""Inline editors for AcroForm fields, placed at the exact field rectangles.

Each editor is a child of its PageItem, so it scales with zoom. Text and choice fields
are real Qt widgets in QGraphicsProxyWidgets; check boxes and radios are painted.
Edits go to the FillModel (undoable); model changes (undo, a twin widget) come back
through ``FillModel.field_changed``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFocusEvent, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGraphicsItem,
    QGraphicsProxyWidget,
    QGraphicsSceneMouseEvent,
    QGraphicsWidget,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSizePolicy,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pdr_sign.services.forms import FieldInfo, FieldValue

if TYPE_CHECKING:
    from pdr_sign.ui.fill_model import FillModel
    from pdr_sign.ui.page_item import PageItem

FIELD_FONT = "Helvetica"  # what the saved appearance uses
EXPORT_ROLE = Qt.ItemDataRole.UserRole


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


class _PlainText(QPlainTextEdit):
    editing_finished = Signal()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.editing_finished.emit()


class FieldProxy(QGraphicsProxyWidget):
    """A text, combo or list field."""

    def __init__(self, field: FieldInfo, widget: QWidget, parent: PageItem) -> None:
        super().__init__(parent)
        self.field = field
        widget.setObjectName("FormField")
        widget.setAccessibleName(field.display_name)
        widget.setToolTip(field.display_name + (" (required)" if field.required else ""))
        widget.setStyleSheet(field_style(auto_font_px(field)))
        widget.setMinimumSize(1, 1)
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setWidget(widget)
        x0, y0, x1, y1 = field.rect
        self.setGeometry(QRectF(x0, y0, x1 - x0, y1 - y0))
        self.setZValue(5)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        super().paint(painter, option, widget)  # type: ignore[arg-type]
        if self.hasFocus() or self.widget().hasFocus():
            painter.setPen(QPen(FieldColors.accent, 0))
            painter.drawRect(self.rect())


class ToggleField(QGraphicsWidget):
    """A check box or one radio button, painted to fill its box at any zoom."""

    toggled = Signal()

    def __init__(self, field: FieldInfo, parent: PageItem) -> None:
        super().__init__(parent)
        self.field = field
        self.checked = False
        x0, y0, x1, y1 = field.rect
        self.setGeometry(QRectF(x0, y0, x1 - x0, y1 - y0))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(field.display_name)
        self.setZValue(5)

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        border = FieldColors.accent if self.hasFocus() else FieldColors.border
        painter.setPen(QPen(border, 0))
        painter.setBrush(FieldColors.fill)
        radio = self.field.kind == "radio"
        if radio:
            painter.drawEllipse(r)
        else:
            painter.drawRect(r)
        if not self.checked:
            return
        black = QColor("black")
        if radio:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(black)
            inset = r.width() * 0.28
            painter.drawEllipse(r.adjusted(inset, inset, -inset, -inset))
            return
        pen = QPen(black, max(r.width(), r.height()) * 0.12)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        w, h = r.width(), r.height()
        points = [
            QPointF(w * 0.2, h * 0.52),
            QPointF(w * 0.42, h * 0.75),
            QPointF(w * 0.82, h * 0.25),
        ]
        painter.drawPolyline([r.topLeft() + p for p in points])

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.rect().contains(event.pos()):
            self.toggled.emit()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space:
            self.toggled.emit()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.update()


FieldGraphic = FieldProxy | ToggleField


class FieldLayer:
    """All field editors of one document, kept in step with the FillModel."""

    def __init__(self, model: FillModel, pages: list[PageItem]) -> None:
        self.model = model
        self.graphics: list[FieldGraphic] = []
        self.by_name: dict[str, list[FieldGraphic]] = {}
        self._setters: dict[int, Callable[[FieldValue], None]] = {}
        for field in model.fields:
            if not field.fillable:
                continue
            graphic = self._build(field, pages[field.page])
            self.graphics.append(graphic)
            self.by_name.setdefault(field.name, []).append(graphic)
        for a, b in zip(self.graphics, self.graphics[1:], strict=False):
            QGraphicsWidget.setTabOrder(a, b)
        for name, value in model.values.items():
            self._show(name, value)
        model.field_changed.connect(self._show)

    def _show(self, name: str, value: FieldValue) -> None:
        for graphic in self.by_name.get(name, []):
            self._setters[id(graphic)](value)

    def focus(self, name: str) -> FieldGraphic | None:
        graphics = self.by_name.get(name)
        if not graphics:
            return None
        graphics[0].setFocus(Qt.FocusReason.OtherFocusReason)
        return graphics[0]

    def commit_pending(self) -> None:
        """Push edits still sitting in a focused editor (before save or close)."""
        for graphic in self.graphics:
            if isinstance(graphic, FieldProxy) and graphic.widget().hasFocus():
                graphic.widget().clearFocus()

    # --- builders ----------------------------------------------------------------

    def _build(self, field: FieldInfo, page: PageItem) -> FieldGraphic:
        if field.kind in ("checkbox", "radio"):
            return self._toggle(field, page)
        if field.kind == "combo":
            return self._combo(field, page)
        if field.kind == "list":
            return self._list(field, page)
        return self._text(field, page)

    def _text(self, field: FieldInfo, page: PageItem) -> FieldProxy:
        name = field.name
        if field.multiline:
            area = _PlainText()
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setTabChangesFocus(True)
            area.document().setDocumentMargin(1)
            area.editing_finished.connect(
                lambda: self.model.set_field_value(name, area.toPlainText())
            )
            proxy = FieldProxy(field, area, page)

            def set_area(v: FieldValue) -> None:
                if area.toPlainText() != v:
                    area.setPlainText(str(v))

            self._setters[id(proxy)] = set_area
            return proxy
        line = QLineEdit()
        line.setFrame(False)
        if field.max_len:
            line.setMaxLength(field.max_len)
        if field.comb:
            line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if field.password:
            line.setEchoMode(QLineEdit.EchoMode.Password)
        line.editingFinished.connect(lambda: self.model.set_field_value(name, line.text()))
        proxy = FieldProxy(field, line, page)

        def set_line(v: FieldValue) -> None:
            if line.text() != v:
                line.setText(str(v))

        self._setters[id(proxy)] = set_line
        return proxy

    def _combo(self, field: FieldInfo, page: PageItem) -> FieldProxy:
        combo = QComboBox()
        combo.setEditable(field.editable)
        combo.setFrame(False)
        for export, label in field.options:
            combo.addItem(label, export)
        name = field.name

        def current() -> str:
            index = combo.currentIndex()
            text = combo.currentText()
            if index >= 0 and combo.itemText(index) == text:
                return str(combo.itemData(index))
            return text

        combo.activated.connect(lambda _i: self.model.set_field_value(name, current()))
        if field.editable and combo.lineEdit() is not None:
            combo.lineEdit().editingFinished.connect(  # type: ignore[union-attr]
                lambda: self.model.set_field_value(name, current())
            )
        proxy = FieldProxy(field, combo, page)

        def set_combo(v: FieldValue) -> None:
            value = str(v)
            index = combo.findData(value)
            if index < 0 and field.editable:
                combo.setEditText(value)
            else:
                combo.setCurrentIndex(index)

        self._setters[id(proxy)] = set_combo
        return proxy

    def _list(self, field: FieldInfo, page: PageItem) -> FieldProxy:
        box = QListWidget()
        box.setFrameShape(QFrame.Shape.NoFrame)
        multi = QAbstractItemView.SelectionMode.MultiSelection
        box.setSelectionMode(
            multi if field.multi_select else QAbstractItemView.SelectionMode.SingleSelection
        )
        for export, label in field.options:
            item = QListWidgetItem(label)
            item.setData(EXPORT_ROLE, export)
            box.addItem(item)
        name = field.name
        box.itemSelectionChanged.connect(
            lambda: self.model.set_field_value(
                name, tuple(str(i.data(EXPORT_ROLE)) for i in box.selectedItems())
            )
        )
        proxy = FieldProxy(field, box, page)

        def set_list(v: FieldValue) -> None:
            selected = set(v) if isinstance(v, tuple) else {v}
            box.blockSignals(True)
            for row in range(box.count()):
                item = box.item(row)
                item.setSelected(str(item.data(EXPORT_ROLE)) in selected)
            box.blockSignals(False)

        self._setters[id(proxy)] = set_list
        return proxy

    def _toggle(self, field: FieldInfo, page: PageItem) -> ToggleField:
        toggle = ToggleField(field, page)
        name, on = field.name, field.on_state

        def flip() -> None:
            if field.kind == "radio":
                self.model.set_field_value(name, on)
            else:
                self.model.set_field_value(name, "" if toggle.checked else on)

        toggle.toggled.connect(flip)

        def set_toggle(v: FieldValue) -> None:
            toggle.checked = bool(v) and v == on
            toggle.update()

        self._setters[id(toggle)] = set_toggle
        return toggle
