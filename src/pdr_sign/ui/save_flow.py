"""Save, Save As and Save signed copy, as the user experiences them.

Decides *where* and *whether* to write (signed documents, read-only files, cancel),
runs the pipeline in ``services/saving.py``, reports problems clearly, and reloads the
tab from the written file so what you see is exactly what was saved.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pdr_sign.services import saving
from pdr_sign.services.saving import SaveRequest
from pdr_sign.ui import desktop, dialogs

if TYPE_CHECKING:
    from pdr_sign.ui.document_tab import DocumentTab
    from pdr_sign.ui.main_window import MainWindow


def flush_edits(tab: DocumentTab) -> None:
    """Commit whatever is still being typed (a field or a text box) to the model."""
    focused = tab.view.scene().focusItem()
    if focused is not None:
        focused.clearFocus()
    if tab.view.field_layer is not None:
        tab.view.field_layer.commit_pending()


def request_for(tab: DocumentTab, flatten: bool = False) -> SaveRequest:
    values, items = tab.model.save_request()
    return SaveRequest(values=values, items=items, flatten=flatten)


def _write(window: MainWindow, tab: DocumentTab, target: Path, flatten: bool) -> bool:
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        saving.save(tab.doc, target, request_for(tab, flatten))
    except saving.SaveError as exc:
        QApplication.restoreOverrideCursor()
        dialogs.show_error(window, "Couldn't save", f"{exc}\n\nYour original file was not changed.")
        return False
    QApplication.restoreOverrideCursor()
    return True


def save(window: MainWindow, tab: DocumentTab, reload: bool = True) -> bool:
    """Ctrl+S. True when the document ends up saved (or had nothing to save).

    ``reload=False`` when the tab is about to close anyway.
    """
    flush_edits(tab)
    if not tab.model.dirty:
        return True
    if tab.signed:
        choice = dialogs.confirm_signed(window)
        if choice == "cancel":
            return False
        if choice == "save_as":
            return save_as(window, tab)
    path = tab.doc.path
    if not saving.can_write_in_place(path):
        # Read-only file or folder: offer a copy instead of failing.
        return save_as(window, tab, note="This file can't be changed here. Save a copy:")
    if not _write(window, tab, path, flatten=False):
        return False
    if reload:
        window.reload_tab(tab, path)
        window.toast("Saved")
    return True


def suggested_folder(path: Path) -> Path:
    """Where Save As starts: next to the original, unless that folder is read-only."""
    return path.parent if os.access(path.parent, os.W_OK) else Path.home()


def save_as(window: MainWindow, tab: DocumentTab, note: str = "") -> bool:
    """Ctrl+Shift+S: write to a new file and switch the tab to it."""
    flush_edits(tab)
    title = note or "Save As"
    target = dialogs.ask_save_path(
        window, title, suggested_folder(tab.doc.path) / tab.doc.path.name
    )
    if target is None:
        return False
    if target.resolve() == tab.doc.path.resolve() and not saving.can_write_in_place(target):
        dialogs.show_error(
            window, "Couldn't save", "That file can't be changed. Choose another name or folder."
        )
        return False
    if not _write(window, tab, target, flatten=False):
        return False
    window.reload_tab(tab, target)
    window.toast(f"Saved as {target.name}")
    return True


def save_signed_copy(window: MainWindow, tab: DocumentTab) -> Path | None:
    """Write a new file with everything locked into the pages; the original stays as it
    is (and so does this tab, unsaved changes included). Returns the new file."""
    flush_edits(tab)
    original = tab.doc.path
    folder = original.parent
    if os.access(folder, os.W_OK):
        target = saving.signed_copy_path(original)
    else:
        chosen = dialogs.ask_save_path(
            window, "Save signed copy", Path.home() / saving.signed_copy_name(original)
        )
        if chosen is None:
            return None
        folder = chosen.parent
        target = saving.numbered(chosen)  # never overwrite, even a file picked by hand
    if not dialogs.confirm_signed_copy(window, target.name):
        return None
    request = request_for(tab, flatten=True)
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        for _attempt in range(20):
            try:
                saving.save(tab.doc, target, request, overwrite=False)
                break
            except saving.TargetExists:
                # Someone created that name in the meantime: take the next number.
                target = saving.numbered(target)
        else:
            raise saving.SaveError("Couldn't find a free file name for the signed copy.")
    except saving.SaveError as exc:
        QApplication.restoreOverrideCursor()
        dialogs.show_error(
            window, "Couldn't save the signed copy", f"{exc}\n\nYour original file was not changed."
        )
        return None
    QApplication.restoreOverrideCursor()
    saved = target
    window.toast_actions(
        "Signed copy saved",
        [
            ("Open", lambda: window.open_paths([str(saved)])),
            ("Show in folder", lambda: desktop.show_in_folder(saved)),
        ],
    )
    return saved


def confirm_close(window: MainWindow, tab: DocumentTab) -> bool:
    """Before closing a tab: True if it may close (saved, discarded or clean)."""
    flush_edits(tab)
    if not tab.model.dirty:
        return True
    answer = dialogs.ask_unsaved(window, tab.doc.path.name)
    if answer == "cancel":
        return False
    if answer == "discard":
        return True
    return save(window, tab, reload=False)
