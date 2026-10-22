"""Image views for the Upload tab: the photo with a crop box, and the result on a
checkerboard (so a transparent background is visible as such)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from pdr_sign.ui.theme import LIGHT


def checkerboard(
    painter: QPainter, rect: QRectF, light: QColor, dark: QColor, cell: int = 8
) -> None:
    painter.save()
    painter.setClipRect(rect)
    y, row = rect.top(), 0
    while y < rect.bottom():
        x, col = rect.left(), 0
        while x < rect.right():
            painter.fillRect(QRectF(x, y, cell, cell), dark if (row + col) % 2 else light)
            x += cell
            col += 1
        y += cell
        row += 1
    painter.restore()


def fit(size: QSize, box: QRectF) -> QRectF:
    if size.isEmpty():
        return QRectF()
    max_upscale = 4.0  # small images may grow, but not into a blur
    scale = min(box.width() / size.width(), box.height() / size.height(), max_upscale)
    w, h = size.width() * scale, size.height() * scale
    return QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)


class CropView(QWidget):
    """The photo, with a crop box you drag out (fractions of the image)."""

    crop_changed = Signal(object)  # tuple of fractions, or None

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(280, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Drag a box around the signature to crop")
        self.setAccessibleName("Photo; drag to crop")
        self.pixmap = QPixmap()
        self.crop: tuple[float, float, float, float] | None = None
        self.accent = self.palette().color(QPalette.ColorRole.Highlight)
        self._start: QPointF | None = None

    def set_image(self, image: QImage) -> None:
        self.pixmap = QPixmap.fromImage(image)
        self.crop = None
        self.update()

    def _image_rect(self) -> QRectF:
        return fit(self.pixmap.size(), QRectF(self.rect()).adjusted(4, 4, -4, -4))

    def _fraction(self, pos: QPointF) -> QPointF:
        r = self._image_rect()
        return QPointF(
            min(max((pos.x() - r.x()) / max(r.width(), 1), 0), 1),
            min(max((pos.y() - r.y()) / max(r.height(), 1), 0), 1),
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.pixmap.isNull():
            self._start = self._fraction(event.position())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start is not None:
            end = self._fraction(event.position())
            a, b = self._start, end
            self.crop = (min(a.x(), b.x()), min(a.y(), b.y()), max(a.x(), b.x()), max(a.y(), b.y()))
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._start is None:
            return
        self._start = None
        if self.crop and (self.crop[2] - self.crop[0] < 0.03 or self.crop[3] - self.crop[1] < 0.03):
            self.crop = None  # a click, not a box
        self.update()
        self.crop_changed.emit(self.crop)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        r = self._image_rect()
        if self.pixmap.isNull():
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No image yet")
            return
        painter.drawPixmap(r, self.pixmap, QRectF(self.pixmap.rect()))
        if self.crop:
            x0, y0, x1, y1 = self.crop
            box = QRectF(
                r.x() + x0 * r.width(),
                r.y() + y0 * r.height(),
                (x1 - x0) * r.width(),
                (y1 - y0) * r.height(),
            )
            shade = QColor(0, 0, 0, 90)
            for part in (
                QRectF(r.left(), r.top(), r.width(), box.top() - r.top()),
                QRectF(r.left(), box.bottom(), r.width(), r.bottom() - box.bottom()),
                QRectF(r.left(), box.top(), box.left() - r.left(), box.height()),
                QRectF(box.right(), box.top(), r.right() - box.right(), box.height()),
            ):
                painter.fillRect(part, shade)
            painter.setPen(QPen(self.accent, 2))
            painter.drawRect(box)


class ResultView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(280, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Cleaned signature preview")
        self.pixmap = QPixmap()
        self.busy = False

    def set_png(self, png: bytes | None) -> None:
        self.pixmap = QPixmap()
        if png:
            self.pixmap.loadFromData(png, "PNG")
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        area = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        # A light checkerboard in both themes, so black ink stays visible on it.
        checkerboard(painter, area, QColor(LIGHT.paper), QColor(LIGHT.paper_border))
        if not self.pixmap.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(
                fit(self.pixmap.size(), area.adjusted(12, 12, -12, -12)),
                self.pixmap,
                QRectF(self.pixmap.rect()),
            )
        elif self.busy:
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "Cleaning up…")
