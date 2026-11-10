"""Normal Save keeps signatures, initials and stamps editable; signed copies don't."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.services import saving, sigimage, stamps
from pdr_sign.services.document import Document
from pdr_sign.services.saving import SaveRequest
from pdr_sign.services.sigimage import PhotoOptions
from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.overlay.signature_item import SignatureGraphic
from pdr_sign.ui.render_scheduler import RenderScheduler
from tests.conftest import make_text_pdf
from tests.sigphoto import phone_photo, stamp_photo


@pytest.fixture(scope="module")
def images() -> dict[str, bytes]:
    signature = sigimage.clean_photo(phone_photo(4), PhotoOptions(ink="blue")).png
    stamp_opts = PhotoOptions(ink="original", auto_straighten=False, keep_frames=True)
    stamp = sigimage.clean_photo(stamp_photo("box"), stamp_opts).png
    return {"signature": signature, "stamp": stamp}


def items_for(images: dict[str, bytes]) -> list[OverlayItem]:
    return [
        OverlayItem("signature", 0, (80, 500, 230, 545), image=images["signature"]),
        OverlayItem("initials", 0, (300, 500, 350, 520), image=images["signature"]),
        OverlayItem(
            "stamp", 0, (300, 600, 420, 660), image=images["stamp"], rotation=-12, opacity=0.7
        ),
    ]


def rotated_pdf(tmp_path: Path, rotation: int) -> Path:
    path = make_text_pdf(tmp_path / f"r{rotation}.pdf", 2)
    with pymupdf.open(path) as pdf:
        for page in pdf:
            page.set_rotation(rotation)
        pdf.saveIncr()
    return path


def key(item: OverlayItem) -> tuple[object, ...]:
    return (
        item.kind,
        item.page,
        tuple(round(v, 3) for v in item.rect),
        item.image,
        item.rotation,
        item.opacity,
    )


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_round_trip_on_every_rotation(
    tmp_path: Path, images: dict[str, bytes], rotation: int
) -> None:
    path = rotated_pdf(tmp_path, rotation)
    items = items_for(images)
    doc = Document.open(path)
    saving.save(doc, path, SaveRequest(items=items))
    doc.close()
    for _ in range(2):  # and again after a second save of what came back
        doc = Document.open(path)
        back = stamps.read_overlays(doc)
        assert sorted(map(key, back)) == sorted(map(key, items))
        with doc.locked() as pdf:
            assert pdf[0].get_images() == []  # not stamped into the page content
            kinds = [a.type[1] for a in pdf[0].annots()]
            assert kinds.count("Stamp") == 3
        saving.save(doc, path, SaveRequest(items=back))
        doc.close()


def test_signed_copy_still_bakes_permanently(tmp_path: Path, images: dict[str, bytes]) -> None:
    path = rotated_pdf(tmp_path, 0)
    doc = Document.open(path)
    target = saving.signed_copy_path(path)
    saving.save(doc, target, SaveRequest(items=items_for(images), flatten=True), overwrite=False)
    doc.close()
    copy = Document.open(target)
    assert stamps.read_overlays(copy) == []
    with copy.locked() as pdf:
        assert len(pdf[0].get_image_info()) == 3
        assert list(pdf[0].annots()) == []
    copy.close()


def test_baked_signatures_from_older_files_still_open(
    tmp_path: Path, images: dict[str, bytes]
) -> None:
    path = rotated_pdf(tmp_path, 90)
    with pymupdf.open(path) as pdf:  # what v1.0.0's normal Save wrote
        pdf[0].insert_image(pymupdf.Rect(80, 500, 230, 545), stream=images["signature"])
        pdf.saveIncr()
    doc = Document.open(path)
    assert stamps.read_overlays(doc) == []
    with doc.locked() as pdf:
        assert len(pdf[0].get_image_info()) == 1
    doc.close()


def test_reopened_signature_is_a_movable_deletable_item(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path, images: dict[str, bytes]
) -> None:
    path = rotated_pdf(tmp_path, 0)
    doc = Document.open(path)
    saving.save(doc, path, SaveRequest(items=items_for(images)[:1]))
    doc.close()
    tab = DocumentTab(Document.open(path), RenderScheduler())
    qtbot.addWidget(tab)
    tab.resize(1000, 900)
    tab.show()
    qtbot.waitExposed(tab)
    view = tab.view
    view.set_zoom(1.0)
    layer = view.fill_layer
    assert layer is not None
    graphic = next(iter(layer.graphics.values()))
    assert isinstance(graphic, SignatureGraphic)
    view.reveal(0, graphic.item.rect)
    QApplication.processEvents()
    centre = graphic.mapToScene(graphic.content_rect().center())
    start = view.mapFromScene(centre)
    end = view.mapFromScene(centre + QPointF(40, 30))
    vp = view.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=start)
    for step in range(1, 9):
        QTest.mouseMove(vp, start + (end - start) * step / 8)
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=end)
    moved = tab.model.items[graphic.item.id].rect
    assert moved[0] == pytest.approx(80 + 40, abs=1.5) and moved[1] == pytest.approx(
        500 + 30, abs=1.5
    )
    assert graphic.isSelected()
    assert layer.delete_selected()
    assert tab.model.items == {}
    tab.close_document()


def test_line_with_fractional_size_keeps_it(tmp_path: Path) -> None:
    path = rotated_pdf(tmp_path, 0)
    doc = Document.open(path)
    line = OverlayItem("line", 0, (80, 300, 200, 300), font_size=13.5)
    saving.save(doc, path, SaveRequest(items=[line]))
    doc.close()
    doc = Document.open(path)
    assert [i.font_size for i in stamps.read_overlays(doc)] == [13.5]
    doc.close()
