"""Canvas helpers kept out of canvas.py: hit tests, click to type, ending
interactions, search highlights."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QGraphicsItem

from pdr_sign.services.search import SearchHit
from pdr_sign.ui.overlay.base import OverlayGraphic
from pdr_sign.ui.overlay.field_paint import SignHere
from pdr_sign.ui.overlay.field_widgets import FieldProxy, ToggleField
from pdr_sign.ui.overlay.text_item import TextGraphic

if TYPE_CHECKING:
    from pdr_sign.ui.canvas import Canvas


def overlay_at(canvas: Canvas, pos: QPoint) -> OverlayGraphic | None:
    """The placed Fill & Sign item under ``pos`` (or whose text is), if any."""
    item = canvas.itemAt(pos)
    while item is not None and not isinstance(item, OverlayGraphic):
        item = item.parentItem()
    return item


def field_at(canvas: Canvas, pos: QPoint) -> QGraphicsItem | None:
    """The form-field editor or "Sign here" box under ``pos``, if any."""
    item = canvas.itemAt(pos)
    while item is not None and not isinstance(item, FieldProxy | ToggleField | SignHere):
        item = item.parentItem()
    return item


def type_at(canvas: Canvas, pos: QPoint) -> None:
    """A plain click on empty page space (no word, link, field or item under it):
    open Fill & Sign and start typing right there, as with the Text tool."""
    hit = canvas._page_point(pos)
    layer = canvas.fill_layer
    if hit is None or layer is None or layer.tool:
        return
    page, local = hit
    if not canvas.page_items[page].page_rect().contains(local) or canvas._over_text(pos):
        return
    if canvas.itemAt(pos) is not canvas.page_items[page]:
        return  # a field, item or "Sign here" box is there
    canvas.fill_requested.emit()
    layer.set_tool("text")
    layer.place(page, local)


def release_interaction(canvas: Canvas) -> None:
    """End everything in progress in ``canvas``: a drag (keeping the move), the mouse
    grab, typing in a text item, a half-drawn line, a page-text press, and the item
    selection. Called when the tab is left, the window is deactivated, or the Fill &
    Sign panel closes, so nothing stays stuck where the matching mouse release or
    focus change will never arrive."""
    scene = canvas.scene()
    grabber = scene.mouseGrabberItem()
    if isinstance(grabber, OverlayGraphic):
        grabber.end_drag()
    elif grabber is not None:
        grabber.ungrabMouse()
    layer = canvas.fill_layer
    if layer is not None:
        for graphic in list(layer.graphics.values()):
            if isinstance(graphic, TextGraphic):
                graphic.end_editing()
        if layer.draft is not None:
            draft, layer.draft = layer.draft, None
            layer.graphics.pop(draft.item.id, None)
            if draft.scene() is not None:
                draft.scene().removeItem(draft)
    canvas.reset_press()
    scene.clearSelection()


def set_search_hits(canvas: Canvas, hits: list[SearchHit]) -> None:
    by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for hit in hits:
        by_page.setdefault(hit.page, []).append(hit.rect)
    for page in canvas._search_pages | set(by_page):
        item = canvas.page_items[page]
        item.search_rects = by_page.get(page, [])
        item.update()
    canvas._search_pages = set(by_page)


def set_current_hit(canvas: Canvas, hit: SearchHit | None) -> None:
    if canvas._current_hit is not None:
        old = canvas.page_items[canvas._current_hit.page]
        old.current_hit = None
        old.update()
    canvas._current_hit = hit
    if hit is not None:
        item = canvas.page_items[hit.page]
        item.current_hit = hit.rect
        item.update()
        canvas.reveal(hit.page, hit.rect)
