"""Panel controls shown while a stamp is selected: quarter turns and opacity."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from pdr_sign.services.stamps import MIN_OPACITY
from pdr_sign.ui import icons
from pdr_sign.ui.theme import SPACING, Tokens


class StampControls(QWidget):
    rotate_requested = Signal(float)  # degrees, clockwise
    opacity_changed = Signal(float)  # 0.5–1.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel("Stamp")
        title.setObjectName("SectionTitle")
        self.turn_left = QToolButton()
        self.turn_left.setToolTip("Turn 90° left")
        self.turn_left.setAccessibleName("Turn stamp 90 degrees left")
        self.turn_left.clicked.connect(lambda: self.rotate_requested.emit(-90.0))
        self.turn_right = QToolButton()
        self.turn_right.setToolTip("Turn 90° right")
        self.turn_right.setAccessibleName("Turn stamp 90 degrees right")
        self.turn_right.clicked.connect(lambda: self.rotate_requested.emit(90.0))
        self.angle = QLabel("0°")
        self.angle.setAccessibleName("Stamp angle")
        hint = QLabel("Drag the round handle to turn freely; Shift snaps to 15°.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(round(MIN_OPACITY * 100), 100)
        self.opacity.setValue(100)
        self.opacity.setAccessibleName("Stamp opacity")
        self.opacity.setToolTip("Opacity")
        self.opacity.valueChanged.connect(self._on_opacity)
        self.opacity_label = QLabel("100 %")
        self.opacity_label.setMinimumWidth(44)

        turn_row = QHBoxLayout()
        turn_row.setSpacing(SPACING // 2)
        turn_row.addWidget(self.turn_left)
        turn_row.addWidget(self.turn_right)
        turn_row.addWidget(self.angle)
        turn_row.addStretch()
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity"))
        opacity_row.addWidget(self.opacity, 1)
        opacity_row.addWidget(self.opacity_label)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING // 2)
        column.addWidget(title)
        column.addLayout(turn_row)
        column.addWidget(hint)
        column.addLayout(opacity_row)

    def set_tokens(self, t: Tokens) -> None:
        self.turn_left.setIcon(icons.icon("rotate-ccw", t.text))
        self.turn_right.setIcon(icons.icon("rotate-cw", t.text))

    def show_stamp(self, rotation: float, opacity: float) -> None:
        signed = rotation - 360 if rotation > 180 else rotation  # 348° reads better as -12°
        self.angle.setText(f"{signed:.0f}°")
        self.opacity.blockSignals(True)
        self.opacity.setValue(round(opacity * 100))
        self.opacity.blockSignals(False)
        self.opacity_label.setText(f"{round(opacity * 100)} %")

    def _on_opacity(self, percent: int) -> None:
        self.opacity_label.setText(f"{percent} %")
        self.opacity_changed.emit(percent / 100)
