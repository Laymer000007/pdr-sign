"""Keyboard shortcuts for the main window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from pdr_sign.ui import save_flow

if TYPE_CHECKING:
    from pdr_sign.ui.main_window import MainWindow


def install(window: MainWindow) -> None:
    """Window-wide keyboard shortcuts (each also reachable from the UI)."""

    def add(keys: list[QKeySequence | QKeySequence.StandardKey | str], slot: object) -> QAction:
        action = QAction(window)
        action.setShortcuts([QKeySequence(k) for k in keys])
        action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        action.triggered.connect(slot)
        window.addAction(action)
        return action

    add([QKeySequence.StandardKey.Open], window.browse)
    add([QKeySequence.StandardKey.Close], lambda: window._with_tab(window.close_tab))
    add(["Ctrl+Tab"], lambda: window._cycle_tab(1))
    add(["Ctrl+Shift+Tab", "Ctrl+Backtab"], lambda: window._cycle_tab(-1))
    add(["Ctrl++", "Ctrl+="], lambda: window._with_tab(lambda t: t.view.zoom_in()))
    add(["Ctrl+-"], lambda: window._with_tab(lambda t: t.view.zoom_out()))
    add(["Ctrl+0"], lambda: window._with_tab(window._apply_default_zoom))
    add(["F9"], lambda: window.set_sidebar_visible(not window.settings.show_sidebar))
    add([QKeySequence.StandardKey.Find], lambda: window._with_tab(lambda t: t.open_search()))
    add(
        [QKeySequence.StandardKey.Copy],
        lambda: window._with_tab(lambda t: t.view.copy_selection()),
    )
    add([QKeySequence.StandardKey.Print], window.print_current)
    add(["Ctrl+S"], lambda: window._with_tab(lambda t: save_flow.save(window, t)))
    add(["Ctrl+Shift+S"], lambda: window._with_tab(lambda t: save_flow.save_as(window, t)))
    add(["Ctrl+E"], lambda: window.set_fill_mode(not window.fill_mode))
    add(
        [QKeySequence.StandardKey.Undo],
        lambda: window._with_tab(lambda t: t.model.undo_stack.undo()),
    )
    add(
        [QKeySequence.StandardKey.Redo, "Ctrl+Shift+Z"],
        lambda: window._with_tab(lambda t: t.model.undo_stack.redo()),
    )
