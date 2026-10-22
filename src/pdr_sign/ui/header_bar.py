"""48 px header: open + sidebar | page and zoom controls | overflow menu."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIntValidator
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QToolButton,
    QWidget,
)

from pdr_sign.services import layout
from pdr_sign.ui import icons
from pdr_sign.ui.theme import HEADER_HEIGHT, SPACING, Tokens, disabled_color


def icon_button(name: str, label: str, shortcut: str = "") -> QToolButton:
    button = QToolButton()
    button.setProperty("iconName", name)
    button.setAccessibleName(label)
    button.setToolTip(f"{label} ({shortcut})" if shortcut else label)
    button.setAutoRaise(True)
    button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return button


# Chosen from three candidates: reads as "finished copy" without suggesting protection.
SIGNED_COPY_ICON = "file-check"


def zoom_label(zoom: float, mode: str) -> str:
    if mode == "fit-width":
        return "Fit width"
    if mode == "fit-page":
        return "Fit page"
    return f"{round(zoom * 100)} %"


class HeaderBar(QWidget):
    open_requested = Signal()
    sidebar_toggled = Signal(bool)
    page_requested = Signal(int)  # 0-based
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    zoom_preset_requested = Signal(object)  # float or "fit-width"/"fit-page"
    about_requested = Signal()
    search_requested = Signal()
    fill_toggled = Signal(bool)
    save_requested = Signal()
    save_as_requested = Signal()
    signed_copy_requested = Signal()
    settings_requested = Signal()
    print_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(HEADER_HEIGHT)
        self._icon_buttons: list[QToolButton] = []

        self.open_button = self._add_icon(icon_button("folder-open", "Open", "Ctrl+O"))
        self.open_button.clicked.connect(self.open_requested)
        self.sidebar_button = self._add_icon(icon_button("panel-left", "Sidebar", "F9"))
        self.sidebar_button.setCheckable(True)
        self.sidebar_button.toggled.connect(self.sidebar_toggled)
        self.print_button = self._add_icon(icon_button("printer", "Print", "Ctrl+P"))
        self.print_button.clicked.connect(self.print_requested)
        self.fill_button = self._add_icon(icon_button("signature", "Fill & Sign", "Ctrl+E"))
        self.fill_button.setObjectName("FillToggle")
        self.fill_button.setCheckable(True)
        self.fill_button.toggled.connect(self.fill_toggled)
        self.save_button = self._add_icon(icon_button("save", "Save", "Ctrl+S"))
        self.save_button.clicked.connect(self.save_requested)
        self.save_button.setEnabled(False)  # only with unsaved changes (set_save_enabled)
        self.signed_copy_button = self._add_icon(icon_button(SIGNED_COPY_ICON, "Save signed copy"))
        self.signed_copy_button.clicked.connect(self.signed_copy_requested)

        self.page_field = QLineEdit()
        self.page_field.setObjectName("PageField")
        self.page_field.setAccessibleName("Current page")
        self.page_field.setToolTip("Go to page")
        self.page_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_field.setFixedWidth(52)
        self.page_field.returnPressed.connect(self._on_page_entered)
        self.page_count = QLabel("/ 0")
        self.page_count.setObjectName("Muted")

        self.zoom_out_button = self._add_icon(icon_button("zoom-out", "Zoom out", "Ctrl+-"))
        self.zoom_out_button.clicked.connect(self.zoom_out_requested)
        self.zoom_button = QToolButton()
        self.zoom_button.setObjectName("ZoomButton")
        self.zoom_button.setAccessibleName("Zoom level")
        self.zoom_button.setToolTip("Zoom level")
        self.zoom_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.zoom_button.setMinimumWidth(84)
        self.zoom_button.setMenu(self._zoom_menu())
        self.zoom_in_button = self._add_icon(icon_button("zoom-in", "Zoom in", "Ctrl++"))
        self.zoom_in_button.clicked.connect(self.zoom_in_requested)

        self.search_button = self._add_icon(icon_button("search", "Search", "Ctrl+F"))
        self.search_button.clicked.connect(self.search_requested)

        self.menu_button = self._add_icon(icon_button("ellipsis-vertical", "Main menu"))
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.menu_button)
        self.print_action = QAction("Print…", menu)
        self.print_action.setShortcut("Ctrl+P")
        # Shown in the menu for discoverability, but the window owns Ctrl+P; a second
        # window-wide binding would make the shortcut ambiguous and fire neither.
        self.print_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.print_action.setShortcutVisibleInContextMenu(True)
        self.print_action.triggered.connect(self.print_requested)
        self.save_as_action = menu.addAction("Save As…")
        self.save_as_action.triggered.connect(self.save_as_requested)
        self.signed_copy_action = menu.addAction("Save signed copy…")
        self.signed_copy_action.triggered.connect(self.signed_copy_requested)
        menu.addAction(self.print_action)
        menu.addSeparator()
        settings = menu.addAction("Settings…")
        settings.triggered.connect(self.settings_requested)
        about = QAction("About PDR", menu)
        about.triggered.connect(self.about_requested)
        menu.addAction(about)
        self.menu_button.setMenu(menu)

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACING, 0, SPACING, 0)
        row.setSpacing(SPACING // 2)
        row.addWidget(self.open_button)
        row.addWidget(self.sidebar_button)
        row.addWidget(self.print_button)
        row.addWidget(self.fill_button)
        row.addWidget(self.save_button)
        row.addWidget(self.signed_copy_button)
        row.addStretch(1)
        row.addWidget(self.page_field)
        row.addWidget(self.page_count)
        row.addSpacing(SPACING * 2)
        row.addWidget(self.zoom_out_button)
        row.addWidget(self.zoom_button)
        row.addWidget(self.zoom_in_button)
        row.addStretch(1)
        row.addWidget(self.search_button)
        row.addWidget(self.menu_button)

        self.document_controls: list[QWidget] = [
            self.sidebar_button,
            self.page_field,
            self.page_count,
            self.zoom_out_button,
            self.zoom_button,
            self.zoom_in_button,
            self.search_button,
        ]
        self.set_document(None)

    def _add_icon(self, button: QToolButton) -> QToolButton:
        self._icon_buttons.append(button)
        return button

    def _zoom_menu(self) -> QMenu:
        menu = QMenu(self)
        for label, value in (("Fit width", "fit-width"), ("Fit page", "fit-page")):
            action = menu.addAction(label)
            action.triggered.connect(lambda _=False, v=value: self.zoom_preset_requested.emit(v))
        menu.addSeparator()
        for zoom in layout.MENU_ZOOMS:
            action = menu.addAction(f"{round(zoom * 100)} %")
            action.triggered.connect(lambda _=False, z=zoom: self.zoom_preset_requested.emit(z))
        return menu

    def set_tokens(self, t: Tokens) -> None:
        dim = disabled_color(t)
        for button in self._icon_buttons:
            on = t.on_accent if button.isCheckable() and button is self.fill_button else None
            name = str(button.property("iconName"))
            button.setIcon(icons.icon(name, t.text, disabled=dim, on=on))

    def set_document(self, page_count: int | None) -> None:
        """Enable the document controls, or disable them when nothing is open."""
        has_doc = page_count is not None
        for widget in self.document_controls:
            widget.setVisible(has_doc)
        self.print_action.setEnabled(has_doc)
        self.print_button.setEnabled(has_doc)
        self.fill_button.setEnabled(has_doc)
        self.save_as_action.setEnabled(has_doc)
        self.signed_copy_action.setEnabled(has_doc)
        self.signed_copy_button.setEnabled(has_doc)
        if not has_doc:
            self.save_button.setEnabled(False)
        if page_count is not None:
            self.page_field.setValidator(QIntValidator(1, page_count, self.page_field))
            self.page_count.setText(f"/ {page_count}")

    def set_page(self, index: int) -> None:
        if not self.page_field.hasFocus():
            self.page_field.setText(str(index + 1))

    def set_zoom(self, zoom: float, mode: str) -> None:
        self.zoom_button.setText(zoom_label(zoom, mode))

    def set_save_enabled(self, dirty: bool) -> None:
        self.save_button.setEnabled(dirty)

    def set_fill_checked(self, checked: bool) -> None:
        self.fill_button.blockSignals(True)
        self.fill_button.setChecked(checked)
        self.fill_button.blockSignals(False)

    def set_sidebar_checked(self, checked: bool) -> None:
        self.sidebar_button.blockSignals(True)
        self.sidebar_button.setChecked(checked)
        self.sidebar_button.blockSignals(False)

    def _on_page_entered(self) -> None:
        text = self.page_field.text().strip()
        if text.isdigit():
            self.page_requested.emit(int(text) - 1)
        self.page_field.clearFocus()
