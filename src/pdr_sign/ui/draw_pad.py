"""A forgiving drawing pad for signatures, tuned for touchpads and mice.

- A "lazy brush" stabiliser: the pen trails the pointer by a few pixels, so the
  wobble of a touchpad finger doesn't reach the ink; when a stroke ends, a light
  moving average takes out what tremor remains.
- Strokes are drawn as quadratic curves through midpoints (smooth, no corners), with a
  little thinning on fast movement for a natural pen look.
- Strokes live in a fixed 1000x400 canvas, so resizing the dialog scales the drawing
  instead of clipping it.
- Undo the last stroke, clear, pick pen width and ink. Tablet pressure is used when
  present.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QTabletEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from pdr_sign.services import sigimage
from pdr_sign.ui.theme import LIGHT

CANVAS_W, CANVAS_H = 1000.0, 400.0
LAZY_RADIUS = 5.0  # canvas units the pen trails behind the pointer
SMOOTH_WINDOW = 2  # points either side averaged when a stroke ends
PEN_WIDTHS = {"fine": 3.0, "medium": 5.0, "bold": 8.0}
EXPORT_SCALE = 1.6  # canvas units → output pixels


def image_to_png(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")  # type: ignore[call-overload]  # stub: bytes; runtime: str
    return bytes(buffer.data().data())


def smooth(points: list[QPointF], window: int = SMOOTH_WINDOW) -> list[QPointF]:
    """A centred moving average that keeps both ends where they were drawn.

    Takes out the last bit of hand and touchpad tremor without rounding off the
    start and end of the stroke.
    """
    if len(points) <= 2 * window + 1:
        return points
    result = [points[0]]
    for i in range(1, len(points) - 1):
        k = min(window, i, len(points) - 1 - i)
        span = points[i - k : i + k + 1]
        result.append(
            QPointF(sum(p.x() for p in span) / len(span), sum(p.y() for p in span) / len(span))
        )
    result.append(points[-1])
    return result


@dataclass
class Stroke:
    points: list[QPointF] = field(default_factory=list)
    widths: list[float] = field(default_factory=list)  # per point, already smoothed


class DrawPad(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DrawPad")
        self.setAccessibleName("Signature drawing area")
        self.setToolTip("Draw your signature here")
        self.setMinimumSize(560, 230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.strokes: list[Stroke] = []
        self.pen_width = PEN_WIDTHS["medium"]
        self.ink = QColor(*sigimage.INK_COLORS["black"])
        self.guide = QColor(LIGHT.paper_muted)
        self._current: Stroke | None = None
        self._brush = QPointF()
        self._last_time = 0
        self._pressure = 1.0

    def sizeHint(self) -> QSize:
        return QSize(680, 272)

    # --- public -----------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not self.strokes

    def set_ink(self, color: QColor) -> None:
        self.ink = color
        self.update()

    def set_pen_width(self, name: str) -> None:
        self.pen_width = PEN_WIDTHS.get(name, self.pen_width)
        self.update()

    def undo(self) -> None:
        if self.strokes:
            self.strokes.pop()
            self.update()
            self.changed.emit()

    def clear(self) -> None:
        if self.strokes:
            self.strokes.clear()
            self.update()
            self.changed.emit()

    def to_png(self) -> bytes:
        """The drawing as a transparent PNG, trimmed to the ink."""
        size = QSize(round(CANVAS_W * EXPORT_SCALE), round(CANVAS_H * EXPORT_SCALE))
        image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(EXPORT_SCALE, EXPORT_SCALE)
        self._paint_strokes(painter)
        painter.end()
        return sigimage.trim_png(image_to_png(image))

    # --- geometry -------------------------------------------------------------------

    def _canvas_rect(self) -> QRectF:
        """Where the 1000x400 canvas sits in the widget (centred, aspect kept)."""
        scale = min(self.width() / CANVAS_W, self.height() / CANVAS_H)
        w, h = CANVAS_W * scale, CANVAS_H * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _to_canvas(self, pos: QPointF) -> QPointF:
        r = self._canvas_rect()
        return QPointF(
            (pos.x() - r.x()) * CANVAS_W / r.width(), (pos.y() - r.y()) * CANVAS_H / r.height()
        )

    # --- input ---------------------------------------------------------------------

    def _begin(self, pos: QPointF, pressure: float) -> None:
        point = self._to_canvas(pos)
        self._brush = point
        self._pressure = pressure
        self._current = Stroke([point], [self.pen_width * pressure])
        self.strokes.append(self._current)
        self._last_time = 0
        self.update()

    def _extend(self, pos: QPointF, pressure: float, timestamp: int) -> None:
        stroke = self._current
        if stroke is None:
            return
        pointer = self._to_canvas(pos)
        offset = pointer - self._brush
        distance = math.hypot(offset.x(), offset.y())
        if distance <= LAZY_RADIUS:
            return  # inside the lazy radius: the pen stays put, the wobble is ignored
        step = (distance - LAZY_RADIUS) / distance
        self._brush = self._brush + offset * step
        # Faster strokes get a touch thinner, like a real pen; smoothed to avoid jumps.
        dt = max(1, timestamp - self._last_time) if self._last_time else 16
        self._last_time = timestamp
        speed = (distance - LAZY_RADIUS) / dt
        target = self.pen_width * pressure * max(0.6, min(1.1, 1.15 - speed * 0.12))
        width = stroke.widths[-1] * 0.7 + target * 0.3
        stroke.points.append(QPointF(self._brush))
        stroke.widths.append(width)
        self.update()

    def _finish(self) -> None:
        if self._current is not None:
            self._current.points = smooth(self._current.points)
            self._current = None
            self.update()
            self.changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin(event.position(), 1.0)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._extend(event.position(), 1.0, event.timestamp())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._finish()

    def tabletEvent(self, event: QTabletEvent) -> None:
        pressure = 0.4 + 0.8 * event.pressure()
        kind = event.type()
        if kind == QTabletEvent.Type.TabletPress:
            self._begin(event.position(), pressure)
        elif kind == QTabletEvent.Type.TabletMove and self._current is not None:
            self._extend(event.position(), pressure, event.timestamp())
        elif kind == QTabletEvent.Type.TabletRelease:
            self._finish()
        event.accept()

    # --- painting ---------------------------------------------------------------------

    def _paint_strokes(self, painter: QPainter) -> None:
        for stroke in self.strokes:
            points, widths = stroke.points, stroke.widths
            if len(points) == 1:  # a dot
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self.ink)
                r = widths[0] / 2
                painter.drawEllipse(points[0], r, r)
                continue
            # Quadratic curves through midpoints: each segment runs from one midpoint
            # to the next, bending through the recorded point between them.
            previous = points[0]
            for i in range(1, len(points)):
                mid_end = (points[i] + points[i + 1]) / 2 if i + 1 < len(points) else points[i]
                pen = QPen(self.ink, widths[i])
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath(previous)
                path.quadTo(points[i], mid_end)
                painter.drawPath(path)
                previous = mid_end

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._canvas_rect()
        # Paper in both themes: the ink is black or blue, like the pages it lands on.
        painter.setPen(QPen(QColor(LIGHT.paper_border), 1))
        painter.setBrush(QColor(LIGHT.paper))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        # A baseline and a hint, like the line on a paper form.
        y = rect.top() + rect.height() * 0.72
        guide = QPen(self.guide, 1, Qt.PenStyle.DashLine)
        painter.setPen(guide)
        painter.drawLine(QPointF(rect.left() + 24, y), QPointF(rect.right() - 24, y))
        if self.is_empty:
            painter.drawText(
                QRectF(rect.left(), y + 6, rect.width(), 24),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "Sign above the line",
            )
        painter.translate(rect.topLeft())
        painter.scale(rect.width() / CANVAS_W, rect.height() / CANVAS_H)
        self._paint_strokes(painter)
        painter.end()
