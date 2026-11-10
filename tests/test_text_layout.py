"""services/text_layout follows MuPDF's own appearance streams, case by case."""

from __future__ import annotations

import re

import pymupdf
import pytest

from pdr_sign.services.forms import FieldInfo
from pdr_sign.services.text_layout import (
    ITEM_BASELINE,
    ITEM_INSET_X,
    ITEM_INSET_Y,
    ITEM_LINE,
    field_text_layout,
    item_annotation_rect,
    item_rect_from_annotation,
)

_C = pymupdf
FF_MULTILINE = 1 << 12


def mupdf_layout(
    height: float, value: str, size: float, multiline: bool
) -> tuple[float, float, float]:
    """(font size, left, first baseline from the top) from MuPDF's appearance stream."""
    pdf = pymupdf.open()
    page = pdf.new_page()
    widget = pymupdf.Widget()
    widget.field_type = _C.PDF_WIDGET_TYPE_TEXT  # type: ignore[attr-defined]
    widget.field_name = "f"
    widget.rect = pymupdf.Rect(50, 50, 250, 50 + height)
    widget.text_fontsize = size
    if multiline:
        widget.field_flags = FF_MULTILINE
    page.add_widget(widget)
    widget = next(page.widgets())
    widget.field_value = value
    widget.update()
    xref = int(pdf.xref_get_key(widget.xref, "AP/N")[1].split()[0])
    stream = pdf.xref_stream(xref).decode()
    font = float(re.findall(r"/Helv ([\d.]+) Tf", stream)[0])
    moves = [(float(x), float(y)) for x, y in re.findall(r"([-\d.]+) ([-\d.]+) Td", stream)]
    left = moves[0][0]
    up = sum(y for _, y in moves[: 2 if multiline else 1])  # baseline, from the bottom
    return font, left, height - up


def field(height: float, size: float, multiline: bool) -> FieldInfo:
    return FieldInfo(
        id=1,
        name="f",
        kind="text",
        page=0,
        rect=(50, 50, 250, 50 + height),
        order=0,
        value="",
        flags=FF_MULTILINE if multiline else 0,
        font_size=size,
    )


@pytest.mark.parametrize("height", [12, 16, 20, 24, 30, 40])
@pytest.mark.parametrize("size", [0, 9, 11])
@pytest.mark.parametrize("value", ["Short", "A much longer value that will never fit in the box"])
def test_single_line_fields_match_mupdf(height: float, size: float, value: str) -> None:
    font, left, baseline = mupdf_layout(height, value, size, multiline=False)
    layout = field_text_layout(field(height, size, False), value)
    assert layout.font_size == pytest.approx(font, abs=0.01)
    assert layout.left == pytest.approx(left)
    assert layout.baseline == pytest.approx(baseline, abs=0.01)


@pytest.mark.parametrize("height", [30, 60])
@pytest.mark.parametrize("size", [0, 9, 14])
def test_multi_line_fields_match_mupdf(height: float, size: float) -> None:
    font, left, baseline = mupdf_layout(height, "Two\nlines", size, multiline=True)
    layout = field_text_layout(field(height, size, True), "Two\nlines")
    assert layout.font_size == pytest.approx(font, abs=0.01)
    assert layout.left == pytest.approx(left)
    assert layout.baseline == pytest.approx(baseline, abs=0.01)


@pytest.mark.parametrize("size", [8, 12, 24])
def test_text_items_match_mupdf_freetext(size: float) -> None:
    pdf = pymupdf.open()
    page = pdf.new_page()
    rect = item_annotation_rect((60, 100, 70, 105), "Hg one\nHg two", size)
    annot = page.add_freetext_annot(rect, "Hg one\nHg two", fontsize=size, fontname="Helv")
    annot.update()
    xref = int(pdf.xref_get_key(annot.xref, "AP/N")[1].split()[0])
    stream = pdf.xref_stream(xref).decode()
    moves = [float(y) for _, y in re.findall(r"([-\d.]+) ([-\d.]+) Td", stream)]
    height = rect[3] - rect[1]
    assert height - (moves[0] + moves[1]) == pytest.approx(ITEM_BASELINE * size, abs=0.01)
    assert -moves[2] == pytest.approx(ITEM_LINE * size, abs=0.01)
    # Never narrower than the text (MuPDF would wrap it), and the inset round-trips.
    assert rect[2] - rect[0] >= pymupdf.get_text_length("Hg one", "helv", size)
    assert item_rect_from_annotation(rect)[:2] == (60.0, 100.0)
    assert (rect[0], rect[1]) == (60 + ITEM_INSET_X, 100 + ITEM_INSET_Y)
