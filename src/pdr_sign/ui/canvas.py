"""The document canvas: PageView plus pointer interaction.

Links, text selection (drag, double-click, context menu, copy) and search highlights.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QClipboard,
    QColor,
    QContextMenuEvent,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
)
from PySide6.QtWidgets import QApplication, QGraphicsView, QMenu, QWidget

from pdr_sign.services.document import Document, LinkInfo
from pdr_sign.services.search import SearchHit
from pdr_sign.services.text import word_at
from pdr_sign.ui.fill_layer import FillLayer
from pdr_sign.ui.fill_model import FillModel
from pdr_sign.ui.overlay.base import OverlayGraphic
from pdr_sign.ui.overlay.field_widgets import FieldColors, FieldLayer, FieldProxy, ToggleField
from pdr_sign.ui.page_item import PageItem
from pdr_sign.ui.page_view import PageView
from pdr_sign.ui.render_scheduler import RenderScheduler
from pdr_sign.ui.text_selection import TextSelection
from pdr_sign.ui.theme import Tokens

AUTOSCROLL_EDGE = 24  # px from the viewport edge where a drag starts scrolling


def clipboard() -> QClipboard:
    """The system clipboard. Tests replace this so they never touch the user's."""
    return QGuiApplication.clipboard()


def translucent(hex_color: str, alpha: int) -> QColor:
    color = QColor(hex_color)
    color.setAlpha(alpha)
    return color


class Canvas(PageView):
    external_link = Signal(str)

    def __init__(
        self, doc: Document, scheduler: RenderScheduler, parent: QWidget | None = None
    ) -> None:
        super().__init__(doc, scheduler, parent)
        self.selection = TextSelection(doc, self)
        self.selection.changed.connect(self._on_selection_changed)
        self._press_pos: QPoint | None = None
        self._press_link: LinkInfo | None = None
        self._selecting = False
        self._search_pages: set[int] = set()
        self._current_hit: SearchHit | None = None
        self._press_to_items = False
        self.fill_layer: FillLayer | None = None
        self.field_layer: FieldLayer | None = None
        self.scene().focusItemChanged.connect(self._on_focus_item)

    def attach_fill(self, model: FillModel) -> None:
        """Show the document's form fields and Fill & Sign items."""
        self.field_layer = FieldLayer(model, self.page_items)
        self.fill_layer = FillLayer(model, self.page_items)

    # --- appearance -------------------------------------------------------------

    @staticmethod
    def set_tokens(t: Tokens) -> None:
        PageItem.selection_color = translucent(t.accent, 80)
        PageItem.hit_color = translucent(t.search_hit, 110)
        PageItem.current_hit_color = translucent(t.search_current, 150)
        OverlayGraphic.accent = QColor(t.accent)
        FieldColors.fill = QColor(t.field_fill)
        FieldColors.border = QColor(t.field_border)
        FieldColors.accent = QColor(t.accent)

    # --- search highlights ---------------------------------------------------------

    def set_search_hits(self, hits: list[SearchHit]) -> None:
        by_page: dict[int, list[tuple[float, float, float, float]]] = {}
        for hit in hits:
            by_page.setdefault(hit.page, []).append(hit.rect)
        for page in self._search_pages | set(by_page):
            item = self.page_items[page]
            item.search_rects = by_page.get(page, [])
            item.update()
        self._search_pages = set(by_page)

    def set_current_hit(self, hit: SearchHit | None) -> None:
        if self._current_hit is not None:
            old = self.page_items[self._current_hit.page]
            old.current_hit = None
            old.update()
        self._current_hit = hit
        if hit is not None:
            item = self.page_items[hit.page]
            item.current_hit = hit.rect
            item.update()
            self.reveal(hit.page, hit.rect)

    # --- selection -----------------------------------------------------------------

    def _on_selection_changed(self, pages: set[int]) -> None:
        for page in pages:
            item = self.page_items[page]
            item.selection_rects = self.selection.rects(page)
            item.update()

    def copy_selection(self) -> bool:
        text = self.selection.text()
        if text:
            clipboard().setText(text)
        return bool(text)

    def _publish_primary_selection(self) -> None:
        """X11/Wayland middle-click paste gets the selected text, as in other apps."""
        board = clipboard()
        text = self.selection.text()
        if text and board.supportsSelection():
            board.setText(text, QClipboard.Mode.Selection)

    # --- hit testing ---------------------------------------------------------------

    def _page_point(self, pos: QPoint) -> tuple[int, QPointF] | None:
        if self.page_layout is None:
            return None
        scene = self.mapToScene(pos)
        page = self.page_layout.page_at(scene.y())
        return page, self.page_items[page].mapFromScene(scene)

    def _link_at(self, pos: QPoint) -> LinkInfo | None:
        hit = self._page_point(pos)
        if hit is None:
            return None
        item = self.page_items[hit[0]]
        return item.link_at(hit[1]) if item.page_rect().contains(hit[1]) else None

    def _over_text(self, pos: QPoint) -> bool:
        hit = self._page_point(pos)
        if hit is None:
            return False
        page, local = hit
        return word_at(self.doc.words(page), local.x(), local.y()) is not None

    # --- mouse -------------------------------------------------------------------

    def _interactive_item_at(self, pos: QPoint) -> bool:
        """A form field or Fill & Sign item (anything above the page itself)."""
        item = self.itemAt(pos)
        return item is not None and not isinstance(item, PageItem)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        self._press_to_items = self._interactive_item_at(pos)
        if self._press_to_items:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._start_line(pos) or self._place_with_tool(pos):
                event.accept()
                return
            self.scene().clearSelection()
            focused = self.scene().focusItem()
            if focused is not None:
                focused.clearFocus()  # commits a field being edited
            self._press_pos = pos
            self._press_link = self._link_at(self._press_pos)
            self._selecting = False
            self.setFocus()
            event.accept()
            return
        super().mousePressEvent(event)

    def _start_line(self, pos: QPoint) -> bool:
        layer = self.fill_layer
        hit = self._page_point(pos)
        if layer is None or layer.tool != "line" or hit is None:
            return False
        page, local = hit
        if not self.page_items[page].page_rect().contains(local):
            return False
        self.scene().clearSelection()
        layer.begin_line(page, local)
        return True

    def _place_with_tool(self, pos: QPoint) -> bool:
        layer = self.fill_layer
        hit = self._page_point(pos)
        if layer is None or not layer.tool or hit is None:
            return False
        page, local = hit
        if not self.page_items[page].page_rect().contains(local):
            return False
        self.scene().clearSelection()
        layer.place(page, local)
        return True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        if self._press_to_items:
            super().mouseMoveEvent(event)
            return
        draft = self.fill_layer.draft if self.fill_layer is not None else None
        if draft is not None:
            parent = draft.parentItem()
            if parent is not None:
                local = parent.mapFromScene(self.mapToScene(pos))
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self.fill_layer.drag_line(local, any_angle=shift)  # type: ignore[union-attr]
            event.accept()
            return
        if self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if not self._selecting:
                moved = (pos - self._press_pos).manhattanLength()
                if moved >= QApplication.startDragDistance():
                    start = self._page_point(self._press_pos)
                    self._selecting = start is not None and self.selection.begin(
                        start[0], start[1].x(), start[1].y()
                    )
            if self._selecting:
                self._autoscroll(pos)
                hit = self._page_point(pos)
                if hit is not None:
                    self.selection.extend(hit[0], hit[1].x(), hit[1].y())
            event.accept()
            return
        if self.fill_layer is not None and self.fill_layer.tool:
            shape = Qt.CursorShape.CrossCursor
        elif self._link_at(pos) is not None:
            shape = Qt.CursorShape.PointingHandCursor
        elif self._over_text(pos):
            shape = Qt.CursorShape.IBeamCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        self.viewport().setCursor(shape)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._press_to_items:
            self._press_to_items = False
            super().mouseReleaseEvent(event)
            return
        if self.fill_layer is not None and self.fill_layer.draft is not None:
            self.fill_layer.end_line()
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._press_pos is None:
            super().mouseReleaseEvent(event)
            return
        pos = event.position().toPoint()
        if self._selecting:
            self._publish_primary_selection()
        else:
            link = self._link_at(pos)
            if link is not None and link == self._press_link:
                self._follow(link)
            else:
                self.selection.clear()
        self._press_pos, self._press_link, self._selecting = None, None, False
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._interactive_item_at(event.position().toPoint()):
            super().mouseDoubleClickEvent(event)
            return
        hit = self._page_point(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and hit is not None:
            if self.selection.select_word(hit[0], hit[1].x(), hit[1].y()):
                self._publish_primary_selection()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        hit = self._page_point(event.pos())
        menu = QMenu(self)
        copy = menu.addAction("Copy")
        copy.setShortcut("Ctrl+C")
        copy.setEnabled(not self.selection.is_empty)
        copy.triggered.connect(self.copy_selection)
        if hit is not None:
            page = hit[0]
            select = menu.addAction("Select page text")
            select.triggered.connect(lambda: self.selection.select_page(page))
        menu.exec(event.globalPos())

    # --- keyboard -------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        focus = self.scene().focusItem()
        if focus is not None and not isinstance(focus, OverlayGraphic):
            QGraphicsView.keyPressEvent(self, event)  # typing in a field: keys are its own
            return
        key = event.key()
        layer = self.fill_layer
        deleting = key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
        if deleting and layer is not None and layer.delete_selected():
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            if layer is not None and layer.tool:
                layer.set_tool("")
            else:
                self.scene().clearSelection()
                self.selection.clear()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_focus_item(self, new: object, _old: object, reason: Qt.FocusReason) -> None:
        """Tabbing into a field or item off-screen scrolls it into view."""
        if reason == Qt.FocusReason.MouseFocusReason:
            return
        if isinstance(new, FieldProxy | ToggleField):
            self.reveal(new.field.page, new.field.rect)
        elif isinstance(new, OverlayGraphic):
            self.reveal(new.item.page, new.scene_rect_in_page())

    def _follow(self, link: LinkInfo) -> None:
        if link.uri:
            self.external_link.emit(link.uri)
        elif link.page is not None:
            self.go_to_page(link.page, link.y)

    def _autoscroll(self, pos: QPoint) -> None:
        bar = self.verticalScrollBar()
        height = self.viewport().height()
        if pos.y() < AUTOSCROLL_EDGE:
            bar.setValue(bar.value() - (AUTOSCROLL_EDGE - pos.y()))
        elif pos.y() > height - AUTOSCROLL_EDGE:
            bar.setValue(bar.value() + (pos.y() - height + AUTOSCROLL_EDGE))
