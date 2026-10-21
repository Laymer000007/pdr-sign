"""Lucide SVG icons, recoloured at runtime to the theme foreground."""

from __future__ import annotations

from functools import cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from pdr_sign.resources import ICONS_DIR


@cache
def _svg_source(name: str) -> str:
    path = ICONS_DIR / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"unknown icon: {name}")
    return path.read_text(encoding="utf-8")


def svg_data(name: str, color: str) -> bytes:
    """The icon's SVG with ``currentColor`` replaced by ``color``."""
    return _svg_source(name).replace("currentColor", color).encode("utf-8")


@cache
def pixmap(name: str, color: str, size: int = 18, dpr: float = 1.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_data(name, color)))
    px = QPixmap(QSize(round(size * dpr), round(size * dpr)))
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, px.width(), px.height()))
    painter.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(name: str, color: str, size: int = 18) -> QIcon:
    """A QIcon with crisp 1x and 2x renders, so HiDPI screens stay sharp."""
    result = QIcon()
    for dpr in (1.0, 2.0):
        result.addPixmap(pixmap(name, color, size, dpr))
    return result
