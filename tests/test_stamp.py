"""Company stamps: cleanup, real size, baking, placement, turning and opacity."""

from __future__ import annotations

import contextlib
import io
import math
from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services import sigimage, stamps
from pdr_sign.services.document import Document
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.services.sigimage import PhotoOptions
from pdr_sign.services.signatures import SignatureStore
from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui import theme
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.stamp_item import StampGraphic
from pdr_sign.ui.stamp_dialog import StampDialog
from pdr_sign.ui.upload_pad import STAMP_OPTIONS
from tests.conftest import trigger_shortcut
from tests.sigphoto import stamp_image, stamp_photo

MM = 72 / 25.4


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def rgba(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGBA")


def box_png(width: int = 600, height: int = 300) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((200, 30, 30, 255), (0, 0, width, 12))
    image.paste((200, 30, 30, 255), (0, 0, 12, height))
    return png_bytes(image)


# --- cleanup ---------------------------------------------------------------------------


def test_stamp_frame_survives_a_tight_crop() -> None:
    tight = png_bytes(stamp_image("box").crop((42, 42, 658, 378)))  # cut into the frame line
    kept = rgba(sigimage.clean_photo(tight, STAMP_OPTIONS).png)
    w, h = kept.size
    left_column = [kept.getpixel((x, h // 2))[3] for x in range(min(20, w))]
    assert max(left_column) == 255  # the outer frame line is still there
    signature_style = PhotoOptions(ink="original")  # border stripping on
    stripped = rgba(sigimage.clean_photo(tight, signature_style).png)
    assert stripped.size != kept.size  # without keep_frames the frame band is lost


def test_stamps_are_not_auto_straightened() -> None:
    tilted = png_bytes(stamp_image("box").rotate(7, expand=True, fillcolor=(240, 238, 232)))
    assert sigimage.clean_photo(tilted, STAMP_OPTIONS).angle == 0.0


def test_original_colours_survive_without_a_fringe() -> None:
    image = rgba(sigimage.clean_photo(stamp_photo("box"), STAMP_OPTIONS).png)
    pixels = list(image.get_flattened_data())
    solid = [p for p in pixels if p[3] == 255]
    reds = [p for p in solid if p[0] > p[2]]
    blues = [p for p in solid if p[2] > p[0]]
    assert reds and blues  # two inks kept apart
    red = [sum(c[i] for c in reds) / len(reds) for i in range(3)]
    blue = [sum(c[i] for c in blues) / len(blues) for i in range(3)]
    assert red[0] > 150 and red[1] < 50 and red[2] < 60
    assert blue[2] > 130 and blue[0] < 70
    # Soft edges carry the ink's colour, not a pale pink mixed with paper.
    edges = [p for p in pixels if 40 < p[3] < 200 and p[0] > p[2]]
    assert edges and sum(p[1] for p in edges) / len(edges) < 80


@pytest.mark.parametrize(("ink", "rgb"), [("red", (200, 30, 30)), ("blue", (29, 78, 216))])
def test_recolour(ink: str, rgb: tuple[int, int, int]) -> None:
    options = PhotoOptions(ink=ink, auto_straighten=False, keep_frames=True)
    image = rgba(sigimage.clean_photo(stamp_photo("round"), options).png)
    assert {p[:3] for p in image.get_flattened_data() if p[3] > 200} == {rgb}


def test_red_ink_meets_contrast_on_paper() -> None:
    assert theme.contrast_ratio("#C81E1E", theme.LIGHT.paper) >= 4.5


def test_real_size_metadata_and_low_res() -> None:
    tagged = sigimage.with_width_mm(box_png(), 32.5)
    assert sigimage.width_mm(tagged) == 32.5
    assert sigimage.width_mm(box_png()) is None
    assert sigimage.is_low_res(box_png(300, 150)) and not sigimage.is_low_res(box_png())


# --- baking -----------------------------------------------------------------------------


def test_bake_is_at_least_600_dpi_at_placed_size() -> None:
    width_pt, height_pt = 40 * MM, 20 * MM
    png, (bw, bh) = sigimage.bake(box_png(), width_pt, height_pt, rotation=30, opacity=0.6)
    image = rgba(png)
    assert image.width / (bw / 72) >= 599  # pixels per inch across the turned box
    assert (bw, bh) == pytest.approx(sigimage.rotated_size(width_pt, height_pt, 30))
    assert max(image.getchannel("A").get_flattened_data()) <= round(255 * 0.6) + 1


def test_bake_caps_very_large_stamps() -> None:
    png, _ = sigimage.bake(box_png(), 300 * MM, 150 * MM, rotation=10)
    assert max(rgba(png).size) <= sigimage.BAKE_MAX_PX + 2


def test_quarter_turn_swaps_the_box() -> None:
    png, (bw, bh) = sigimage.bake(box_png(), 100, 50, rotation=90)
    assert (bw, bh) == pytest.approx((50, 100))
    image = rgba(png)
    assert image.height > image.width


@pytest.mark.parametrize("page_rotation", [0, 90, 180, 270])
def test_turned_faded_stamp_is_written_where_placed(tmp_path: Path, page_rotation: int) -> None:
    src = pymupdf.open()
    src.new_page(width=595, height=842).set_rotation(page_rotation)
    src.save(tmp_path / "blank.pdf")
    doc = Document.open(tmp_path / "blank.pdf")
    item = OverlayItem(
        "stamp", 0, (200, 300, 313.4, 356.7), image=box_png(), rotation=30, opacity=0.7
    )
    stamps.write_overlays(doc, [item])
    with doc.locked() as pdf:
        pdf.save(tmp_path / "stamped.pdf")
    doc.close()
    page = pymupdf.open(tmp_path / "stamped.pdf")[0]
    (info,) = page.get_image_info()
    bbox = pymupdf.Rect(info["bbox"]) * page.rotation_matrix
    w, h = sigimage.rotated_size(113.4, 56.7, 30)
    assert (bbox.x0 + bbox.x1) / 2 == pytest.approx(256.7, abs=0.5)  # centred on the item
    assert (bbox.y0 + bbox.y1) / 2 == pytest.approx(328.35, abs=0.5)
    assert (bbox.width, bbox.height) == pytest.approx((w, h), abs=0.5)


# --- UI ------------------------------------------------------------------------------------


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from pdr_sign.ui import stamp_dialog

    calls: list[str] = []

    def fake(_tokens: object, _parent: object) -> tuple[bytes, bool]:
        calls.append("stamp")
        return sigimage.with_width_mm(box_png(), 32), True

    monkeypatch.setattr(stamp_dialog, "ask_stamp", fake)
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


def open_tab(window: MainWindow, path: Path) -> DocumentTab:
    window.open_paths([str(path)])
    tab = window.current_tab()
    assert tab is not None
    tab.view.set_zoom(1.0)
    tab.view.go_to_page(0)
    return tab


def view_pos(tab: DocumentTab, point: QPointF) -> QPointF:
    view = tab.view
    return QPointF(view.mapFromScene(view.page_items[0].mapToScene(point)))


def drag(tab: DocumentTab, points: list[QPointF], shift: bool = False) -> None:
    vp = tab.view.viewport()
    mod = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    first = view_pos(tab, points[0])
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, mod, first.toPoint())
    for p in points[1:]:
        pos = view_pos(tab, p)
        QApplication.sendEvent(
            vp,
            QMouseEvent(
                QEvent.Type.MouseMove,
                pos,
                QPointF(vp.mapToGlobal(pos)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                mod,
            ),
        )
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, mod, view_pos(tab, points[-1]).toPoint())


def place(tab: DocumentTab, png: bytes, at: QPointF) -> tuple[StampGraphic, OverlayItem]:
    layer = tab.view.fill_layer
    assert layer is not None
    layer.arm_image("stamp", png)
    graphic = layer.place(0, at)
    assert isinstance(graphic, StampGraphic)
    return graphic, tab.model.items[graphic.item.id]


def test_stamp_tool_places_at_real_size(
    window: MainWindow, form_pdf: Path, asked: list[str]
) -> None:
    tab = open_tab(window, form_pdf)
    window.set_fill_mode(True)
    tab.panel._buttons["stamp"].click()
    assert asked == ["stamp"] and len(tab.panel.saved["stamp"].buttons) == 1
    layer = tab.view.fill_layer
    assert layer is not None and layer.tool == "stamp"
    QTest.mouseClick(
        tab.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=view_pos(tab, QPointF(300, 500)).toPoint(),
    )
    (item,) = tab.model.items.values()
    assert item.kind == "stamp"
    assert item.rect[2] - item.rect[0] == pytest.approx(32 * MM)  # the stored real width
    assert ((item.rect[0] + item.rect[2]) / 2, (item.rect[1] + item.rect[3]) / 2) == pytest.approx(
        (300, 500)
    )


def test_default_width_and_no_field_snapping(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    tab.view.go_to_page(1, 650)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.arm_image("stamp", box_png())
    layer.place(1, QPointF(400, 725))  # the middle of the signature field
    (item,) = tab.model.items.values()
    assert item.rect[2] - item.rect[0] == pytest.approx(stamps.STAMP_DEFAULT_MM * MM)
    assert (item.rect[0] + item.rect[2]) / 2 == pytest.approx(400)  # not fitted into it


def test_knob_turns_and_shift_snaps(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    graphic, item = place(tab, box_png(), QPointF(300, 400))
    centre = QPointF(300, 400)
    knob = graphic.mapToParent(graphic._knob().center())
    # Swing the knob from straight up to the right of the centre: a quarter turn.
    radius = centre.y() - knob.y()
    path = [knob] + [
        centre + QPointF(radius * math.sin(math.radians(a)), -radius * math.cos(math.radians(a)))
        for a in range(10, 100, 10)
    ]
    drag(tab, path)
    assert tab.model.items[item.id].rotation == pytest.approx(90, abs=2)
    knob = graphic.mapToParent(graphic._knob().center())
    end = centre + QPointF(
        radius * math.sin(math.radians(97)), -radius * math.cos(math.radians(97))
    )
    drag(tab, [knob, end], shift=True)
    assert tab.model.items[item.id].rotation == pytest.approx(90)  # 97° snaps to 90°
    # Snapping back onto 90° changed nothing, so one undo restores the original angle.
    trigger_shortcut(window, "Ctrl+Z")
    assert tab.model.items[item.id].rotation == 0 and graphic.rotation() == 0


def test_panel_quarter_turns_and_opacity(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    window.set_fill_mode(True)
    graphic, item = place(tab, box_png(), QPointF(300, 400))
    controls = tab.panel.stamp_controls
    assert controls.isVisible()
    controls.turn_left.click()
    assert tab.model.items[item.id].rotation == 270 and controls.angle.text() == "-90°"
    controls.turn_right.click()
    controls.turn_right.click()
    assert tab.model.items[item.id].rotation == 90
    steps = tab.model.undo_stack.count()
    for value in (90, 75, 60):
        controls.opacity.setValue(value)
    assert tab.model.items[item.id].opacity == 0.6
    assert tab.model.undo_stack.count() == steps + 1  # one slider drag, one undo step
    controls.opacity.setValue(20)  # can't go below 50 %
    assert tab.model.items[item.id].opacity == 0.5
    assert graphic.opacity() == pytest.approx(0.5)
    tab.view.scene().clearSelection()
    assert not controls.isVisible()


def test_resize_while_turned_keeps_the_opposite_corner(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    graphic, item = place(tab, box_png(), QPointF(300, 400))
    graphic.rotate_by(30)
    tl = graphic.mapToParent(graphic._corner("tl"))
    br = graphic.mapToParent(graphic._corner("br"))
    outward = br + (br - tl) * 0.25
    drag(tab, [br, br + (outward - br) * 0.5, outward])
    new = tab.model.items[item.id]
    assert graphic.mapToParent(graphic._corner("tl")).toTuple() == pytest.approx(
        tl.toTuple(), abs=0.6
    )
    assert new.rect[2] - new.rect[0] > item.rect[2] - item.rect[0]
    w, h = new.rect[2] - new.rect[0], new.rect[3] - new.rect[1]
    assert w / h == pytest.approx(2.0, rel=0.01)  # aspect kept
    assert new.rotation == 30


def test_turned_stamp_stays_on_the_page(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    graphic, _ = place(tab, box_png(), QPointF(300, 400))
    graphic.rotate_by(45)
    graphic.setPos(QPointF(-500, -500))
    outline = graphic.mapRectToParent(graphic.content_rect())
    assert outline.left() >= -0.01 and outline.top() >= -0.01


# --- dialog --------------------------------------------------------------------------------


def test_stamp_dialog(qtbot: QtBot, qapp: QApplication) -> None:
    configure(qapp, Settings(theme="light"))
    dialog = StampDialog(theme.LIGHT)
    qtbot.addWidget(dialog)
    assert not dialog.use_button.isEnabled()
    assert list(dialog.upload.ink_buttons) == ["original", "red", "blue", "black"]
    assert dialog.upload.ink_buttons["original"].isChecked()
    assert not dialog.upload.auto_button.isVisibleTo(dialog)  # stamps don't auto-straighten
    dialog.upload.load_bytes(stamp_photo("box"))
    qtbot.waitUntil(lambda: dialog.upload.png is not None, timeout=5000)
    assert dialog.use_button.isEnabled() and dialog.warning.isHidden()
    dialog.width_box.set_value(45, emit=True)
    png = dialog.current_png()
    assert png is not None and sigimage.width_mm(png) == 45
    dialog.upload.load_bytes(png_bytes(stamp_image("round").resize((160, 160))))
    qtbot.waitUntil(lambda: not dialog.warning.isHidden(), timeout=5000)
    assert "may print soft" in dialog.warning.text()


def test_store_keeps_stamps_apart(tmp_path: Path) -> None:
    store = SignatureStore(tmp_path)
    store.add("stamp", box_png())
    assert len(store.list("stamp")) == 1 and store.list("signature") == []
