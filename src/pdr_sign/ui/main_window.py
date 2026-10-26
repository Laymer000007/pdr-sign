"""Top-level window: header, document tabs, empty state, file handling."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QCloseEvent,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
)
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services import recent as recent_service
from pdr_sign.services import settings as settings_service
from pdr_sign.services.document import Document, DocumentError, PasswordRequired, WrongPassword
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.services.signatures import SignatureStore
from pdr_sign.ui import dialogs, icons, save_flow, shortcuts, window_actions
from pdr_sign.ui.canvas import Canvas
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.empty_state import EmptyState
from pdr_sign.ui.header_bar import HeaderBar
from pdr_sign.ui.render_scheduler import RenderScheduler
from pdr_sign.ui.signature_library import SignatureLibrary
from pdr_sign.ui.theme import Tokens
from pdr_sign.ui.window_helpers import is_pdf_url, window_title, zoom_setting


class ThemeLike(Protocol):
    def set_override(self, override: str) -> None: ...


class MainWindow(QMainWindow):
    def __init__(
        self,
        tokens: Tokens,
        settings: Settings | None = None,
        recent: RecentFiles | None = None,
        scheduler: RenderScheduler | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings or Settings()
        self.recent = recent or RecentFiles()
        self.scheduler = scheduler or RenderScheduler()
        self.setWindowTitle(window_title())
        self.resize(1180, 820)
        self.setMinimumSize(640, 480)
        self.setAcceptDrops(True)

        self.header = HeaderBar(self)
        self.tab_bar = QTabBar(self)
        self.tab_bar.setObjectName("DocumentTabs")
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tab_bar.hide()
        self.stack = QStackedWidget(self)
        self.empty_state = EmptyState(self)
        self.stack.addWidget(self.empty_state)

        central = QWidget(self)
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.header)
        column.addWidget(self.tab_bar)
        column.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.tabs: list[DocumentTab] = []
        self._printer: QPrinter | None = None  # kept so printer choices persist
        self.fill_mode = False
        self.signatures = SignatureLibrary(SignatureStore(self.settings.signature_dir), self)
        self.theme_controller: ThemeLike | None = None  # set by app.build_window
        self._connect()
        shortcuts.install(self)
        self.tokens = tokens
        self.set_tokens(tokens)
        self._refresh_chrome()

    # --- wiring ---------------------------------------------------------------

    def _connect(self) -> None:
        h = self.header
        h.open_requested.connect(self.browse)
        h.sidebar_toggled.connect(self.set_sidebar_visible)
        h.page_requested.connect(lambda i: self._with_tab(lambda t: t.view.go_to_page(i)))
        h.zoom_in_requested.connect(lambda: self._with_tab(lambda t: t.view.zoom_in()))
        h.zoom_out_requested.connect(lambda: self._with_tab(lambda t: t.view.zoom_out()))
        h.zoom_preset_requested.connect(self._zoom_preset)
        h.about_requested.connect(lambda: dialogs.AboutDialog(self).exec())
        h.search_requested.connect(lambda: self._with_tab(lambda t: t.open_search()))
        h.print_requested.connect(self.print_current)
        h.fill_toggled.connect(self.set_fill_mode)
        h.save_requested.connect(lambda: self._with_tab(lambda t: save_flow.save(self, t)))
        h.save_as_requested.connect(lambda: self._with_tab(lambda t: save_flow.save_as(self, t)))
        h.signed_copy_requested.connect(
            lambda: self._with_tab(lambda t: save_flow.save_signed_copy(self, t))
        )
        h.settings_requested.connect(self.open_settings)
        self.empty_state.open_requested.connect(self.browse)
        self.empty_state.recent_requested.connect(lambda p: self.open_paths([p]))
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabMoved.connect(self._on_tab_moved)

    # --- tabs -----------------------------------------------------------------

    def current_tab(self) -> DocumentTab | None:
        widget = self.stack.currentWidget()
        return widget if isinstance(widget, DocumentTab) else None

    def _with_tab(self, fn: object) -> None:
        tab = self.current_tab()
        if tab is not None and callable(fn):
            fn(tab)

    def _cycle_tab(self, step: int) -> None:
        if len(self.tabs) > 1:
            self.tab_bar.setCurrentIndex((self.tab_bar.currentIndex() + step) % len(self.tabs))

    def _on_tab_changed(self, index: int) -> None:
        if 0 <= index < len(self.tabs):
            self.stack.setCurrentWidget(self.tabs[index])
        self._refresh_chrome()

    def _on_tab_moved(self, src: int, dst: int) -> None:
        self.tabs.insert(dst, self.tabs.pop(src))

    def _refresh_chrome(self) -> None:
        tab = self.current_tab()
        self.tab_bar.setVisible(len(self.tabs) > 1)
        if tab is None:
            self.stack.setCurrentWidget(self.empty_state)
            self.empty_state.set_recent(self.recent.existing())
            self.header.set_document(None)
            self.setWindowTitle(window_title())
            return
        self.header.set_document(tab.doc.page_count)
        self.header.set_page(tab.view.current_page)
        self.header.set_zoom(tab.view.zoom, tab.view.zoom_mode)
        self.header.set_sidebar_checked(tab.sidebar_visible)
        self.header.set_fill_checked(self.fill_mode)
        self.header.set_save_enabled(tab.model.dirty)
        self.setWindowTitle(window_title(tab.doc.display_name, tab.model.dirty))
        tab.view.setFocus()

    # --- opening and closing ---------------------------------------------------------

    def browse(self) -> None:
        start = str(Path(self.recent.entries[0].path).parent) if self.recent.entries else ""
        paths, _ = QFileDialog.getOpenFileNames(self, "Open PDF", start, "PDF files (*.pdf)")
        self.open_paths(paths)

    def open_paths(self, paths: list[str]) -> None:
        for raw in paths:
            path = Path(raw).expanduser().resolve()
            existing = next((t for t in self.tabs if t.doc.path == path), None)
            if existing is not None:
                self.tab_bar.setCurrentIndex(self.tabs.index(existing))
                continue
            doc = self._open_document(path)
            if doc is not None:
                self._add_tab(doc)
        self.raise_()
        self.activateWindow()

    def _open_document(self, path: Path) -> Document | None:
        password: str | None = None
        retry = False
        while True:
            try:
                return Document.open(path, password)
            except PasswordRequired as exc:
                retry = isinstance(exc, WrongPassword)
                password = dialogs.ask_password(self, path.name, retry)
                if password is None:
                    return None
            except DocumentError as exc:
                dialogs.show_error(self, "Couldn't open file", str(exc))
                if not path.exists():
                    self.recent.remove(path)
                return None

    def _add_tab(self, doc: Document) -> None:
        tab = DocumentTab(doc, self.scheduler, self, library=self.signatures)
        tab.view.current_page_changed.connect(lambda i, t=tab: self._on_page(t, i))
        tab.view.zoom_changed.connect(lambda z, m, t=tab: self._on_zoom(t, z, m))
        tab.external_link.connect(self.open_external_link)
        tab.dirty_changed.connect(lambda _d, t=tab: self._update_tab_title(t))
        tab.fill_done.connect(lambda: self.set_fill_mode(False))
        self.tabs.append(tab)
        self.stack.addWidget(tab)
        self.stack.setCurrentWidget(tab)
        tab.set_sidebar_visible(self.settings.show_sidebar, animate=False)
        tab.set_tokens(self.tokens)
        tab.set_panel_visible(self.fill_mode, animate=False)
        tab.set_default_ink(self.settings.default_text_color)

        entry = self.recent.get(doc.path)
        self._apply_zoom_setting(tab, entry.zoom if entry and entry.zoom else None)
        if entry and 0 < entry.page < doc.page_count:
            tab.view.go_to_page(entry.page)
        self.recent.touch(doc.path)
        # A missing thumbnail only affects the recent grid.
        with contextlib.suppress(OSError, DocumentError, RuntimeError):
            recent_service.save_thumbnail(doc.path, doc.thumbnail_png())

        self.tab_bar.blockSignals(True)
        index = self.tab_bar.addTab(doc.path.name)
        self.tab_bar.setTabToolTip(index, str(doc.path))
        self.tab_bar.setTabButton(
            index, QTabBar.ButtonPosition.RightSide, window_actions.close_button(self, tab)
        )
        self.tab_bar.setCurrentIndex(index)
        self.tab_bar.blockSignals(False)
        self._refresh_chrome()

    def close_tab(self, tab: DocumentTab, ask: bool = True) -> bool:
        """Close a tab; with unsaved changes, ask first. False if the user cancelled."""
        if ask and not save_flow.confirm_close(self, tab):
            return False
        self._remember(tab)
        index = self.tabs.index(tab)
        self.tabs.pop(index)
        self.tab_bar.blockSignals(True)
        self.tab_bar.removeTab(index)
        self.tab_bar.blockSignals(False)
        self.stack.removeWidget(tab)
        tab.close_document()
        tab.deleteLater()
        if self.tabs:
            self.stack.setCurrentWidget(self.tabs[self.tab_bar.currentIndex()])
        self._refresh_chrome()
        return True

    def reload_tab(self, tab: DocumentTab, path: Path) -> DocumentTab | None:
        """Reopen ``tab`` from ``path`` (after saving) in the same place, page and zoom."""
        index = self.tabs.index(tab)
        password = tab.doc.password
        self.close_tab(tab, ask=False)  # remembers page and zoom for the reopen
        try:
            doc = Document.open(path, password)
        except DocumentError as exc:
            dialogs.show_error(self, "Couldn't reopen the saved file", str(exc))
            return None
        self._add_tab(doc)
        new = self.tabs[-1]
        if index < len(self.tabs) - 1:
            self.tab_bar.moveTab(len(self.tabs) - 1, index)
            self.tab_bar.setCurrentIndex(index)
        return new

    def open_settings(self) -> None:
        window_actions.open_settings(self)

    def open_external_link(self, uri: str) -> None:
        window_actions.open_external_link(self, uri)

    def toast_actions(self, text: str, actions: list[tuple[str, Callable[[], None]]]) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.view.action_toast.show_actions(text, actions)

    def toast(self, text: str) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.view.indicator.show_message(text, 1800)

    def _remember(self, tab: DocumentTab) -> None:
        zoom = zoom_setting(tab.view.zoom, tab.view.zoom_mode)
        self.recent.touch(tab.doc.path, page=tab.view.current_page, zoom=zoom)

    def closeEvent(self, event: QCloseEvent) -> None:
        for tab in list(self.tabs):
            if not self.close_tab(tab):
                event.ignore()  # the user chose Cancel
                return
        settings_service.save(self.settings)
        super().closeEvent(event)

    # --- view state --------------------------------------------------------------

    def _on_page(self, tab: DocumentTab, index: int) -> None:
        if tab is self.current_tab():
            self.header.set_page(index)

    def _on_zoom(self, tab: DocumentTab, zoom: float, mode: str) -> None:
        if tab is self.current_tab():
            self.header.set_zoom(zoom, mode)

    def _zoom_preset(self, value: object) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        if isinstance(value, str):
            tab.view.apply_zoom_mode(value)
        elif isinstance(value, float):
            tab.view.set_zoom(value)

    def _apply_zoom_setting(self, tab: DocumentTab, value: str | None) -> None:
        value = value or self.settings.default_zoom
        if value in ("fit-width", "fit-page"):
            tab.view.apply_zoom_mode(value)
            return
        try:
            zoom = float(value)
        except ValueError:
            zoom = 1.0
        tab.view.set_zoom(zoom if value != "100" else 1.0, osd=False)

    def _apply_default_zoom(self, tab: DocumentTab) -> None:
        self._apply_zoom_setting(tab, None)

    def set_fill_mode(self, on: bool) -> None:
        """Show or hide the Fill & Sign panel (one app-wide mode, like the sidebar)."""
        if self.current_tab() is None:
            on = False
        self.fill_mode = on
        for tab in self.tabs:
            tab.set_panel_visible(on, animate=tab is self.current_tab())
        self.header.set_fill_checked(on)

    def _update_tab_title(self, tab: DocumentTab) -> None:
        if tab not in self.tabs:
            return
        index = self.tabs.index(tab)
        marker = "• " if tab.model.dirty else ""
        self.tab_bar.setTabText(index, marker + tab.doc.path.name)
        if tab is self.current_tab():
            self._refresh_chrome()

    def print_current(self) -> None:
        window_actions.print_current(self)

    def set_sidebar_visible(self, visible: bool) -> None:
        self.settings.show_sidebar = visible
        for tab in self.tabs:
            tab.set_sidebar_visible(visible, animate=tab is self.current_tab())
        self.header.set_sidebar_checked(visible)

    # --- theme / drag and drop -----------------------------------------------------

    def set_tokens(self, t: Tokens) -> None:
        """Re-apply theme-dependent bits that QSS can't reach (icon colours)."""
        self.tokens = t
        self.header.set_tokens(t)
        self.empty_state.set_tokens(t)
        Canvas.set_tokens(t)
        for tab in self.tabs:
            tab.set_tokens(t)
        for i in range(self.tab_bar.count()):
            button = self.tab_bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if isinstance(button, QToolButton):
                button.setIcon(icons.icon("x", t.muted, 14))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(is_pdf_url(u) for u in event.mimeData().urls()):
            event.acceptProposedAction()
            self.empty_state.set_drag_active(True)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.empty_state.set_drag_active(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self.empty_state.set_drag_active(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if is_pdf_url(u)]
        if paths:
            event.acceptProposedAction()
            self.open_paths(paths)
