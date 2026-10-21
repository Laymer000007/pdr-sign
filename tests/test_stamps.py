from pathlib import Path

import pymupdf
import pytest

from pdr_sign.services import stamps
from pdr_sign.services.document import Document
from pdr_sign.services.stamps import OverlayItem


def save_and_reopen(doc: Document, path: Path) -> Document:
    with doc.locked() as pdf:
        pdf.save(path)
    doc.close()
    return Document.open(path)


def test_overlay_round_trip(text_pdf: Path, tmp_path: Path) -> None:
    doc = Document.open(text_pdf)
    items = [
        OverlayItem("text", 0, (100, 100, 260, 118), text="Hello there", font_size=12),
        OverlayItem("date", 1, (100, 200, 180, 216), text="2026/10/21", color="#1D4ED8"),
        OverlayItem("check", 2, (300, 300, 314, 314), font_size=14),
        OverlayItem("cross", 2, (320, 300, 334, 314), font_size=14),
        OverlayItem("dot", 2, (340, 300, 354, 314), font_size=14),
    ]
    assert stamps.write_overlays(doc, items) == {0, 1, 2}
    again = save_and_reopen(doc, tmp_path / "stamped.pdf")

    # Other viewers see the text in the page.
    with again.locked() as pdf:
        assert "Hello there" in pdf[0].get_text()

    loaded = stamps.read_overlays(again)
    assert [(i.kind, i.page) for i in loaded] == [(i.kind, i.page) for i in items]
    for original, back in zip(items, loaded, strict=True):
        assert back.rect == pytest.approx(original.rect, abs=0.5)
        assert back.font_size == pytest.approx(original.font_size)
        if not original.is_mark:
            assert back.text == original.text
            assert back.color == original.color
    again.close()


def test_read_with_remove_strips_annotations(text_pdf: Path, tmp_path: Path) -> None:
    doc = Document.open(text_pdf)
    stamps.write_overlays(doc, [OverlayItem("text", 0, (100, 100, 200, 118), text="x")])
    again = save_and_reopen(doc, tmp_path / "s.pdf")
    assert len(stamps.read_overlays(again, remove=True)) == 1
    assert stamps.read_overlays(again) == []
    again.close()


def test_foreign_free_text_is_left_alone(text_pdf: Path, tmp_path: Path) -> None:
    src = pymupdf.open(text_pdf)
    src[0].add_freetext_annot(pymupdf.Rect(50, 50, 150, 70), "someone else's note")
    src.save(tmp_path / "foreign.pdf")
    doc = Document.open(tmp_path / "foreign.pdf")
    assert stamps.read_overlays(doc, remove=True) == []
    with doc.locked() as pdf:
        assert len(list(pdf[0].annots())) == 1
    doc.close()


def test_rotated_page_keeps_visible_rect(tmp_path: Path) -> None:
    src = pymupdf.open()
    src.new_page(width=595, height=842).set_rotation(90)
    src.save(tmp_path / "rot.pdf")
    doc = Document.open(tmp_path / "rot.pdf")
    item = OverlayItem("text", 0, (100, 100, 250, 120), text="Upright")
    stamps.write_overlays(doc, [item])
    again = save_and_reopen(doc, tmp_path / "rot2.pdf")
    (back,) = stamps.read_overlays(again)
    assert back.rect == pytest.approx(item.rect, abs=0.5)
    # The text reads left-to-right in the visible orientation.
    with again.locked() as pdf:
        words = pdf[0].get_text("words")
        r = pymupdf.Rect(words[0][:4]) * pdf[0].rotation_matrix
    assert r.width > r.height
    again.close()


def test_clamp_font_size() -> None:
    assert stamps.clamp_font_size(4) == 8
    assert stamps.clamp_font_size(40) == 24
    assert stamps.clamp_font_size(12) == 12
