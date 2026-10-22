"""Render the app icon SVG to every hicolor PNG size (dev tool; outputs are committed).

.venv/bin/python packaging/tools/make_icons.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from pdr_sign import APP_ID  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def main() -> None:
    QGuiApplication([])
    source = ROOT / "src" / "pdr_sign" / "resources" / "pdr-sign.svg"
    out = ROOT / "packaging" / "linux" / "icons" / "hicolor"
    renderer = QSvgRenderer(str(source))
    for size in SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        target = out / f"{size}x{size}" / "apps" / f"{APP_ID}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(target))
    scalable = out / "scalable" / "apps" / f"{APP_ID}.svg"
    scalable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, scalable)
    print("icons written to", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
