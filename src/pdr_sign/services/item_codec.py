"""Fill & Sign items on the clipboard. Qt-free.

Copied items travel as JSON under their own MIME type, so a paste works across pages,
tabs, windows and even after PDR Sign restarts. Every pasted item gets a new id;
size, rotation, colour, opacity and the image itself are kept.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from typing import Any

from pdr_sign.services.stamps import OverlayItem, OverlayKind, new_id

MIME = "application/x-pdr-sign-items"
_KINDS = {"text", "date", "initials", "check", "cross", "dot", "line", "signature", "stamp"}
Rect = tuple[float, float, float, float]


def encode(items: list[OverlayItem]) -> bytes:
    data = [
        {
            "kind": i.kind,
            "page": i.page,
            "rect": list(i.rect),
            "text": i.text,
            "font_size": i.font_size,
            "color": i.color,
            "rotation": i.rotation,
            "opacity": i.opacity,
            "image": base64.b64encode(i.image).decode("ascii") if i.image else None,
        }
        for i in items
    ]
    return json.dumps({"version": 1, "items": data}).encode("utf-8")


def decode(blob: bytes) -> list[OverlayItem]:
    """Items from the clipboard (fresh ids), or [] if it isn't something we wrote."""
    try:
        data = json.loads(blob.decode("utf-8"))
        return [_item(raw) for raw in data["items"]]
    except (ValueError, KeyError, TypeError, AttributeError):
        return []


def _item(raw: dict[str, Any]) -> OverlayItem:
    kind = str(raw["kind"])
    if kind not in _KINDS:
        raise ValueError(kind)
    x0, y0, x1, y1 = (float(v) for v in raw["rect"])
    image = raw.get("image")
    return OverlayItem(
        kind=kind,  # type: ignore[arg-type]
        page=int(raw["page"]),
        rect=(x0, y0, x1, y1),
        text=str(raw.get("text", "")),
        font_size=float(raw.get("font_size", 12.0)),
        color=str(raw.get("color", "#000000")),
        image=base64.b64decode(image) if image else None,
        rotation=float(raw.get("rotation", 0.0)),
        opacity=float(raw.get("opacity", 1.0)),
    )


def bounds(items: list[OverlayItem]) -> Rect:
    """The box around all ``items`` (a line's rect holds its end points, any order)."""
    xs = [v for i in items for v in (i.rect[0], i.rect[2])]
    ys = [v for i in items for v in (i.rect[1], i.rect[3])]
    return min(xs), min(ys), max(xs), max(ys)


def placed(
    items: list[OverlayItem], page: int, dx: float, dy: float, page_size: tuple[float, float]
) -> list[OverlayItem]:
    """Copies of ``items`` on ``page``, moved by (dx, dy) and kept on the page as a
    group (its layout unchanged), each with a new id."""
    if not items:
        return []
    x0, y0, x1, y1 = bounds(items)
    width, height = page_size
    dx = min(max(dx, -x0), width - x1) if x1 - x0 <= width else -x0
    dy = min(max(dy, -y0), height - y1) if y1 - y0 <= height else -y0
    return [
        replace(
            i,
            id=new_id(),
            page=page,
            rect=(i.rect[0] + dx, i.rect[1] + dy, i.rect[2] + dx, i.rect[3] + dy),
        )
        for i in items
    ]


def kind_of(value: str) -> OverlayKind:
    """``value`` as an item kind (for text and image items made from other apps)."""
    if value not in _KINDS:
        raise ValueError(value)
    return value  # type: ignore[return-value]
