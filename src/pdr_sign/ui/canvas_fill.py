"""Canvas helpers kept out of canvas.py: hit tests, click to type, ending
interactions, search highlights."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent, QKeyEvent
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView, QMenu

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


# Shift or Ctrl with a click or a rubber band adds to the selection.
ADD_MODIFIERS = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier


def context_menu(canvas: Canvas, event: QContextMenuEvent) -> None:
    """Placed item under the pointer: Copy / Cut / Paste / Duplicate / Delete.
    Elsewhere: copy page text, select the page's text, and Paste."""
    pos = event.pos()
    if overlay_at(canvas, pos) is not None:
        canvas.item_actions.menu(pos).exec(event.globalPos())
        return
    hit = canvas._page_point(pos)
    menu = QMenu(canvas)
    copy = menu.addAction("Copy")
    copy.setShortcut("Ctrl+C")
    copy.setEnabled(not canvas.selection.is_empty)
    copy.triggered.connect(canvas.copy_selection)
    paste = menu.addAction("Paste")
    paste.setShortcut("Ctrl+V")
    paste.setEnabled(canvas.fill_layer is not None and canvas.item_actions.can_paste())
    paste.triggered.connect(lambda: canvas.item_actions.paste(pos))
    if hit is not None:
        page = hit[0]
        select = menu.addAction("Select page text")
        select.triggered.connect(lambda: canvas.selection.select_page(page))
    menu.exec(event.globalPos())


def copy_any(canvas: Canvas) -> bool:
    """Ctrl+C: the words selected while typing in an item, else the selected items,
    else the selected page text."""
    focus = canvas.scene().focusItem()
    parent = focus.parentItem() if focus is not None else None
    if isinstance(parent, TextGraphic) and parent.editing:
        from pdr_sign.ui import canvas as canvas_module

        words = parent.editor.textCursor().selectedText().replace("\u2029", "\n")
        if words:
            canvas_module.clipboard().setText(words)
        return bool(words)
    return canvas.item_actions.copy() or canvas.copy_selection()


def key_press(canvas: Canvas, event: QKeyEvent) -> bool:
    """Canvas keys; False to let QGraphicsView handle the key."""
    focus = canvas.scene().focusItem()
    if focus is not None and not isinstance(focus, OverlayGraphic):
        QGraphicsView.keyPressEvent(canvas, event)  # typing in a field: keys are its own
        return True
    key = event.key()
    layer = canvas.fill_layer
    if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and canvas.item_actions.delete():
        event.accept()
        return True
    if key == Qt.Key.Key_Escape:
        if layer is not None and layer.tool:
            layer.set_tool("")
        else:
            canvas.scene().clearSelection()
            canvas.selection.clear()
        event.accept()
        return True
    return False
