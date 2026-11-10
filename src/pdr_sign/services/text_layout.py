"""Where MuPDF puts text when it draws a saved item or a form-field value. Qt-free.

The canvas draws text with Qt and the saved file with MuPDF, and the two lay text out
differently (a different Helvetica substitute, different line spacing, padding). So
the canvas doesn't use Qt's own layout: it puts every baseline where MuPDF will,
using these rules (taken from MuPDF's appearance streams and checked against them by
``tests/test_text_layout.py``). What you see is then what Save and Save signed copy
write.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from pdr_sign.services.forms import FieldInfo

# Fill & Sign text and date items (FreeText annotations).
ITEM_BASELINE = 0.8  # first baseline below the annotation's top, x font size
ITEM_LINE = 1.2  # line spacing, x font size
# The item's box on the canvas has a little padding around the text; the annotation
# written to the PDF starts that much further in, so the text lands where it was drawn.
ITEM_INSET_X = 2.0
ITEM_INSET_Y = 1.0

# Form-field values (widget appearances).
FIELD_LEFT = 2.0  # points from the field's left edge
FIELD_LINE = 1.116  # multi-line spacing, x font size
FIELD_MULTILINE_AUTO = 12.0  # MuPDF's size for an "auto" multi-line field
FIELD_SINGLE_GAP = 4.0  # an "auto" single-line field is this much shorter than the box


def text_width(text: str, size: float) -> float:
    """Width of ``text`` in Helvetica at ``size`` points (as MuPDF measures it)."""
    return float(pymupdf.get_text_length(text, fontname="helv", fontsize=size))


@dataclass(frozen=True)
class FieldTextLayout:
    font_size: float
    left: float  # points from the field's left edge to the text
    baseline: float  # points from the field's top edge to the first baseline
    line_height: float


def field_text_layout(field: FieldInfo, value: str) -> FieldTextLayout:
    """How MuPDF draws ``value`` in a text or dropdown field."""
    x0, y0, x1, y1 = field.rect
    width, height = x1 - x0, y1 - y0
    if field.multiline:
        size = field.font_size or FIELD_MULTILINE_AUTO
        return FieldTextLayout(size, FIELD_LEFT, FIELD_LEFT + FIELD_LINE * size, FIELD_LINE * size)
    size = field.font_size
    if size <= 0:  # auto: as tall as the box allows, smaller if the text is too wide
        size = height - FIELD_SINGLE_GAP
        unit = text_width(value, 1.0) if value else 0.0
        if unit > 0:
            size = min(size, (width - FIELD_SINGLE_GAP) / unit)
    # MuPDF centres the line on the box: baseline (h - size) / 2 + 0.2 x size up from
    # the bottom, i.e. h / 2 + 0.3 x size down from the top.
    return FieldTextLayout(size, FIELD_LEFT, height / 2 + 0.3 * size, FIELD_LINE * size)


def item_annotation_rect(
    rect: tuple[float, float, float, float], text: str, size: float
) -> tuple[float, float, float, float]:
    """The FreeText rectangle for a text item drawn in ``rect`` on the canvas: inset
    like the canvas text, and never too small (MuPDF wraps or clips text that is)."""
    x0, y0, x1, y1 = rect
    lines = text.split("\n") or [""]
    need_w = max(text_width(line, size) for line in lines) + 1.0
    need_h = ITEM_LINE * size * len(lines)
    left, top = x0 + ITEM_INSET_X, y0 + ITEM_INSET_Y
    return (left, top, max(x1, left + need_w), max(y1, top + need_h))


def item_rect_from_annotation(
    rect: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """The canvas box for a FreeText rectangle read back from a file."""
    x0, y0, x1, y1 = rect
    return (x0 - ITEM_INSET_X, y0 - ITEM_INSET_Y, x1, y1)
