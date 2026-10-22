"""A slim, dismissible notice above the canvas (non-blocking)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from pdr_sign.ui.theme import SPACING


class Banner(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAccessibleName(text)
        self.close_button = QToolButton()
        self.close_button.setText("Dismiss")
        self.close_button.setAccessibleName("Dismiss notice")
        self.close_button.clicked.connect(self.hide)
        row = QHBoxLayout(self)
        row.setContentsMargins(SPACING * 2, SPACING, SPACING * 2, SPACING)
        row.addWidget(self.label, 1)
        row.addWidget(self.close_button)
