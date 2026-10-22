"""Small "125 %" pill that appears over the canvas while zooming, then fades."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from pdr_sign.ui.theme import ANIMATION_MS, animations_enabled

VISIBLE_MS = 700


class ZoomIndicator(QLabel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("ZoomIndicator")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(ANIMATION_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._hide_timer = QTimer(self, singleShot=True, interval=VISIBLE_MS)
        self._hide_timer.timeout.connect(self._fade_out)
        self.hide()

    def show_zoom(self, zoom: float) -> None:
        self.show_message(f"{round(zoom * 100)} %")

    def show_message(self, text: str, visible_ms: int = VISIBLE_MS) -> None:
        """A short-lived pill (zoom level, "Saved", …)."""
        self._hide_timer.setInterval(visible_ms)
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self._fade.stop()
        if not self.isVisible() and animations_enabled():
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        else:
            self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._hide_timer.start()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)

    def _fade_out(self) -> None:
        if not animations_enabled():
            self.hide()
            return
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()
