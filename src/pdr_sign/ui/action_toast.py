"""A toast with buttons ("Signed copy saved · Open · Show in folder")."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from pdr_sign.ui.theme import SPACING

VISIBLE_MS = 12000  # long enough to reach for a button


class ActionToast(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("ActionToast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.label = QLabel()
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(SPACING * 2, SPACING, SPACING, SPACING)
        self.row.setSpacing(SPACING)
        self.row.addWidget(self.label)
        self.buttons: list[QToolButton] = []
        self.dismiss = QToolButton()
        self.dismiss.setText("✕")
        self.dismiss.setAccessibleName("Dismiss")
        self.dismiss.setToolTip("Dismiss")
        self.dismiss.clicked.connect(self.hide)
        self._timer = QTimer(self, singleShot=True, interval=VISIBLE_MS)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_actions(self, text: str, actions: list[tuple[str, Callable[[], None]]]) -> None:
        for button in self.buttons:
            self.row.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        self.row.removeWidget(self.dismiss)
        self.label.setText(text)
        self.label.setAccessibleName(text)
        for label, action in actions:
            button = QToolButton()
            button.setObjectName("ToastAction")
            button.setText(label)
            button.clicked.connect(lambda _=False, a=action: self._run(a))
            self.row.addWidget(button)
            self.buttons.append(button)
        self.row.addWidget(self.dismiss)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start()

    def _run(self, action: Callable[[], None]) -> None:
        self.hide()
        action()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.adjustSize()
            self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)
