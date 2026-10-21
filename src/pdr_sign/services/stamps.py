"""Fill & Sign overlay items and how they are written into the PDF. Qt-free.

Text, date and mark items (check, cross, dot) become FreeText annotations
and lines become Line annotations, all tagged ``/PDR 1`` (and ``/PDRKind /<kind>``),
so PDR can reopen them as editable items while every other viewer just shows them.
Signatures and initials are stamped into the page content as images.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import pymupdf

from pdr_sign.services.document import Document
from pdr_sign.services.text import Rect

# PyMuPDF defines its constants at import time; its type stubs don't list them.
_C: Any = pymupdf

OverlayKind = Literal["text", "date", "initials", "check", "cross", "dot", "line", "signature"]
MARK_KINDS: tuple[OverlayKind, ...] = ("check", "cross", "dot")
TEXT_KINDS: tuple[OverlayKind, ...] = ("text", "date")
IMAGE_KINDS: tuple[OverlayKind, ...] = ("signature", "initials")
LINE_LENGTH = 40.0  # points, for a line placed with a plain click

# ZapfDingbats glyphs, available in every PDF viewer without embedding a font.
MARK_GLYPHS = {"check": "4", "cross": "8", "dot": "l"}

DEFAULT_FONT_SIZE = 12.0
MIN_FONT_SIZE, MAX_FONT_SIZE = 8.0, 24.0
TEXT_COLORS = {"black": "#000000", "blue": "#1D4ED8"}


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class OverlayItem:
    kind: OverlayKind
    page: int
    rect: Rect  # visible page coordinates (points)
    text: str = ""
    font_size: float = DEFAULT_FONT_SIZE
    color: str = TEXT_COLORS["black"]
    id: str = field(default_factory=new_id)
    image: bytes | None = None  # signature / initials PNG (transparent, trimmed)

    # For a line, ``rect`` holds its two end points (x1, y1, x2, y2) as drawn, not a
    # normalised box: the direction matters for the end-point handles.

    def moved_to(self, rect: Rect) -> OverlayItem:
        return replace(self, rect=rect)

    @property
    def is_mark(self) -> bool:
        return self.kind in MARK_KINDS

    @property
    def is_image(self) -> bool:
        return self.kind in IMAGE_KINDS


def line_width(size: float) -> float:
    """Stroke width for a line drawn at text size ``size``: 0.75 pt at 8, 3 pt at 24."""
    size = clamp_font_size(size)
    return round(0.75 + (size - MIN_FONT_SIZE) * 2.25 / (MAX_FONT_SIZE - MIN_FONT_SIZE), 3)


def clamp_font_size(size: float) -> float:
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return r, g, b


def _hex(rgb: object) -> str:
    if not isinstance(rgb, list | tuple) or len(rgb) < 3:
        return TEXT_COLORS["black"]
    return "#{:02X}{:02X}{:02X}".format(*(round(float(c) * 255) for c in rgb[:3]))


def write_overlays(doc: Document, items: list[OverlayItem]) -> set[int]:
    """Add the text/mark items to the in-memory PDF. Returns the pages touched."""
    pages: set[int] = set()
    with doc.locked() as pdf:
        for item in items:
            page = pdf[item.page]
            if item.kind in IMAGE_KINDS:
                _write_signature(page, item)
                pages.add(item.page)
                continue
            if item.kind == "line":
                _write_line(pdf, page, item)
                pages.add(item.page)
                continue
            rect = pymupdf.Rect(item.rect) * page.derotation_matrix
            if item.is_mark:
                text, font = MARK_GLYPHS[item.kind], "ZaDb"
            else:
                text, font = item.text, "Helv"
            annot = page.add_freetext_annot(
                rect,
                text,
                fontsize=item.font_size,
                fontname=font,
                text_color=_rgb(item.color),
                fill_color=None,
                rotate=page.rotation,
                align=_C.TEXT_ALIGN_CENTER if item.is_mark else _C.TEXT_ALIGN_LEFT,
            )
            annot.set_border(width=0)
            annot.set_info(title="PDR", content=text)
            annot.update()
            pdf.xref_set_key(annot.xref, "PDR", "1")
            pdf.xref_set_key(annot.xref, "PDRKind", f"/{item.kind}")
            pages.add(item.page)
    doc.invalidate_render()
    return pages


def _write_signature(page: pymupdf.Page, item: OverlayItem) -> None:
    """Stamp a signature image into the page content. Permanent, like other Fill & Sign
    tools: it is not an annotation and does not reopen as an editable item."""
    if not item.image:
        return
    rect = pymupdf.Rect(item.rect) * page.derotation_matrix
    # ``rotate`` turns the image with the page so it reads upright as displayed.
    page.insert_image(
        rect, stream=item.image, keep_proportion=True, overlay=True, rotate=page.rotation
    )


def _write_line(pdf: pymupdf.Document, page: pymupdf.Page, item: OverlayItem) -> None:
    x1, y1, x2, y2 = item.rect
    m = page.derotation_matrix
    annot = page.add_line_annot(pymupdf.Point(x1, y1) * m, pymupdf.Point(x2, y2) * m)
    annot.set_border(width=line_width(item.font_size))
    annot.set_colors(stroke=_rgb(item.color))
    annot.set_info(title="PDR")
    annot.update()
    pdf.xref_set_key(annot.xref, "PDR", "1")
    pdf.xref_set_key(annot.xref, "PDRKind", "/line")
    pdf.xref_set_key(annot.xref, "PDRSize", f"{item.font_size:g}")


def _read_line(
    pdf: pymupdf.Document, page: pymupdf.Page, annot: pymupdf.Annot, index: int
) -> OverlayItem | None:
    vertices = annot.vertices or []
    if len(vertices) < 2:
        return None
    (x1, y1), (x2, y2) = (pymupdf.Point(v) * page.rotation_matrix for v in vertices[:2])
    size_kind, size = pdf.xref_get_key(annot.xref, "PDRSize")
    stroke = (annot.colors or {}).get("stroke")
    return OverlayItem(
        kind="line",
        page=index,
        rect=(x1, y1, x2, y2),
        font_size=float(size) if size_kind in ("int", "real") else DEFAULT_FONT_SIZE,
        color=_hex(stroke),
    )


def read_overlays(doc: Document, remove: bool = False) -> list[OverlayItem]:
    """PDR-tagged annotations as editable items; ``remove`` deletes them from memory.

    Removing lets the UI show them as live overlays instead of baked-in pixels; they
    are written again on save.
    """
    items: list[OverlayItem] = []
    with doc.locked() as pdf:
        for index in range(pdf.page_count):
            page = pdf[index]
            doomed = []
            for annot in page.annots(types=[_C.PDF_ANNOT_FREE_TEXT, _C.PDF_ANNOT_LINE]):
                if pdf.xref_get_key(annot.xref, "PDR")[1] != "1":
                    continue
                kind = pdf.xref_get_key(annot.xref, "PDRKind")[1].lstrip("/")
                if kind == "line":
                    line = _read_line(pdf, page, annot, index)
                    if line is not None:
                        items.append(line)
                        doomed.append(annot)
                    continue
                if kind not in (*TEXT_KINDS, *MARK_KINDS):
                    continue
                r = annot.rect * page.rotation_matrix
                info = annot.info
                da = _parse_da(pdf.xref_get_key(annot.xref, "DA")[1])
                items.append(
                    OverlayItem(
                        kind=kind,
                        page=index,
                        rect=(r.x0, r.y0, r.x1, r.y1),
                        text="" if kind in MARK_KINDS else info.get("content", ""),
                        font_size=da[0] or DEFAULT_FONT_SIZE,
                        color=da[1],
                    )
                )
                doomed.append(annot)
            if remove:
                for annot in doomed:
                    page.delete_annot(annot)
    if remove:
        doc.invalidate_render()
    return items


def _parse_da(da: str) -> tuple[float, str]:
    """Font size and colour from a default-appearance string like ``0 0 1 rg /Helv 12 Tf``."""
    tokens = da.replace("(", " ").replace(")", " ").split()
    size, color = 0.0, TEXT_COLORS["black"]
    for i, token in enumerate(tokens):
        if token == "Tf" and i >= 1:
            with contextlib.suppress(ValueError):
                size = float(tokens[i - 1])
        if token == "rg" and i >= 3:
            with contextlib.suppress(ValueError):
                color = _hex([float(t) for t in tokens[i - 3 : i]])
    return size, color
