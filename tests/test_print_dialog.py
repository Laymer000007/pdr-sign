"""The single print dialog: everything visible at once, ranges, snap hint, output."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPageLayout
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QPushButton, QWidget
from pytestqt.qtbot import QtBot

from pdr_sign.services.document import Document
from pdr_sign.ui import dialogs, print_dialog, printing
from pdr_sign.ui.print_dialog import (
    PDF_TARGET,
    SNAP_PRINT_COMMAND,
    SNAP_PRINT_MESSAGE,
    PrintDialog,
    parse_ranges,
)


def make(qtbot: QtBot, blocked: bool = False, current: int = 2) -> PrintDialog:
    dialog = PrintDialog("Print", 6, current, printers=[], blocked=blocked)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


def test_ranges() -> None:
    assert parse_ranges("1-3, 5", 6) == [0, 1, 2, 4]
    assert parse_ranges("2–4;4,1", 6) == [1, 2, 3, 0]
    assert parse_ranges("5-3", 6) is None
    assert parse_ranges("0", 6) is None
    assert parse_ranges("7", 6) is None
    assert parse_ranges("a", 6) is None
    assert parse_ranges("", 6) is None


def test_everything_is_visible_at_once_without_options_button(qtbot: QtBot) -> None:
    dialog = make(qtbot)
    for widget in (
        dialog.printer_box,
        dialog.all_pages,
        dialog.current_page,
        dialog.range_field,
        dialog.copies,
        dialog.paper,
        dialog.orientation,
        dialog.fit,
        dialog.actual,
        dialog.print_button,
    ):
        assert widget.isVisible(), widget
    labels = [b.text() for b in dialog.findChildren(QPushButton)]
    assert not any("Options" in t for t in labels)
    assert dialog.width() >= 640
    assert dialog.current_page.text() == "Current page (3)"


def test_pages_choice(qtbot: QtBot) -> None:
    dialog = make(qtbot)
    assert dialog.choices().pages == list(range(6))
    dialog.current_page.setChecked(True)
    assert dialog.choices().pages == [2]
    qtbot.keyClicks(dialog.range_field, "2-3")
    assert dialog.range_pages.isChecked()  # typing a range selects it
    assert dialog.choices().pages == [1, 2]
    dialog.range_field.setText("9")
    assert not dialog.print_button.isEnabled() and dialog.range_error.isVisible()


def test_defaults_match_previous_output(qtbot: QtBot) -> None:
    choices = make(qtbot).choices()
    assert choices.printer == PDF_TARGET  # no printers given
    assert choices.fit and choices.auto_rotate and choices.copies == 1
    assert choices.orientation == QPageLayout.Orientation.Portrait


def test_forced_landscape(qtbot: QtBot) -> None:
    dialog = make(qtbot)
    dialog.orientation.setCurrentText("Landscape")
    choices = dialog.choices()
    assert not choices.auto_rotate
    assert choices.orientation == QPageLayout.Orientation.Landscape


def test_snap_hint_with_copy(qtbot: QtBot, fake_clipboard: Any) -> None:
    assert make(qtbot).snap_banner.isHidden()
    dialog = make(qtbot, blocked=True)
    assert dialog.snap_banner.isVisible()
    assert SNAP_PRINT_MESSAGE == (
        "To print from PDR Sign, run this once in a terminal: "
        "sudo snap connect pdr-sign:cups-control"
    )
    qtbot.mouseClick(dialog.copy_command, Qt.MouseButton.LeftButton)
    assert fake_clipboard.text() == SNAP_PRINT_COMMAND
    assert dialog.copy_command.text() == "Copied"


def test_snap_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SNAP_NAME", raising=False)
    assert not print_dialog.snap_printing_blocked()
    monkeypatch.setenv("SNAP_NAME", "pdr-sign")
    monkeypatch.setattr(print_dialog.shutil, "which", lambda _n: "/usr/bin/snapctl")
    connected: set[str] = set()

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args, 0 if args[-1] in connected else 1)

    monkeypatch.setattr(print_dialog.subprocess, "run", fake_run)
    assert print_dialog.snap_printing_blocked()
    connected.add("cups-control")
    assert not print_dialog.snap_printing_blocked()
    connected.clear()
    connected.add("cups")
    assert not print_dialog.snap_printing_blocked()


def test_save_as_pdf_prints_the_chosen_pages(
    qtbot: QtBot, text_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "printed.pdf"
    monkeypatch.setattr(dialogs, "ask_save_path", lambda *_: out)

    def accept_with_range(dialog: PrintDialog) -> int:
        dialog.range_field.setText("2-3")
        dialog.range_pages.setChecked(True)
        return int(PrintDialog.DialogCode.Accepted)

    monkeypatch.setattr(PrintDialog, "exec", accept_with_range)
    monkeypatch.setattr(print_dialog, "snap_printing_blocked", lambda: False)
    monkeypatch.setattr(print_dialog.QPrinterInfo, "availablePrinters", staticmethod(list))
    parent = QWidget()
    qtbot.addWidget(parent)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    doc = Document.open(text_pdf)
    printing.run_print_dialog(parent, printer, doc, 0)
    doc.close()
    with pymupdf.open(out) as pdf:
        assert pdf.page_count == 2


def test_pdf_paper_follows_locale(qtbot: QtBot) -> None:
    dialog = make(qtbot)
    assert dialog.paper.currentData().isEquivalentTo(print_dialog.locale_page_size())
