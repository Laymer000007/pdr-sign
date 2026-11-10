"""Putting a document tab into a window and taking it out again (closing it, or moving
it to another window with its undo history, page and zoom intact)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QTabBar

from pdr_sign.ui import window_actions

if TYPE_CHECKING:
    from pdr_sign.ui.document_tab import DocumentTab
    from pdr_sign.ui.main_window import MainWindow


def attach(window: MainWindow, tab: DocumentTab) -> None:
    """Show ``tab`` in ``window``: wire it to this window only, and give it this
    window's sidebar, Fill & Sign panel and theme state."""
    links = [
        tab.view.current_page_changed.connect(lambda i: window._on_page(tab, i)),
        tab.view.zoom_changed.connect(lambda z, m: window._on_zoom(tab, z, m)),
        tab.external_link.connect(window.open_external_link),
        tab.dirty_changed.connect(lambda _d: window._update_tab_title(tab)),
        tab.fill_done.connect(lambda: window.set_fill_mode(False)),
        tab.fill_requested.connect(window._open_fill_for_field),
    ]
    window._tab_links[tab] = links
    window.tabs.append(tab)
    window.stack.addWidget(tab)  # reparents it from any old window
    window.stack.setCurrentWidget(tab)
    tab.set_sidebar_visible(window.settings.show_sidebar, animate=False)
    tab.set_tokens(window.tokens)
    tab.set_panel_visible(window.fill_mode, animate=False)
    tab.set_default_ink(window.settings.default_text_color)

    bar = window.tab_bar
    bar.blockSignals(True)
    marker = "• " if tab.model.dirty else ""
    index = bar.addTab(marker + tab.doc.path.name)
    bar.setTabToolTip(index, str(tab.doc.path))
    bar.setTabButton(
        index, QTabBar.ButtonPosition.RightSide, window_actions.close_button(window, tab)
    )
    bar.setCurrentIndex(index)
    bar.blockSignals(False)


def detach(window: MainWindow, tab: DocumentTab) -> None:
    """Take ``tab`` out of ``window`` without closing its document."""
    tab.view.release_interaction()
    for link in window._tab_links.pop(tab, []):
        QObject.disconnect(link)
    index = window.tabs.index(tab)
    window.tabs.pop(index)
    window.tab_bar.blockSignals(True)
    window.tab_bar.removeTab(index)
    window.tab_bar.blockSignals(False)
    window.stack.removeWidget(tab)
    if window.tabs:
        window.stack.setCurrentWidget(window.tabs[window.tab_bar.currentIndex()])
    window._refresh_chrome()


def reload(window: MainWindow, tab: DocumentTab, path: Path) -> DocumentTab | None:
    """Reopen ``tab`` from ``path`` (after saving) in the same place, page and zoom."""
    from pdr_sign.services.document import Document, DocumentError
    from pdr_sign.ui import dialogs

    index = window.tabs.index(tab)
    password = tab.doc.password
    window.close_tab(tab, ask=False)  # remembers page and zoom for the reopen
    try:
        doc = Document.open(path, password)
    except DocumentError as exc:
        dialogs.show_error(window, "Couldn't reopen the saved file", str(exc))
        return None
    window._add_tab(doc)
    new = window.tabs[-1]
    if index < len(window.tabs) - 1:
        window.tab_bar.moveTab(len(window.tabs) - 1, index)
        window.tab_bar.setCurrentIndex(index)
    return new
