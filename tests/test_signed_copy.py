"""Save signed copy: a new, locked-in file next to the original; never overwrites."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services import saving
from pdr_sign.services.document import Document
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.saving import SaveRequest
from pdr_sign.services.settings import Settings
from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui import dialogs
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow

SUFFIX = " - signed with PDR-sign"


# --- naming ---------------------------------------------------------------------------


def test_name_next_to_the_original(tmp_path: Path) -> None:
    original = tmp_path / "Lease agreement.pdf"
    assert saving.signed_copy_path(original) == tmp_path / f"Lease agreement{SUFFIX}.pdf"


def test_numbering_when_taken(tmp_path: Path) -> None:
    original = tmp_path / "Form.pdf"
    (tmp_path / f"Form{SUFFIX}.pdf").write_bytes(b"x")
    assert saving.signed_copy_path(original).name == f"Form{SUFFIX} (2).pdf"
    (tmp_path / f"Form{SUFFIX} (2).pdf").write_bytes(b"x")
    assert saving.signed_copy_path(original).name == f"Form{SUFFIX} (3).pdf"


def test_signing_a_signed_copy_counts_up(tmp_path: Path) -> None:
    copy = tmp_path / f"Form{SUFFIX}.pdf"
    copy.write_bytes(b"x")
    assert saving.signed_copy_path(copy).name == f"Form{SUFFIX} (2).pdf"
    numbered = tmp_path / f"Form{SUFFIX} (2).pdf"
    assert saving.signed_copy_name(numbered) == f"Form{SUFFIX}.pdf"


def test_numbered_keeps_a_free_choice(tmp_path: Path) -> None:
    chosen = tmp_path / "mine.pdf"
    assert saving.numbered(chosen) == chosen
    chosen.write_bytes(b"x")
    assert saving.numbered(chosen).name == "mine (2).pdf"


# --- never overwrite ----------------------------------------------------------------------


def test_save_without_overwrite_refuses_an_existing_file(form_pdf: Path, tmp_path: Path) -> None:
    target = tmp_path / "taken.pdf"
    target.write_bytes(b"precious")
    doc = Document.open(form_pdf)
    with pytest.raises(saving.TargetExists):
        saving.save(doc, target, SaveRequest(flatten=True), overwrite=False)
    assert target.read_bytes() == b"precious"
    assert not list(tmp_path.glob("*.pdr-*"))


def test_a_file_appearing_mid_save_is_not_overwritten(
    form_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "copy.pdf"
    real_verify = saving.verify

    def sneaky(*args: object) -> None:
        real_verify(*args)  # type: ignore[arg-type]
        target.write_bytes(b"someone else's")  # appears after the name was chosen

    monkeypatch.setattr(saving, "verify", sneaky)
    with pytest.raises(saving.TargetExists):
        saving.save(Document.open(form_pdf), target, SaveRequest(flatten=True), overwrite=False)
    assert target.read_bytes() == b"someone else's"


# --- the dialog -------------------------------------------------------------------------------


def test_confirmation_wording_and_default(qapp: QApplication) -> None:
    box = dialogs.signed_copy_box(None, f"Form{SUFFIX}.pdf")
    assert box.windowTitle() == "Save signed copy?"
    assert box.text() == (
        f"PDR will create a new file: Form{SUFFIX}.pdf\n\n"
        "Your original stays unchanged, so you can still make corrections and save another "
        "signed copy later.\n\n"
        "In the new copy, everything you filled in, signed and stamped is locked into the "
        "page. Fields, text, signatures and stamps can no longer be edited or removed in "
        "normal PDF readers.\n\n"
        "Please check the document carefully before continuing."
    )
    labels = [b.text().replace("&", "") for b in box.buttons()]
    assert sorted(labels) == ["Cancel", "Save signed copy"]
    default = box.defaultButton()
    assert default is not None and box.standardButton(default) == QMessageBox.StandardButton.Cancel


def test_feature_never_claims_protection() -> None:
    import inspect

    from pdr_sign.ui import header_bar, save_flow

    text = " ".join(
        [
            dialogs.SIGNED_COPY_TITLE,
            dialogs.SIGNED_COPY_BODY,
            dialogs.SIGNED_COPY_ACCEPT,
            inspect.getsource(save_flow.save_signed_copy),
            inspect.getsource(header_bar),
        ]
    ).lower()
    for word in ("secured", "encrypted", "tamper-proof", "tamperproof"):
        assert word not in text


# --- the flow in the window ---------------------------------------------------------------


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    settings = Settings(theme="light", signature_dir=str(tmp_path / "sigs"))
    w = build_window(configure(qapp, settings), settings, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.resize(1100, 800)
    w.show()
    qtbot.waitExposed(w)
    yield w
    for tab in list(w.tabs):
        w.close_tab(tab, ask=False)


@pytest.fixture
def confirmed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    names: list[str] = []
    monkeypatch.setattr(
        dialogs, "confirm_signed_copy", lambda _p, name: (names.append(name), True)[1]
    )
    return names


def filled_tab(window: MainWindow, path: Path) -> DocumentTab:
    window.open_paths([str(path)])
    tab = window.current_tab()
    assert tab is not None
    tab.model.set_field_value("name", "Jane Ndlovu")
    tab.model.add_item(OverlayItem("text", 0, (320, 330, 480, 346), text="Signed at Cape Town"))
    return tab


def test_signed_copy_from_the_header(
    qtbot: QtBot, window: MainWindow, form_pdf: Path, confirmed: list[str]
) -> None:
    from PySide6.QtCore import Qt

    original = form_pdf.read_bytes()
    tab = filled_tab(window, form_pdf)
    button = window.header.signed_copy_button
    assert button.toolTip() == "Save signed copy" and button.accessibleName() == "Save signed copy"
    layout = window.header.layout()
    assert (
        layout is not None
        and layout.indexOf(button) == layout.indexOf(window.header.save_button) + 1
    )
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    copy = form_pdf.parent / f"form{SUFFIX}.pdf"
    assert confirmed == [copy.name]
    assert form_pdf.read_bytes() == original  # the original is untouched
    flat = pymupdf.open(copy)
    assert (
        sum(1 for p in flat for _ in p.widgets()) == 0
        and sum(1 for p in flat for _ in p.annots()) == 0
    )
    assert "Jane Ndlovu" in flat[0].get_text() and "Signed at Cape Town" in flat[0].get_text()
    # The original tab stays open, editable and unsaved.
    assert window.current_tab() is tab and tab.model.dirty and len(window.tabs) == 1
    assert len(tab.model.items) == 1

    # Again: a second copy, numbered, the first left alone.
    first = copy.read_bytes()
    window.header.signed_copy_action.trigger()  # the menu entry does the same
    assert (form_pdf.parent / f"form{SUFFIX} (2).pdf").exists() and copy.read_bytes() == first


def test_toast_open_and_show_in_folder(
    monkeypatch: pytest.MonkeyPatch, window: MainWindow, form_pdf: Path, confirmed: list[str]
) -> None:
    from pdr_sign.ui import desktop

    shown: list[Path] = []
    monkeypatch.setattr(desktop, "show_in_folder", shown.append)
    tab = filled_tab(window, form_pdf)
    window.header.signed_copy_requested.emit()
    toast = tab.view.action_toast
    assert toast.isVisible() and toast.label.text() == "Signed copy saved"
    labels = [b.text() for b in toast.buttons]
    assert labels == ["Open", "Show in folder"]
    toast.buttons[1].click()
    assert shown == [form_pdf.parent / f"form{SUFFIX}.pdf"]
    window.header.signed_copy_requested.emit()
    window.current_tab().view.action_toast.buttons[0].click()  # type: ignore[union-attr]
    assert len(window.tabs) == 2  # opened in a new tab
    assert window.tabs[1].doc.path.name == f"form{SUFFIX} (2).pdf"
    assert window.tabs[0].model.dirty  # the original is still unsaved


def test_cancel_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, window: MainWindow, form_pdf: Path
) -> None:
    monkeypatch.setattr(dialogs, "confirm_signed_copy", lambda *_: False)
    filled_tab(window, form_pdf)
    window.header.signed_copy_requested.emit()
    assert not list(form_pdf.parent.glob(f"*{SUFFIX}*"))


def test_unwritable_folder_asks_where(
    monkeypatch: pytest.MonkeyPatch,
    window: MainWindow,
    form_pdf: Path,
    tmp_path: Path,
    confirmed: list[str],
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "picked.pdf").write_bytes(b"keep me")
    asked: list[Path] = []
    monkeypatch.setattr(
        dialogs,
        "ask_save_path",
        lambda _p, _t, suggested: (asked.append(suggested), elsewhere / "picked.pdf")[1],
    )
    tab = filled_tab(window, form_pdf)
    folder = form_pdf.parent
    folder.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        if os.access(folder, os.W_OK):
            pytest.skip("running as a user who can write anywhere")
        window.header.signed_copy_requested.emit()
    finally:
        folder.chmod(stat.S_IRWXU)
    assert asked and asked[0].name == f"form{SUFFIX}.pdf"  # suggested in the home folder
    assert (elsewhere / "picked.pdf").read_bytes() == b"keep me"  # never overwritten
    assert confirmed == ["picked (2).pdf"] and (elsewhere / "picked (2).pdf").exists()
    assert tab.model.dirty


def test_panel_has_no_flatten_button(window: MainWindow, form_pdf: Path) -> None:
    tab = filled_tab(window, form_pdf)
    assert not hasattr(tab.panel, "flatten_button")
