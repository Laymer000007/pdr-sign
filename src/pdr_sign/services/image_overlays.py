"""Signatures, initials and stamps as editable image annotations. Qt-free.

Normal Save writes each one as a Stamp annotation tagged ``/PDR 1`` like the text
items. Its appearance is the image as placed (turned and faded, see sigimage.bake),
so every viewer shows it; the original image, its box, rotation and opacity are kept
next to it (``/PDRImage``, ``/PDRRect``, ``/PDRRotation``, ``/PDROpacity``), so PDR
reopens it as an item you can move, resize, turn or delete.

Save signed copy doesn't use these: it stamps the image into the page content
(``stamps._write_signature``), permanently.
"""

from __future__ import annotations

import io
import re
from typing import Any

import pymupdf
from PIL import Image

from pdr_sign import APP_NAME
from pdr_sign.services import sigimage

_C: Any = pymupdf
LABELS = {"signature": "Signature", "initials": "Initials", "stamp": "Stamp"}
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _turned(png: bytes, degrees: int) -> bytes:
    """``png`` turned counter-clockwise by a multiple of 90°, so that once the page's
    own /Rotate turns it clockwise again it reads upright, as placed."""
    turns = {
        90: Image.Transpose.ROTATE_90,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_270,
    }
    if degrees % 360 not in turns:
        return png
    with Image.open(io.BytesIO(png)) as image:
        out = io.BytesIO()
        image.transpose(turns[degrees % 360]).save(out, "PNG")
        return out.getvalue()


def write_image(
    pdf: pymupdf.Document,
    page: pymupdf.Page,
    kind: str,
    rect: tuple[float, float, float, float],
    png: bytes,
    rotation: float,
    opacity: float,
) -> None:
    x0, y0, x1, y1 = rect
    shown = png
    if rotation % 360 or opacity < 1:
        shown, (w, h) = sigimage.bake(png, x1 - x0, y1 - y0, rotation, opacity)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        box = pymupdf.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    else:
        box = pymupdf.Rect(x0, y0, x1, y1)
    unrotated = box * page.derotation_matrix
    annot = page.add_stamp_annot(unrotated, stamp=_turned(shown, page.rotation))
    annot.set_info(title=APP_NAME, content=LABELS.get(kind, "Signature"))
    annot.update()
    original = pdf.get_new_xref()
    pdf.update_object(original, "<<>>")
    pdf.update_stream(original, png)
    xref = annot.xref
    pdf.xref_set_key(xref, "PDR", "1")
    pdf.xref_set_key(xref, "PDRKind", f"/{kind}")
    pdf.xref_set_key(xref, "PDRImage", f"{original} 0 R")
    pdf.xref_set_key(xref, "PDRRect", "[{:g} {:g} {:g} {:g}]".format(*rect))
    pdf.xref_set_key(xref, "PDRRotation", f"{rotation:g}")
    pdf.xref_set_key(xref, "PDROpacity", f"{opacity:g}")


def read_image(
    pdf: pymupdf.Document, annot: pymupdf.Annot
) -> tuple[tuple[float, float, float, float], bytes, float, float] | None:
    """(rect, original PNG, rotation, opacity) of a PDR image annotation, or None if
    it isn't one PDR can edit (missing or damaged keys)."""
    xref = annot.xref
    kind, value = pdf.xref_get_key(xref, "PDRImage")
    rect_kind, rect_value = pdf.xref_get_key(xref, "PDRRect")
    if kind != "xref" or rect_kind != "array":
        return None
    numbers = [float(n) for n in _NUMBER.findall(rect_value)]
    if len(numbers) != 4:
        return None
    try:
        png = pdf.xref_stream(int(value.split()[0]))
    except (ValueError, RuntimeError):
        return None
    if not png:
        return None
    rotation = _number(pdf, xref, "PDRRotation", 0.0)
    opacity = _number(pdf, xref, "PDROpacity", 1.0)
    x0, y0, x1, y1 = numbers
    return (x0, y0, x1, y1), png, rotation, opacity


def _number(pdf: pymupdf.Document, xref: int, key: str, default: float) -> float:
    kind, value = pdf.xref_get_key(xref, key)
    if kind not in ("int", "real", "float"):
        return default
    try:
        return float(value)
    except ValueError:
        return default
