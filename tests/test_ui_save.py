"""Phase 5 in the UI: Save / Save As / flattened copy, prompts, reload, settings."""

from __future__ import annotations

import contextlib
import io
import stat
from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services import forms, saving, stamps
from pdr_sign.services.document import Document
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui import dialogs
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from tests.conftest import trigger_shortcut


def png() -> bytes:
    image = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
    image.paste((0, 0, 0, 255), (0, 27, 200, 33))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


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


def open_tab(window: MainWindow, path: Path) -> DocumentTab:
    window.open_paths([str(path)])
    tab = window.current_tab()
    assert tab is not None
    return tab


def fill(tab: DocumentTab) -> None:
    m = tab.model
    m.set_field_value("name", "Jane Ndlovu")
    m.add_item(OverlayItem("text", 0, (320, 330, 480, 346), text="Signed at Cape Town"))
    m.add_item(OverlayItem("line", 0, (100, 400, 250, 400)))
    m.add_item(OverlayItem("signature", 1, (300, 700, 500, 750), image=png()))


def test_save_button_follows_unsaved_changes(
    qtbot: QtBot, window: MainWindow, form_pdf: Path
) -> None:
    tab = open_tab(window, form_pdf)
    save = window.header.save_button
    assert not save.isEnabled()
    fill(tab)
    assert save.isEnabled()
    trigger_shortcut(window, "Ctrl+Z")
    trigger_shortcut(window, "Ctrl+Z")
    trigger_shortcut(window, "Ctrl+Z")
    trigger_shortcut(window, "Ctrl+Z")
    assert not save.isEnabled()  # undone back to the saved state


def test_save_reloads_with_items_editable(qtbot: QtBot, window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    fill(tab)
    qtbot.mouseClick(window.header.save_button, Qt.MouseButton.LeftButton)
    new = window.current_tab()
    assert new is not None and new is not tab  # reloaded from the written file
    assert not new.model.dirty and not window.header.save_button.isEnabled()
    assert new.model.values["name"] == "Jane Ndlovu"
    kinds = sorted(i.kind for i in new.model.items.values())
    assert kinds == ["line", "text"]  # editable again; the signature is now page content
    with new.doc.locked() as pdf:
        assert len(pdf[1].get_image_info()) == 1
        assert list(pdf[0].annots()) == []  # editable items aren't drawn twice
    assert not list(form_pdf.parent.glob("*.pdr-*"))


def test_ctrl_s_saves_and_window_title_clears(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    tab.model.set_field_value("name", "Ada")
    assert window.windowTitle().startswith("• ")
    trigger_shortcut(window, "Ctrl+S")
    assert not window.windowTitle().startswith("• ")
    assert forms.field_values(forms.list_fields(Document.open(form_pdf)))["name"] == "Ada"


def test_read_only_file_falls_back_to_save_as(
    monkeypatch: pytest.MonkeyPatch,
    window: MainWindow,
    form_pdf: Path,
    tmp_path: Path,
    no_save_dialogs: dict[str, list[object]],
) -> None:
    tab = open_tab(window, form_pdf)
    tab.model.set_field_value("name", "Ada")
    original = form_pdf.read_bytes()
    form_pdf.chmod(stat.S_IRUSR)
    target = tmp_path / "copy.pdf"
    monkeypatch.setattr(
        dialogs,
        "ask_save_path",
        lambda _p, title, _s: (no_save_dialogs["path"].append(title), target)[1],
    )
    try:
        trigger_shortcut(window, "Ctrl+S")
    finally:
        form_pdf.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert no_save_dialogs["path"] == ["This file can't be changed here. Save a copy:"]
    assert form_pdf.read_bytes() == original
    current = window.current_tab()
    assert current is not None and current.doc.path == target and not current.model.dirty


@pytest.mark.parametrize("answer", ["cancel", "save_as", "save"])
def test_signed_document_warning(
    monkeypatch: pytest.MonkeyPatch,
    window: MainWindow,
    signed_pdf: Path,
    tmp_path: Path,
    answer: str,
) -> None:
    tab = open_tab(window, signed_pdf)
    assert tab.signed
    tab.model.set_field_value("name", "Ada")
    original = signed_pdf.read_bytes()
    asked: list[bool] = []
    monkeypatch.setattr(dialogs, "confirm_signed", lambda _p: (asked.append(True), answer)[1])
    monkeypatch.setattr(dialogs, "ask_save_path", lambda *_: tmp_path / "copy.pdf")
    trigger_shortcut(window, "Ctrl+S")
    assert asked == [True]
    if answer == "cancel":
        assert signed_pdf.read_bytes() == original and tab.model.dirty
    elif answer == "save_as":
        assert signed_pdf.read_bytes() == original  # the signed original is kept
        assert (tmp_path / "copy.pdf").exists()
    else:
        assert signed_pdf.read_bytes() != original


@pytest.mark.parametrize("answer", ["cancel", "discard", "save"])
def test_closing_with_unsaved_changes(
    monkeypatch: pytest.MonkeyPatch, window: MainWindow, form_pdf: Path, answer: str
) -> None:
    tab = open_tab(window, form_pdf)
    tab.model.set_field_value("name", "Ada")
    original = form_pdf.read_bytes()
    monkeypatch.setattr(dialogs, "ask_unsaved", lambda _p, _n: answer)
    closed = window.close_tab(tab)
    assert closed is (answer != "cancel")
    assert (form_pdf.read_bytes() == original) is (answer != "save")
    if answer == "save":
        assert forms.field_values(forms.list_fields(Document.open(form_pdf)))["name"] == "Ada"


def test_window_close_can_be_cancelled(
    monkeypatch: pytest.MonkeyPatch, window: MainWindow, form_pdf: Path
) -> None:
    tab = open_tab(window, form_pdf)
    tab.model.set_field_value("name", "Ada")
    monkeypatch.setattr(dialogs, "ask_unsaved", lambda *_: "cancel")
    window.close()
    assert window.isVisible() and window.tabs == [tab]


def test_failed_save_reports_and_keeps_everything(
    monkeypatch: pytest.MonkeyPatch, window: MainWindow, form_pdf: Path
) -> None:
    tab = open_tab(window, form_pdf)
    tab.model.set_field_value("name", "Ada")
    original = form_pdf.read_bytes()
    errors: list[str] = []
    monkeypatch.setattr(dialogs, "show_error", lambda _p, _t, msg: errors.append(msg))

    def broken(*_: object) -> None:
        raise saving.VerificationError("The field “name” didn't keep its new value.")

    monkeypatch.setattr(saving, "verify", broken)
    trigger_shortcut(window, "Ctrl+S")
    assert form_pdf.read_bytes() == original
    assert errors and "original file was not changed" in errors[0]
    assert window.current_tab() is tab and tab.model.dirty


def test_flattened_copy_leaves_the_document_alone(
    monkeypatch: pytest.MonkeyPatch, window: MainWindow, form_pdf: Path, tmp_path: Path
) -> None:
    tab = open_tab(window, form_pdf)
    fill(tab)
    target = tmp_path / "flat.pdf"
    monkeypatch.setattr(dialogs, "ask_save_path", lambda *_: target)
    window.header.flatten_action.trigger()
    flat = pymupdf.open(target)
    assert (
        sum(1 for p in flat for _ in p.widgets()) == 0
        and sum(1 for p in flat for _ in p.annots()) == 0
    )
    assert "Jane Ndlovu" in flat[0].get_text()
    assert window.current_tab() is tab and tab.model.dirty  # still unsaved here
    tab.panel.flatten_button.click()  # the panel's Flatten does the same
    assert target.exists()


def test_xfa_banner(window: MainWindow, xfa_pdf: Path, form_pdf: Path) -> None:
    tab = open_tab(window, xfa_pdf)
    assert tab.xfa_banner.isVisible()
    assert "XFA" in tab.xfa_banner.label.text()
    tab.xfa_banner.close_button.click()
    assert not tab.xfa_banner.isVisible()
    plain = open_tab(window, form_pdf)
    assert not plain.xfa_banner.isVisible()


def test_settings_apply_live(
    qapp: QApplication, window: MainWindow, text_pdf: Path, tmp_path: Path
) -> None:
    from pdr_sign.services import settings as settings_service
    from pdr_sign.ui.settings_dialog import SettingsDialog
    from pdr_sign.ui.window_actions import apply_setting

    tab = open_tab(window, text_pdf)
    dialog = SettingsDialog(window.settings, lambda s, k: apply_setting(window, s, k), window)
    dialog.theme_buttons["dark"].click()
    assert window.tokens.scheme == "dark"
    dialog.ink_buttons["blue"].click()
    layer = tab.view.fill_layer
    assert layer is not None and layer.text_color == stamps.TEXT_COLORS["blue"]
    dialog.links.setChecked(True)
    folder = tmp_path / "other-sigs"
    dialog._set("signature_dir", str(folder))
    window.signatures.add("signature", png(), True)
    assert list(folder.glob("signature-*.png"))
    saved = settings_service.load()
    assert (saved.theme, saved.open_links_without_asking, saved.signature_dir) == (
        "dark",
        True,
        str(folder),
    )
    with contextlib.suppress(RuntimeError):
        dialog.theme_buttons["light"].click()


def test_reopened_items_are_not_drawn_twice(
    qtbot: QtBot, window: MainWindow, form_pdf: Path
) -> None:
    """Regression: tiles rendered before the saved annotations were stripped showed
    every reopened text, mark and line twice (pixels + editable overlay)."""
    doc = Document.open(form_pdf)
    saving.save(
        doc,
        form_pdf,
        saving.SaveRequest(
            items=[
                OverlayItem("text", 0, (100, 500, 300, 520), text="Only once"),
            ]
        ),
    )
    doc.close()
    tab = open_tab(window, form_pdf)
    tab.view.set_zoom(1.0)
    tab.view.go_to_page(0)
    assert window.scheduler.wait_idle()
    qtbot.wait(50)
    # Whatever the canvas rendered came from a page without the annotation.
    with tab.doc.locked() as pdf:
        assert list(pdf[0].annots()) == [] and "Only once" not in pdf[0].get_text()
    from pdr_sign.ui.page_item import tile_key

    view = tab.view
    key = tile_key(tab.doc, 0, view.render_zoom, view.devicePixelRatioF(), 0, 0)
    tile = window.scheduler.pixmap(key)
    assert tile is not None
    image = tile.toImage()
    scale = view.render_zoom * view.devicePixelRatioF()
    inked = [
        image.pixelColor(round(x * scale), round(y * scale)).lightness() < 128
        for x in range(100, 300, 2)
        for y in range(500, 520, 2)
        if round(x * scale) < image.width() and round(y * scale) < image.height()
    ]
    assert not any(inked)  # the text exists only as the editable overlay
