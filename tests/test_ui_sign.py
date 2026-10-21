"""Phase 4: signature dialog, library, placement and snapping."""

from __future__ import annotations

import contextlib
import io
import math
import random
from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services import stamps
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.services.signatures import SignatureStore
from pdr_sign.ui import theme
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.draw_pad import smooth
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.signature_item import SignatureGraphic
from pdr_sign.ui.signature_dialog import SignatureDialog
from pdr_sign.ui.signature_library import SignatureLibrary
from tests.sigphoto import phone_photo


def png_of(width: int, height: int) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((0, 0, 0, 255), (0, height // 2 - 2, width, height // 2 + 2))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


SIG = png_of(400, 100)  # 4:1


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stand-in for the modal dialog: returns SIG, remembered."""
    from pdr_sign.ui import signature_dialog

    calls: list[str] = []

    def fake(kind: str, _tokens: object, _parent: object) -> tuple[bytes, bool]:
        calls.append(kind)
        return SIG, True

    monkeypatch.setattr(signature_dialog, "ask_signature", fake)
    return calls


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    settings = Settings(theme="light", signature_dir=str(tmp_path / "sigs"))
    w = build_window(configure(qapp, settings), settings, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.resize(1100, 800)
    w.show()
    qtbot.waitExposed(w)
    w.activateWindow()
    with contextlib.suppress(qtbot.TimeoutError):
        qtbot.waitUntil(w.isActiveWindow, timeout=1000)
    yield w
    for tab in list(w.tabs):
        w.close_tab(tab)


def open_tab(window: MainWindow, path: Path, zoom: float = 1.0) -> DocumentTab:
    window.open_paths([str(path)])
    tab = window.current_tab()
    assert tab is not None
    tab.view.set_zoom(zoom)
    tab.view.go_to_page(0)
    return tab


def click_page(tab: DocumentTab, page: int, point: QPointF) -> None:
    view = tab.view
    pos = view.mapFromScene(view.page_items[page].mapToScene(point))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)


def centre(rect: tuple[float, float, float, float]) -> tuple[float, float]:
    return (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2


# --- dialog --------------------------------------------------------------------------


def scribble(dialog: SignatureDialog, jitter: float = 0.0) -> None:
    pad = dialog.draw
    r = pad._canvas_rect()
    rng = random.Random(1)
    points = [
        QPointF(
            r.left() + r.width() * (0.1 + 0.8 * k / 120),
            r.top() + r.height() * (0.5 + 0.15 * math.sin(k / 8)),
        )
        for k in range(121)
    ]
    QTest.mousePress(pad, Qt.MouseButton.LeftButton, pos=points[0].toPoint())
    for p in points[1:]:
        noisy = p + QPointF(rng.uniform(-jitter, jitter), rng.uniform(-jitter, jitter))
        QTest.mouseMove(pad, noisy.toPoint(), 4)
    QTest.mouseRelease(pad, Qt.MouseButton.LeftButton, pos=points[-1].toPoint())


def test_draw_tab_strokes_undo_clear_and_export(qtbot: QtBot, qapp: QApplication) -> None:
    configure(qapp, Settings(theme="light"))
    dialog = SignatureDialog("signature", theme.LIGHT)
    qtbot.addWidget(dialog)
    dialog.resize(820, 560)
    dialog.show()
    assert not dialog.use_button.isEnabled()
    assert dialog.remember_box.isChecked()
    scribble(dialog)
    scribble(dialog)
    assert len(dialog.draw.strokes) == 2 and dialog.use_button.isEnabled()
    dialog.undo_button.click()
    assert len(dialog.draw.strokes) == 1
    png = dialog.current_png()
    assert png is not None
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    assert image.getpixel((0, 0))[3] == 0  # transparent
    assert image.width > 3 * image.height  # trimmed to the wide scribble
    dialog.ink_buttons["blue"].click()
    blue = Image.open(io.BytesIO(dialog.current_png() or b"")).convert("RGBA")
    assert max(p[2] for p in blue.get_flattened_data() if p[3] > 200) > 150
    dialog.clear_button.click()
    assert dialog.draw.is_empty and not dialog.use_button.isEnabled()


def test_touchpad_jitter_is_smoothed(qtbot: QtBot, qapp: QApplication) -> None:
    configure(qapp, Settings(theme="light"))
    dialog = SignatureDialog("signature", theme.LIGHT)
    qtbot.addWidget(dialog)
    dialog.resize(820, 560)
    dialog.show()
    scribble(dialog, jitter=3.0)
    points = dialog.draw.strokes[0].points

    def wiggle(pts: list[QPointF]) -> float:
        """Mean size of direction changes: small for a smooth curve."""
        total = 0.0
        for a, b, c in zip(pts, pts[1:], pts[2:], strict=False):
            ab, bc = b - a, c - b
            total += abs(
                math.atan2(ab.x() * bc.y() - ab.y() * bc.x(), ab.x() * bc.x() + ab.y() * bc.y())
            )
        return total / max(1, len(pts) - 2)

    assert wiggle(points) < 0.25  # radians; raw ±3 px jitter is far rougher


def test_smooth_keeps_ends() -> None:
    pts = [QPointF(x, (x % 2) * 4) for x in range(10)]
    out = smooth(pts)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert max(p.y() for p in out[2:-2]) < 3


def test_type_tab(qtbot: QtBot, qapp: QApplication) -> None:
    configure(qapp, Settings(theme="light"))
    dialog = SignatureDialog("initials", theme.LIGHT)
    qtbot.addWidget(dialog)
    dialog.tabs.setCurrentIndex(1)
    assert dialog.type.name.placeholderText() == "Your initials"
    assert not dialog.use_button.isEnabled()
    QTest.keyClicks(dialog.type.name, "JN")
    assert dialog.use_button.isEnabled()
    caveat = dialog.current_png()
    dialog.type.tiles["Dancing Script"].click()
    dancing = dialog.current_png()
    assert caveat and dancing and caveat != dancing


def test_upload_tab_cleans_a_phone_photo(qtbot: QtBot, qapp: QApplication) -> None:
    configure(qapp, Settings(theme="light"))
    dialog = SignatureDialog("signature", theme.LIGHT)
    qtbot.addWidget(dialog)
    dialog.tabs.setCurrentIndex(2)
    pad = dialog.upload
    pad.load_bytes(phone_photo(angle=6))
    qtbot.waitUntil(lambda: pad.png is not None, timeout=5000)
    assert dialog.use_button.isEnabled()
    assert pad.angle_label.text().startswith("Auto +6") or pad.angle_label.text().startswith(
        "Auto +5"
    )
    first = pad.png
    pad.rotate_right.click()
    pad.wait_idle()
    qtbot.waitUntil(lambda: pad.png != first, timeout=5000)
    pad.load_bytes(b"not an image")
    assert "isn't an image" in pad.status.text()


# --- library ----------------------------------------------------------------------------


def test_library_remember_and_session(tmp_path: Path, qapp: QApplication) -> None:
    library = SignatureLibrary(SignatureStore(tmp_path))
    saved = library.add("signature", SIG, remember=True)
    once = library.add("signature", png_of(200, 50), remember=False)
    assert [i.id for i in library.items("signature")] == [once.id, saved.id]
    assert len(list(tmp_path.glob("signature-*.png"))) == 1  # the session one isn't on disk
    fresh = SignatureLibrary(SignatureStore(tmp_path))
    assert [i.id for i in fresh.items("signature")] == [saved.id]
    library.remove("signature", once.id)
    library.remove("signature", saved.id)
    assert library.items("signature") == []


# --- placement ---------------------------------------------------------------------------


def test_first_signature_opens_dialog_then_places(
    window: MainWindow, text_pdf: Path, asked: list[str]
) -> None:
    tab = open_tab(window, text_pdf)
    window.set_fill_mode(True)
    tab.panel._buttons["signature"].click()
    assert asked == ["signature"]
    layer = tab.view.fill_layer
    assert layer is not None and layer.tool == "signature"
    assert tab.panel._buttons["signature"].isChecked()
    assert len(tab.panel.saved["signature"].buttons) == 1  # remembered, shown in the panel

    click_page(tab, 0, QPointF(250, 400))
    (item,) = tab.model.items.values()
    assert item.kind == "signature" and item.image == SIG
    assert centre(item.rect) == pytest.approx((250, 400), abs=1)
    assert item.rect[2] - item.rect[0] == pytest.approx(150)
    assert item.rect[3] - item.rect[1] == pytest.approx(37.5)  # aspect kept
    assert layer.tool == ""  # one-shot

    tab.panel._buttons["signature"].click()  # now there's one: no dialog, just arm it
    assert asked == ["signature"] and layer.tool == "signature"


@pytest.mark.parametrize("zoom", [0.75, 1.5, 3.0])
def test_placement_is_zoom_independent(
    window: MainWindow, text_pdf: Path, tmp_path: Path, zoom: float
) -> None:
    tab = open_tab(window, text_pdf, zoom=zoom)
    tab.view.go_to_page(1, 250)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.arm_image("signature", SIG)
    click_page(tab, 1, QPointF(200, 300))
    (item,) = tab.model.items.values()
    assert item.page == 1
    assert centre(item.rect) == pytest.approx((200, 300), abs=1.5 / zoom + 0.5)
    stamps.write_overlays(tab.doc, [item])
    with tab.doc.locked() as pdf:
        pdf.save(tmp_path / "signed.pdf")
    (info,) = pymupdf.open(tmp_path / "signed.pdf")[1].get_image_info()
    assert tuple(info["bbox"]) == pytest.approx(item.rect, abs=0.5)


def test_snaps_into_signature_field(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    tab.view.go_to_page(1, 650)
    layer = tab.view.fill_layer
    assert layer is not None
    (field,) = layer.sign_fields  # page 2, (300, 700, 500, 750)
    layer.arm_image("signature", SIG)
    click_page(tab, 1, QPointF(320, 690))  # just above the field's top-left corner
    (item,) = tab.model.items.values()
    fx0, fy0, fx1, fy1 = field.rect
    x0, y0, x1, y1 = item.rect
    assert fx0 <= x0 and x1 <= fx1 and fy0 <= y0 and y1 <= fy1  # inside the field
    assert centre(item.rect) == pytest.approx(centre(field.rect), abs=0.5)
    assert (x1 - x0) / (y1 - y0) == pytest.approx(4.0, rel=0.01)


def test_drop_near_field_snaps_but_resize_inside_does_not(
    window: MainWindow, form_pdf: Path
) -> None:
    tab = open_tab(window, form_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.arm_image("signature", SIG)
    click_page(tab, 1, QPointF(150, 400))  # far from the field
    (item,) = tab.model.items.values()
    graphic = layer.graphics[item.id]
    assert isinstance(graphic, SignatureGraphic)
    graphic.setPos(QPointF(330, 705))  # dragged roughly onto the field
    graphic.commit()
    snapped = tab.model.items[item.id]
    assert centre(snapped.rect) == pytest.approx((400, 725), abs=0.5)

    graphic._resizing = "br"  # as during a handle drag
    graphic.set_size(80, 20)
    graphic.commit()
    graphic._resizing = None
    resized = tab.model.items[item.id]
    assert resized.rect[2] - resized.rect[0] == pytest.approx(80)


def test_saved_strip_picks_and_deletes(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    window.set_fill_mode(True)
    window.signatures.add("initials", png_of(120, 60), remember=True)
    strip = tab.panel.saved["initials"]
    assert len(strip.buttons) == 1
    strip.buttons[0].click()
    layer = tab.view.fill_layer
    assert layer is not None and layer.tool == "initials"
    click_page(tab, 0, QPointF(300, 300))
    (item,) = tab.model.items.values()
    assert item.kind == "initials" and item.rect[2] - item.rect[0] == pytest.approx(56)
    (saved,) = window.signatures.items("initials")
    strip.delete_requested.emit("initials", saved.id)
    assert strip.buttons == [] and window.signatures.items("initials") == []


def test_clicking_sign_here_signs_into_the_field(
    window: MainWindow, form_pdf: Path, asked: list[str]
) -> None:
    tab = open_tab(window, form_pdf)
    tab.view.go_to_page(1, 650)
    layer = tab.view.field_layer
    assert layer is not None
    (hint,) = layer.sign_here
    click_page(tab, 1, QPointF(400, 725))  # the middle of the field
    assert asked == ["signature"]  # no signature yet: the dialog was asked for one
    (item,) = tab.model.items.values()
    assert centre(item.rect) == pytest.approx(centre(hint.field.rect), abs=0.5)
    # Clicking the field again hits the signature on top of the hint: it's selected,
    # not signed twice.
    tab.view.scene().clearSelection()
    click_page(tab, 1, QPointF(400, 725))
    assert len(tab.model.items) == 1 and asked == ["signature"]
    fill = tab.view.fill_layer
    assert fill is not None and fill.graphics[item.id].isSelected()
