"""Generate docs/screenshots/*.png for the AppStream metainfo and README (dev tool).

QT_QPA_PLATFORM=offscreen .venv/bin/python packaging/tools/store_screenshots.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "packaging" / "tools")]

import screenshot_doc  # noqa: E402
from PySide6.QtCore import QEventLoop, QPointF, QTimer  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from tests.sigphoto import phone_photo, stamp_photo  # noqa: E402

from pdr_sign.app import build_window, configure  # noqa: E402
from pdr_sign.services import sigimage  # noqa: E402
from pdr_sign.services.recent import RecentFiles  # noqa: E402
from pdr_sign.services.settings import Settings  # noqa: E402
from pdr_sign.services.sigimage import PhotoOptions  # noqa: E402
from pdr_sign.ui.signature_dialog import render_typed  # noqa: E402

SIZE = (1360, 850)
OUT = ROOT / "docs" / "screenshots"


def pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> None:
    app = QApplication([])
    work = Path(tempfile.mkdtemp())
    doc = screenshot_doc.make(work / "Residential lease.pdf")
    OUT.mkdir(parents=True, exist_ok=True)
    signature = sigimage.clean_photo(phone_photo(6), PhotoOptions(ink="blue")).png
    stamp_opts = PhotoOptions(ink="original", auto_straighten=False, keep_frames=True, strength=0.4)
    stamp = sigimage.with_width_mm(sigimage.clean_photo(stamp_photo("box"), stamp_opts).png, 42)
    initials = render_typed("TM", "Caveat", QColor(29, 78, 216))
    for scheme in ("light", "dark"):
        settings = Settings(
            theme=scheme, show_sidebar=True, signature_dir=str(work / f"sigs-{scheme}")
        )
        w = build_window(configure(app, settings), settings, RecentFiles(work / f"r-{scheme}.json"))
        w.resize(*SIZE)
        w.show()
        pump(100)
        lib = w.signatures
        lib.add("signature", signature, True)
        lib.add("initials", initials, True)
        lib.add("stamp", stamp, True)
        w.open_paths([str(doc)])
        pump(300)
        tab = w.current_tab()
        assert tab is not None
        view = tab.view

        # 1. Reading
        view.apply_zoom_mode("fit-width")
        view.go_to_page(0)
        view.indicator.hide()
        pump(500)
        w.grab().save(str(OUT / f"viewer-{scheme}.png"))

        # 2. Fill & Sign
        m, layer = tab.model, view.fill_layer
        assert layer is not None
        for name, value in {
            "landlord": "Pieter van Wyk",
            "tenant": "Thandi Mokoena",
            "address": "12 Kloof Street, Gardens, Cape Town",
            "rent": "R 9 500",
            "start": "1 November 2026",
            "pets": "Yes",
        }.items():
            m.set_field_value(name, value)
        w.set_fill_mode(True)
        pump(300)
        view.apply_zoom_mode("fit-page")
        pump(200)
        layer.set_tool("text")
        text = layer.place(0, QPointF(64, 752))
        text.editor.setPlainText("Cape Town")  # type: ignore[union-attr]
        text.editor.clearFocus()  # type: ignore[union-attr]
        layer.set_tool("")
        layer.arm_image("signature", signature)
        layer.place(0, QPointF(417, 767))
        layer.arm_image("stamp", stamp)
        placed = layer.place(0, QPointF(170, 700))
        placed.rotate_by(-8)  # type: ignore[union-attr]
        layer.set_stamp_opacity(0.85)
        view.indicator.hide()  # no zoom toast in the shot
        pump(500)
        w.grab().save(str(OUT / f"fill-sign-{scheme}.png"))
        w.set_fill_mode(False)
        view.scene().clearSelection()

        # 3. Search
        tab.sidebar.tabs.setCurrentWidget(tab.sidebar.search)
        view.apply_zoom_mode("fit-width")
        tab.open_search()
        QTest.keyClicks(tab.search_bar.field, "deposit")
        tab.search_bar.query_changed.emit("deposit")
        pump(700)
        tab.search.step(1)
        view.indicator.hide()
        pump(400)
        w.grab().save(str(OUT / f"search-{scheme}.png"))
        for t in list(w.tabs):
            w.close_tab(t, ask=False)
        w.close()
        pump(50)
    print("screenshots in", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
