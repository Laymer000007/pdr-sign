"""One open document: sidebar, find bar and canvas, wired together."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from pdr_sign.services import forms
from pdr_sign.services.document import Document
from pdr_sign.services.search import SearchHit
from pdr_sign.ui.canvas import Canvas
from pdr_sign.ui.fill_model import FillModel
from pdr_sign.ui.fill_sign_panel import FillSignPanel
from pdr_sign.ui.overlay.text_item import TextGraphic
from pdr_sign.ui.render_scheduler import RenderScheduler
from pdr_sign.ui.search_bar import SearchBar
from pdr_sign.ui.search_controller import SearchController
from pdr_sign.ui.sidebar import Sidebar
from pdr_sign.ui.theme import (
    ANIMATION_MS,
    PANEL_WIDTH,
    SIDEBAR_WIDTH,
    Tokens,
    animations_enabled,
)

RESULTS_REFRESH_MS = 120  # coalesce streaming results before rebuilding the list


class DocumentTab(QWidget):
    external_link = Signal(str)
    dirty_changed = Signal(bool)
    fill_done = Signal()

    def __init__(
        self, doc: Document, scheduler: RenderScheduler, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.doc = doc
        self.view = Canvas(doc, scheduler, self)
        self.search_bar = SearchBar(self)
        self.search = SearchController(doc, self)
        self.model = FillModel(forms.list_fields(doc), self)
        self.view.attach_fill(self.model)
        self.panel = FillSignPanel(self.model.fields, self)
        self.panel.setMaximumWidth(0)
        self.panel_visible = False
        self.panel_divider = QFrame()
        self.panel_divider.setObjectName("Divider")
        self.panel_divider.setFixedWidth(1)
        self.panel_divider.hide()
        self.sidebar = Sidebar(doc, scheduler)
        self.sidebar.setMaximumWidth(0)
        self.sidebar.setMinimumWidth(0)
        self.sidebar_visible = False

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedWidth(1)
        self.divider = divider
        divider.hide()

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.sidebar)
        row.addWidget(divider)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.search_bar)
        column.addWidget(self.view, 1)
        row.addLayout(column, 1)
        row.addWidget(self.panel_divider)
        row.addWidget(self.panel)

        self._slide = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        self._slide.setDuration(ANIMATION_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.finished.connect(self._on_slide_finished)

        self.sidebar.thumbnails.page_activated.connect(self.view.go_to_page)
        self.sidebar.outline.destination_activated.connect(self.view.go_to_page)
        self.view.current_page_changed.connect(self.sidebar.thumbnails.set_current)
        self.view.external_link.connect(self.external_link)

        self._results_timer = QTimer(self, singleShot=True, interval=RESULTS_REFRESH_MS)
        self._results_timer.timeout.connect(self._refresh_results)
        self.search_bar.query_changed.connect(self._start_search)
        self.search_bar.next_requested.connect(lambda: self.search.step(1))
        self.search_bar.previous_requested.connect(lambda: self.search.step(-1))
        self.search_bar.closed.connect(self._on_search_closed)
        self.search.results_changed.connect(lambda: self._results_timer.start())
        self.search.finished.connect(self._refresh_results)
        self.search.current_changed.connect(self._on_current_hit)
        self.sidebar.search.hit_activated.connect(self.search.set_current)

        self._panel_slide = QPropertyAnimation(self.panel, b"maximumWidth", self)
        self._panel_slide.setDuration(ANIMATION_MS)
        self._panel_slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._panel_slide.finished.connect(
            lambda: self.panel_divider.setVisible(self.panel.maximumWidth() > 0)
        )
        layer = self.view.fill_layer
        assert layer is not None
        self.panel.tool_selected.connect(layer.set_tool)
        layer.tool_changed.connect(self.panel.set_tool)
        self.panel.style_changed.connect(layer.apply_style)
        self.panel.field_activated.connect(self.focus_field)
        self.panel.done.connect(self.fill_done)
        self.panel.set_values(self.model.values)
        self.model.field_changed.connect(lambda *_: self.panel.set_values(self.model.values))
        self.model.dirty_changed.connect(self.dirty_changed)
        self.view.scene().selectionChanged.connect(self._sync_style_from_selection)

    # --- Fill & Sign -------------------------------------------------------------

    def set_panel_visible(self, visible: bool, animate: bool = True) -> None:
        self.panel_visible = visible
        target = PANEL_WIDTH if visible else 0
        layer = self.view.fill_layer
        if not visible and layer is not None:
            layer.set_tool("")
        self._panel_slide.stop()
        if visible:
            self.panel_divider.show()
        if animate and animations_enabled() and self.isVisible():
            self._panel_slide.setStartValue(self.panel.maximumWidth())
            self._panel_slide.setEndValue(target)
            self._panel_slide.start()
        else:
            self.panel.setMaximumWidth(target)
            self.panel_divider.setVisible(visible)

    def focus_field(self, name: str) -> None:
        if self.view.field_layer is not None:
            self.view.field_layer.focus(name)

    def _sync_style_from_selection(self) -> None:
        layer = self.view.fill_layer
        if layer is None:
            return
        for graphic in layer.selected():
            if isinstance(graphic, TextGraphic):
                self.panel.set_style(graphic.item.font_size, graphic.item.color)
                return

    # --- search ------------------------------------------------------------------

    def open_search(self) -> None:
        self.search_bar.open_bar()
        if self.sidebar_visible:
            self.sidebar.tabs.setCurrentWidget(self.sidebar.search)

    def _start_search(self, query: str) -> None:
        self.search.start(query, self.view.current_page)
        if query.strip() and self.sidebar_visible:
            self.sidebar.tabs.setCurrentWidget(self.sidebar.search)

    def _refresh_results(self) -> None:
        self._results_timer.stop()
        hits = self.search.hits
        self.view.set_search_hits(hits)
        self.sidebar.search.set_hits(hits, self.search.query, self.search.running)
        self.sidebar.search.set_current(self.search.current_index)
        self._update_search_status()

    def _on_current_hit(self, hit: SearchHit | None) -> None:
        self.view.set_current_hit(hit)
        self.sidebar.search.set_current(self.search.current_index)
        self._update_search_status()

    def _update_search_status(self) -> None:
        s = self.search
        self.search_bar.set_status(s.current_index, len(s.hits), s.running, s.capped)

    def _on_search_closed(self) -> None:
        self.search.clear()
        self.view.setFocus()

    def set_tokens(self, t: Tokens) -> None:
        self.search_bar.set_tokens(t)
        self.panel.set_tokens(t)
        self.panel.set_values(self.model.values)
        self.view.viewport().update()

    def set_sidebar_visible(self, visible: bool, animate: bool = True) -> None:
        self.sidebar_visible = visible
        target = SIDEBAR_WIDTH if visible else 0
        self._slide.stop()
        self.sidebar.setMinimumWidth(0)
        if visible:
            self.divider.show()
        if animate and animations_enabled() and self.isVisible():
            self._slide.setStartValue(self.sidebar.maximumWidth())
            self._slide.setEndValue(target)
            self._slide.start()
        else:
            self.sidebar.setMaximumWidth(target)
            self._slide.setEndValue(target)
            self._on_slide_finished()

    def _on_slide_finished(self) -> None:
        open_ = self.sidebar.maximumWidth() > 0
        self.divider.setVisible(open_)
        if open_:
            self.sidebar.setMinimumWidth(SIDEBAR_WIDTH)
            self.sidebar.thumbnails.request_visible()

    def close_document(self) -> None:
        self.search.cancel()
        self.view.release()
        self.sidebar.thumbnails.release()
        self.view.scheduler.drop_document(self.doc)
        self.doc.close()
