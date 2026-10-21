"""One open document: sidebar + canvas, wired together."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

from pdr_sign.services.document import Document
from pdr_sign.ui.page_view import PageView
from pdr_sign.ui.render_scheduler import RenderScheduler
from pdr_sign.ui.sidebar import Sidebar
from pdr_sign.ui.theme import ANIMATION_MS, SIDEBAR_WIDTH, animations_enabled


class DocumentTab(QWidget):
    external_link = Signal(str)

    def __init__(
        self, doc: Document, scheduler: RenderScheduler, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.doc = doc
        self.view = PageView(doc, scheduler, self)
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
        row.addWidget(self.view, 1)

        self._slide = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        self._slide.setDuration(ANIMATION_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.finished.connect(self._on_slide_finished)

        self.sidebar.thumbnails.page_activated.connect(self.view.go_to_page)
        self.sidebar.outline.destination_activated.connect(self.view.go_to_page)
        self.view.current_page_changed.connect(self.sidebar.thumbnails.set_current)
        self.view.external_link.connect(self.external_link)

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
        self.view.release()
        self.sidebar.thumbnails.release()
        self.view.scheduler.drop_document(self.doc)
        self.doc.close()
