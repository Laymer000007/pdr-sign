"""Right-hand Fill & Sign panel: tools, text style, the document's fields, Done."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
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
from pdr_sign.ui.saved_signatures import SavedStrip
from pdr_sign.ui.stamp_controls import StampControls
from pdr_sign.ui.stepper import Stepper
from pdr_sign.ui.theme import LIGHT, PANEL_WIDTH, SPACING, Tokens

# (tool, label, icon, shortcut hint)
TOOL_BUTTONS = (
    ("text", "Text", "type", "Click on the page to type"),
    ("check", "Check", "check", "Check: click to place a check mark"),
    ("cross", "Cross", "x", "Click to place a cross"),
    ("dot", "Dot", "dot", "Click to place a dot"),
    ("line", "Line", "minus", "Line"),
    ("date", "Date", "calendar", "Click to place today's date"),
    ("initials", "Initials", "pen-tool", "Place your initials"),
    ("signature", "Signature", "signature", "Place your signature"),
    ("stamp", "Stamp", "stamp", "Place a company stamp"),
)
IMAGE_TOOLS = ("initials", "signature", "stamp")
TILE_COLUMNS = 3
TILE_GAP = SPACING // 2
# Three equal tiles across the panel's content width (panel minus 2 x 16 px padding).
TILE = QSize((PANEL_WIDTH - 4 * SPACING - (TILE_COLUMNS - 1) * TILE_GAP) // TILE_COLUMNS, 60)
NAME_ROLE = Qt.ItemDataRole.UserRole


class FillSignPanel(QWidget):
    tool_selected = Signal(str)
    style_changed = Signal(float, str)  # font size, colour
    field_activated = Signal(str)  # field name
    sign_requested = Signal(str)  # "signature" / "initials": arm the latest or create one
    done = Signal()

    def __init__(self, fields: list[FieldInfo], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FillSignPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Not setFixedWidth: that also pins the *minimum* width, and the layout honours
        # a minimum over a maximum, so collapsing the panel (maximum -> 0) did nothing.
        # The content below has the fixed width; the panel itself may shrink to 0.
        self.setMinimumWidth(0)
        self.setMaximumWidth(PANEL_WIDTH)
        self._buttons: dict[str, QToolButton] = {}
        self._tokens: Tokens = LIGHT

        title = QLabel("Fill & Sign")
        title.setObjectName("PanelTitle")

        tools = QGridLayout()
        tools.setSpacing(TILE_GAP)
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
            button.setFixedSize(TILE)  # identical tiles whatever the label length
            button.clicked.connect(lambda checked, t=tool: self._on_tool(t, checked))
            self.group.addButton(button)
            self._buttons[tool] = button
            tools.addWidget(button, n // TILE_COLUMNS, n % TILE_COLUMNS)

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

        self.saved = {kind: SavedStrip(kind) for kind in ("signature", "initials", "stamp")}
        self.stamp_controls = StampControls()
        self.stamp_controls.hide()  # shown while a stamp is selected
        if fillable:
            self.fields.setMinimumHeight(150)

        self.done_button = QPushButton("Done")
        self.done_button.setProperty("primary", True)
        self.done_button.setToolTip("Close Fill & Sign (Ctrl+E)")
        self.done_button.clicked.connect(self.done)

        # Everything but Done scrolls, so a short window still reaches every section.
        content = QWidget()
        content.setObjectName("FillSignContent")
        content.setFixedWidth(PANEL_WIDTH)
        column = QVBoxLayout(content)
        column.setContentsMargins(SPACING * 2, SPACING * 2, SPACING * 2, SPACING)
        column.setSpacing(SPACING * 1 + SPACING // 2)
        column.addWidget(title)
        column.addLayout(tools)
        column.addWidget(self.stamp_controls)
        column.addWidget(style_label)
        column.addLayout(color_row)
        for strip in self.saved.values():
            column.addWidget(strip)
        column.addWidget(self.fields_title)
        column.addWidget(self.fields, 1)
        if not fillable:
            column.addStretch(1)
        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName("FillSignScroll")
        self.content_scroll.setWidget(content)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, SPACING * 2)
        outer.setSpacing(SPACING)
        outer.addWidget(self.content_scroll, 1)
        done_row = QHBoxLayout()
        done_row.setContentsMargins(SPACING * 2, 0, SPACING * 2, 0)
        done_row.addWidget(self.done_button)
        outer.addLayout(done_row)

    # --- state in -----------------------------------------------------------------

    def set_tokens(self, t: Tokens) -> None:
        self._tokens = t
        for strip in self.saved.values():
            strip.set_tokens(t)
        self.stamp_controls.set_tokens(t)
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
        if checked and tool in IMAGE_TOOLS:
            self.set_tool("")  # lit again once something is armed (tool_changed)
            self.sign_requested.emit(tool)
            return
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
