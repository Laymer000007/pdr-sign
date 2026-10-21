"""One open document: sidebar, find bar and canvas, wired together."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from pdr_sign.services.document import Document
from pdr_sign.services.search import SearchHit
from pdr_sign.ui.canvas import Canvas
from pdr_sign.ui.render_scheduler import RenderScheduler
from pdr_sign.ui.search_bar import SearchBar
from pdr_sign.ui.search_controller import SearchController
from pdr_sign.ui.sidebar import Sidebar
from pdr_sign.ui.theme import ANIMATION_MS, SIDEBAR_WIDTH, Tokens, animations_enabled

RESULTS_REFRESH_MS = 120  # coalesce streaming results before rebuilding the list


class DocumentTab(QWidget):
    external_link = Signal(str)

    def __init__(
        self, doc: Document, scheduler: RenderScheduler, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.doc = doc
        self.view = Canvas(doc, scheduler, self)
        self.search_bar = SearchBar(self)
        self.search = SearchController(doc, self)
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
