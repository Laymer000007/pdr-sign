"""Right-hand Fill & Sign panel: tools, text style, the document's fields, Done."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services.forms import FieldInfo, FieldValue
from pdr_sign.services.stamps import (
    DEFAULT_FONT_SIZE,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    TEXT_COLORS,
)
from pdr_sign.ui import icons
from pdr_sign.ui.stepper import Stepper
from pdr_sign.ui.theme import LIGHT, PANEL_WIDTH, SPACING, Tokens

# (tool, label, icon, shortcut hint)
TOOL_BUTTONS = (
    ("text", "Text", "type", "Click on the page to type"),
    ("check", "Checkmark", "check", "Click to place a tick"),
    ("cross", "Cross", "x", "Click to place a cross"),
    ("dot", "Dot", "dot", "Click to place a dot"),
    ("date", "Date", "calendar", "Click to place today's date"),
)
NAME_ROLE = Qt.ItemDataRole.UserRole


class FillSignPanel(QWidget):
    tool_selected = Signal(str)
    style_changed = Signal(float, str)  # font size, colour
    field_activated = Signal(str)  # field name
    done = Signal()

    def __init__(self, fields: list[FieldInfo], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FillSignPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(PANEL_WIDTH)
        self._buttons: dict[str, QToolButton] = {}
        self._tokens: Tokens = LIGHT

        title = QLabel("Fill & Sign")
        title.setObjectName("PanelTitle")

        tools = QGridLayout()
        tools.setSpacing(SPACING // 2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(False)  # so the active tool can be clicked off again
        for n, (tool, label, icon_name, hint) in enumerate(TOOL_BUTTONS):
            button = QToolButton()
            button.setObjectName("ToolButton")
            button.setText(label)
            button.setProperty("iconName", icon_name)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setAccessibleName(f"{label} tool")
            button.setToolTip(hint)
            button.setMinimumSize(76, 56)
            button.clicked.connect(lambda checked, t=tool: self._on_tool(t, checked))
            self.group.addButton(button)
            self._buttons[tool] = button
            tools.addWidget(button, n // 3, n % 3)

        style_label = QLabel("Text")
        style_label.setObjectName("SectionTitle")
        self.size_box = Stepper(
            int(MIN_FONT_SIZE), int(MAX_FONT_SIZE), int(DEFAULT_FONT_SIZE), " pt", "Text size"
        )
        self.size_box.value_changed.connect(lambda _: self._emit_style())
        self.colors: dict[str, QToolButton] = {}
        color_row = QHBoxLayout()
        color_row.setSpacing(SPACING // 2)
        color_row.addWidget(self.size_box)
        color_row.addStretch()
        color_group = QButtonGroup(self)
        for name, value in TEXT_COLORS.items():
            swatch = QToolButton()
            swatch.setObjectName("Swatch")
            swatch.setCheckable(True)
            swatch.setAccessibleName(f"{name.capitalize()} text")
            swatch.setToolTip(f"{name.capitalize()} text")
            swatch.setStyleSheet(f"#Swatch {{ background: {value}; }}")
            swatch.setFixedSize(24, 24)
            swatch.clicked.connect(lambda _=False: self._emit_style())
            color_group.addButton(swatch)
            color_row.addWidget(swatch)
            self.colors[value] = swatch
        self.colors[TEXT_COLORS["black"]].setChecked(True)

        fillable = _unique_fillable(fields)
        self.fields_title = QLabel("Fields in this document")
        self.fields_title.setObjectName("SectionTitle")
        self.fields = QListWidget()
        self.fields.setObjectName("FieldList")
        self.fields.setAccessibleName("Fields in this document")
        self.fields.setFrameShape(QFrame.Shape.NoFrame)
        for f in fillable:
            item = QListWidgetItem(f.display_name + (" *" if f.required else ""))
            item.setData(NAME_ROLE, f.name)
            item.setToolTip(f.name)
            self.fields.addItem(item)
        self.fields.itemActivated.connect(lambda it: self.field_activated.emit(it.data(NAME_ROLE)))
        self.fields.itemClicked.connect(lambda it: self.field_activated.emit(it.data(NAME_ROLE)))
        for widget in (self.fields_title, self.fields):
            widget.setVisible(bool(fillable))

        self.done_button = QPushButton("Done")
        self.done_button.setProperty("primary", True)
        self.done_button.setToolTip("Close Fill & Sign (Ctrl+E)")
        self.done_button.clicked.connect(self.done)

        column = QVBoxLayout(self)
        column.setContentsMargins(SPACING * 2, SPACING * 2, SPACING * 2, SPACING * 2)
        column.setSpacing(SPACING * 1 + SPACING // 2)
        column.addWidget(title)
        column.addLayout(tools)
        column.addWidget(style_label)
        column.addLayout(color_row)
        column.addWidget(self.fields_title)
        column.addWidget(self.fields, 1)
        if not fillable:
            column.addStretch(1)
        column.addWidget(self.done_button)

    # --- state in -----------------------------------------------------------------

    def set_tokens(self, t: Tokens) -> None:
        self._tokens = t
        self.size_box.set_tokens(t)
        for button in self._buttons.values():
            name = str(button.property("iconName"))
            button.setIcon(icons.icon(name, t.text, 20, on=t.on_accent))

    def set_tool(self, tool: str) -> None:
        for name, button in self._buttons.items():
            button.setChecked(name == tool)

    def set_style(self, font_size: float, color: str) -> None:
        self.size_box.set_value(round(font_size))
        swatch = self.colors.get(color.upper()) or self.colors.get(color)
        if swatch is not None:
            swatch.setChecked(True)

    def set_values(self, values: dict[str, FieldValue]) -> None:
        """Mark filled fields with a tick in the list."""
        for row in range(self.fields.count()):
            item = self.fields.item(row)
            name = item.data(NAME_ROLE)
            filled = bool(values.get(name))
            item.setIcon(
                icons.icon("check", self._tokens.text, 14)
                if filled
                else icons.icon("dot", self._tokens.muted, 14)
            )

    # --- state out ------------------------------------------------------------------

    def current_color(self) -> str:
        return next((c for c, b in self.colors.items() if b.isChecked()), TEXT_COLORS["black"])

    def _emit_style(self) -> None:
        self.style_changed.emit(float(self.size_box.value()), self.current_color())

    def _on_tool(self, tool: str, checked: bool) -> None:
        self.set_tool(tool if checked else "")
        self.tool_selected.emit(tool if checked else "")


def _unique_fillable(fields: list[FieldInfo]) -> list[FieldInfo]:
    seen: set[str] = set()
    result = []
    for f in fields:
        if f.fillable and f.name not in seen:
            seen.add(f.name)
            result.append(f)
    return result
