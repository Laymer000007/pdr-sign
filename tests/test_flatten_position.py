"""What you see is what "Save signed copy" bakes in: same place, same size.

Two checks at 150 dpi:
- normal save vs signed copy: every page renders the same (antialiasing only), for
  every item type on all four page rotations;
- on screen vs signed copy: the ink of each text item and field value starts where
  PDR drew it (within a point).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.services import saving
from pdr_sign.services.document import Document
from pdr_sign.services.saving import SaveRequest
from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.render_scheduler import RenderScheduler
from tests.conftest import make_form_pdf
from tests.sigphoto import phone_photo

DPI = 150
SCALE = DPI / 72
TOLERANCE_PT = 1.0

Probe = tuple[str, tuple[float, float, float, float]]


def _png() -> bytes:
    from pdr_sign.services import sigimage
    from pdr_sign.services.sigimage import PhotoOptions

    return sigimage.clean_photo(phone_photo(3), PhotoOptions(ink="blue")).png


def _items() -> tuple[list[OverlayItem], list[Probe]]:
    items: list[OverlayItem] = []
    probes: list[Probe] = []
    y = 340.0
    for size in (8.0, 12.0, 16.0, 24.0):
        rect = (60.0, y, 60 + size * 10, y + size * 1.4)
        items.append(OverlayItem("text", 0, rect, text=f"Text {size:g}pt", font_size=size))
        probes.append((f"text {size:g}", (55, y - 8, 60 + size * 7, y + size * 2)))
        y += size * 2.6
    items.append(OverlayItem("text", 0, (60, y, 260, y + 34), text="Line one\nLine two"))
    probes.append(("multi-line text", (55, y - 8, 280, y + 44)))
    y += 54
    items.append(OverlayItem("date", 0, (60, y, 160, y + 17), text="10/11/2026"))
    probes.append(("date", (55, y - 8, 180, y + 24)))
    return items, probes


FIELD_VALUES = {"name": "Ada Lovelace", "notes": "Two\nlines", "code": ""}
FIELD_PROBES: list[Probe] = [
    ("field name (11 pt)", (73, 73, 299, 91)),
    ("field notes (auto)", (73, 101, 299, 159)),
]


def _ink(
    get: Callable[[int, int], int], size: tuple[int, int], rect: tuple[float, ...]
) -> tuple[float, float] | None:
    """Top and left of the dark pixels inside ``rect`` (page points)."""
    x0, y0, x1, y1 = (int(v * SCALE) for v in rect)
    w, h = size
    top = left = None
    for y in range(max(0, y0), min(h, y1)):
        for x in range(max(0, x0), min(w, x1)):
            if get(x, y) < 110:
                top = y if top is None else top
                left = x if left is None else min(left, x)
    if top is None or left is None:
        return None
    return top / SCALE, left / SCALE


def _saved(tmp_path: Path, rotation: int, flatten: bool) -> Path:
    src = tmp_path / f"src-{rotation}.pdf"
    if not src.exists():
        make_form_pdf(src)
        with pymupdf.open(src) as pdf:
            for page in pdf:
                # The fixture's empty signature field carries PyMuPDF's orange "SIGN"
                # tab as its appearance, which MuPDF draws stretched on a turned page
                # until it's baked; real forms' empty signature fields don't have one.
                for widget in list(page.widgets()):
                    if widget.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:  # type: ignore[attr-defined]
                        page.delete_widget(widget)
                page.set_rotation(rotation)
            pdf.saveIncr()
    target = tmp_path / f"{'flat' if flatten else 'normal'}-{rotation}.pdf"
    shutil.copy(src, target)
    items, _ = _items()
    items += [
        OverlayItem("check", 0, (300, 340, 316, 356), font_size=16),
        OverlayItem("cross", 0, (330, 340, 346, 356), font_size=16),
        OverlayItem("dot", 0, (360, 340, 376, 356), font_size=16),
        OverlayItem("line", 0, (300, 380, 420, 380), font_size=12),
        OverlayItem("signature", 0, (300, 420, 450, 465), image=_png()),
        OverlayItem("stamp", 0, (300, 500, 400, 560), image=_png(), rotation=15, opacity=0.8),
    ]
    doc = Document.open(target)
    saving.save(doc, target, SaveRequest(FIELD_VALUES, items, flatten=flatten))
    doc.close()
    return target


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_signed_copy_renders_like_normal_save(tmp_path: Path, rotation: int) -> None:
    normal = _saved(tmp_path, rotation, flatten=False)
    flat = _saved(tmp_path, rotation, flatten=True)
    with pymupdf.open(normal) as a, pymupdf.open(flat) as b:
        assert a.page_count == b.page_count
        for index in range(a.page_count):
            pa = a[index].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            pb = b[index].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            assert (pa.width, pa.height) == (pb.width, pb.height)
            sa, sb = pa.samples, pb.samples
            different = sum(1 for i in range(len(sa)) if abs(sa[i] - sb[i]) > 48)
            assert different <= len(sa) * 0.0005, (index, different)  # antialiasing only


def _screen(tab: DocumentTab) -> QImage:
    """The overlays and field editors as PDR draws them, on white."""
    page = tab.view.page_items[0]
    image = QImage(int(595 * SCALE), int(842 * SCALE), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    tab.view.scene().render(
        painter,
        QRectF(0, 0, image.width(), image.height()),
        page.mapRectToScene(QRectF(0, 0, 595, 842)),
    )
    painter.end()
    return image


def test_on_screen_text_matches_signed_copy(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    from pdr_sign.app import configure
    from pdr_sign.services.settings import Settings

    configure(qapp, Settings(theme="light"))
    normal = _saved(tmp_path, 0, flatten=False)
    flat = _saved(tmp_path, 0, flatten=True)
    doc = Document.open(normal)  # reopened: items and values are live again
    tab = DocumentTab(doc, RenderScheduler())
    qtbot.addWidget(tab)
    tab.resize(1200, 900)
    tab.show()
    qtbot.waitExposed(tab)
    for item in tab.view.page_items:  # hide the PDF raster: compare PDR's own drawing
        item.paint = lambda *_a, **_k: None  # type: ignore[method-assign]
    screen = _screen(tab)
    with pymupdf.open(flat) as pdf:
        pix = pdf[0].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    get_flat = lambda x, y: pix.samples_mv[y * pix.stride + x]  # noqa: E731
    get_screen = lambda x, y: QColor(screen.pixel(x, y)).lightness()  # noqa: E731
    _, probes = _items()
    failures = []
    for name, rect in [*probes, *FIELD_PROBES]:
        on_screen = _ink(get_screen, (screen.width(), screen.height()), rect)
        baked = _ink(get_flat, (pix.width, pix.height), rect)
        assert on_screen is not None and baked is not None, name
        dy, dx = baked[0] - on_screen[0], baked[1] - on_screen[1]
        if abs(dy) > TOLERANCE_PT or abs(dx) > TOLERANCE_PT:
            failures.append(f"{name}: dx {dx:+.2f} pt, dy {dy:+.2f} pt")
    tab.close_document()
    assert not failures, failures
