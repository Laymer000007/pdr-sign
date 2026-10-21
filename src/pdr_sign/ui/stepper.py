"""A compact "- 12 pt +" stepper (QSpinBox arrows do not survive our stylesheet)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from pdr_sign.ui import icons
from pdr_sign.ui.theme import Tokens, disabled_color


class Stepper(QWidget):
    value_changed = Signal(int)

    def __init__(
        self,
        minimum: int,
        maximum: int,
        value: int,
        suffix: str,
        name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.minimum, self.maximum, self.suffix = minimum, maximum, suffix
        self._value = value
        self.setObjectName("Stepper")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAccessibleName(name)
        self.down = QToolButton()
        self.up = QToolButton()
        for button, label, delta in (
            (self.down, f"Smaller {name.lower()}", -1),
            (self.up, f"Larger {name.lower()}", 1),
        ):
            button.setAccessibleName(label)
            button.setToolTip(label)
            button.setAutoRepeat(True)
            button.clicked.connect(lambda _=False, d=delta: self.set_value(self._value + d, True))
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumWidth(44)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(0)
        row.addWidget(self.down)
        row.addWidget(self.label)
        row.addWidget(self.up)
        self.set_value(value)

    def value(self) -> int:
        return self._value

    def set_value(self, value: int, emit: bool = False) -> None:
        value = max(self.minimum, min(self.maximum, value))
        changed = value != self._value
        self._value = value
        self.label.setText(f"{value}{self.suffix}")
        self.label.setAccessibleName(f"{self.accessibleName()}: {value}{self.suffix}")
        self.down.setEnabled(value > self.minimum)
        self.up.setEnabled(value < self.maximum)
        if emit and changed:
            self.value_changed.emit(value)

    def set_tokens(self, t: Tokens) -> None:
        dim = disabled_color(t)
        self.down.setIcon(icons.icon("minus", t.text, 14, disabled=dim))
        self.up.setIcon(icons.icon("plus", t.text, 14, disabled=dim))
