"""Check mark, cross and dot items: vector marks that scale with their box."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from pdr_sign.ui.overlay.base import OverlayGraphic

MARK_SIZE = 14.0  # points, the default box for a new mark


class MarkGraphic(OverlayGraphic):
    keep_aspect = True

    def paint_content(self, painter: QPainter) -> None:
        r = self.content_rect()
        color = QColor(self.item.color)
        stroke = max(r.width(), r.height()) * 0.14
        if self.item.kind == "dot":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            inset = r.width() * 0.22
            painter.drawEllipse(r.adjusted(inset, inset, -inset, -inset))
            return
        pen = QPen(color, stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        w, h = r.width(), r.height()
        path = QPainterPath()
        if self.item.kind == "check":
            path.moveTo(QPointF(w * 0.18, h * 0.55))
            path.lineTo(QPointF(w * 0.42, h * 0.78))
            path.lineTo(QPointF(w * 0.84, h * 0.24))
        else:  # cross
            path.moveTo(QPointF(w * 0.22, h * 0.22))
            path.lineTo(QPointF(w * 0.78, h * 0.78))
            path.moveTo(QPointF(w * 0.78, h * 0.22))
            path.lineTo(QPointF(w * 0.22, h * 0.78))
        painter.drawPath(path)

    def commit(self) -> None:
        # A mark's font size is its box size, so the saved glyph matches what you see.
        x0, y0, x1, y1 = self.scene_rect_in_page()
        new = self.item.moved_to((x0, y0, x1, y1))
        from dataclasses import replace

        new = replace(new, font_size=round(y1 - y0, 2))
        if new != self.item:
            self.model.update_item(new)
