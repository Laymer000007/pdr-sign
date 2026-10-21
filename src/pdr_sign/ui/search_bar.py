"""Slim find bar shown above the canvas (Ctrl+F)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

from pdr_sign.ui import icons
from pdr_sign.ui.header_bar import icon_button
from pdr_sign.ui.theme import SPACING, Tokens

DEBOUNCE_MS = 200


class SearchBar(QWidget):
    query_changed = Signal(str)  # debounced
    next_requested = Signal()
    previous_requested = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SearchBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.field = QLineEdit()
        self.field.setObjectName("SearchField")
        self.field.setPlaceholderText("Search in document")
        self.field.setAccessibleName("Search in document")
        self.field.setClearButtonEnabled(True)
        self.field.setMinimumWidth(260)
        self.field.installEventFilter(self)
        self.count = QLabel("")
        self.count.setObjectName("Muted")
        self.count.setMinimumWidth(96)

        self.prev_button = icon_button("chevron-up", "Previous match", "Shift+Enter")
        self.next_button = icon_button("chevron-down", "Next match", "Enter")
        self.close_button = icon_button("x", "Close search", "Esc")
        self._buttons: list[QToolButton] = [self.prev_button, self.next_button, self.close_button]
        self.prev_button.clicked.connect(self.previous_requested)
        self.next_button.clicked.connect(self.next_requested)
        self.close_button.clicked.connect(self.close_bar)

        self._debounce = QTimer(self, singleShot=True, interval=DEBOUNCE_MS)
        self._debounce.timeout.connect(lambda: self.query_changed.emit(self.field.text()))
        self.field.textChanged.connect(lambda _: self._debounce.start())

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACING * 2, SPACING, SPACING * 2, SPACING)
        row.setSpacing(SPACING // 2)
        row.addStretch()
        row.addWidget(self.field)
        row.addWidget(self.count)
        row.addWidget(self.prev_button)
        row.addWidget(self.next_button)
        row.addWidget(self.close_button)
        row.addStretch()
        self.hide()

    def set_tokens(self, t: Tokens) -> None:
        for button in self._buttons:
            button.setIcon(icons.icon(str(button.property("iconName")), t.text))

    def open_bar(self) -> None:
        self.show()
        self.field.setFocus()
        self.field.selectAll()

    def close_bar(self) -> None:
        self._debounce.stop()
        self.hide()
        self.closed.emit()

    def set_status(self, current: int, total: int, running: bool, capped: bool) -> None:
        if not self.field.text().strip():
            self.count.setText("")
        elif total == 0:
            self.count.setText("Searching…" if running else "No matches")
        else:
            more = "+" if capped else ""
            self.count.setText(f"{max(current, 0) + 1} of {total}{more}")
        self.prev_button.setEnabled(total > 0)
        self.next_button.setEnabled(total > 0)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.field and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._debounce.isActive():  # Enter before the debounce fired: search now
                    self._debounce.stop()
                    self.query_changed.emit(self.field.text())
                elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.previous_requested.emit()
                else:
                    self.next_requested.emit()
                return True
            if key == Qt.Key.Key_Escape:
                self.close_bar()
                return True
        return super().eventFilter(watched, event)
