"""The print dialog: printer, pages, copies, paper, orientation and scaling in one view.

Qt's own dialog hides scaling behind a tab and paper/orientation behind "Properties";
this one shows everything at once, follows the app theme, and explains the one-time
`snap connect` when a confined snap can't reach CUPS.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign import APP_COMMAND
from pdr_sign.ui.stepper import Stepper
from pdr_sign.ui.theme import LIGHT, SPACING, Tokens

PDF_TARGET = "Save as PDF"
SNAP_PRINT_COMMAND = f"sudo snap connect {APP_COMMAND}:cups-control"
SNAP_PRINT_MESSAGE = f"To print from PDR Sign, run this once in a terminal: {SNAP_PRINT_COMMAND}"
ORIENTATIONS = ("Automatic", "Portrait", "Landscape")
DUPLEX = {
    "Off": QPrinter.DuplexMode.DuplexNone,
    "Long edge": QPrinter.DuplexMode.DuplexLongSide,
    "Short edge": QPrinter.DuplexMode.DuplexShortSide,
}


def parse_ranges(text: str, page_count: int) -> list[int] | None:
    """ "1-3, 5" -> [0, 1, 2, 4] (0-based, in order, no repeats); None if invalid."""
    pages: list[int] = []
    parts = [p.strip() for p in re.split(r"[,;]", text) if p.strip()]
    if not parts:
        return None
    for part in parts:
        match = re.fullmatch(r"(\d+)\s*(?:[-–]\s*(\d+))?", part)
        if match is None:
            return None
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if not 1 <= first <= last <= page_count:
            return None
        for number in range(first, last + 1):
            if number - 1 not in pages:
                pages.append(number - 1)
    return pages


def locale_page_size() -> QPageSize:
    """The paper size Qt picks for this locale (Letter in the US and Canada, else A4)."""
    return QPrinter().pageLayout().pageSize()


def snap_printing_blocked() -> bool:
    """Inside a strict snap with neither the cups nor the cups-control plug connected."""
    if "SNAP_NAME" not in os.environ:
        return False
    snapctl = shutil.which("snapctl")
    if snapctl is None:
        return False
    for plug in ("cups-control", "cups"):
        try:
            done = subprocess.run(
                [snapctl, "is-connected", plug], capture_output=True, timeout=3, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if done.returncode == 0:
            return False
    return True


@dataclass
class PrintChoices:
    printer: str  # a CUPS printer name, or PDF_TARGET
    pages: list[int]
    copies: int
    collate: bool
    fit: bool
    auto_rotate: bool
    orientation: QPageLayout.Orientation
    page_size: QPageSize
    duplex: QPrinter.DuplexMode
    grayscale: bool


class PrintDialog(QDialog):
    def __init__(
        self,
        title: str,
        page_count: int,
        current: int,
        printers: list[QPrinterInfo] | None = None,
        blocked: bool | None = None,
        parent: QWidget | None = None,
        tokens: Tokens = LIGHT,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        self.page_count = page_count
        self.current = current
        self.printers = QPrinterInfo.availablePrinters() if printers is None else printers
        self.blocked = snap_printing_blocked() if blocked is None else blocked

        # printer
        self.printer_box = QComboBox()
        self.printer_box.setAccessibleName("Printer")
        default = QPrinterInfo.defaultPrinterName()
        for info in self.printers:
            self.printer_box.addItem(info.description() or info.printerName(), info.printerName())
        self.printer_box.addItem(PDF_TARGET, PDF_TARGET)
        names = [i.printerName() for i in self.printers]
        self.printer_box.setCurrentIndex(names.index(default) if default in names else 0)
        self.printer_note = QLabel()
        self.printer_note.setObjectName("Muted")
        self.printer_note.setWordWrap(True)

        # pages
        self.all_pages = QRadioButton(f"All {page_count} pages")
        self.current_page = QRadioButton(f"Current page ({current + 1})")
        self.range_pages = QRadioButton("Pages")
        self.range_field = QLineEdit()
        self.range_field.setPlaceholderText(f"e.g. 1–3, 5 (of {page_count})")
        self.range_field.setAccessibleName("Page range")
        self.range_error = QLabel(f"Use page numbers from 1 to {page_count}, like 1–3, 5.")
        self.range_error.setObjectName("Muted")
        self.range_error.setWordWrap(True)
        self.all_pages.setChecked(True)
        page_group = QButtonGroup(self)
        for button in (self.all_pages, self.current_page, self.range_pages):
            page_group.addButton(button)
            button.toggled.connect(self._validate)
        self.range_field.textEdited.connect(lambda _t: self.range_pages.setChecked(True))
        self.range_field.textChanged.connect(self._validate)
        range_row = QHBoxLayout()
        range_row.addWidget(self.range_pages)
        range_row.addWidget(self.range_field, 1)
        pages_col = QVBoxLayout()
        pages_col.setSpacing(SPACING // 2)
        pages_col.addWidget(self.all_pages)
        pages_col.addWidget(self.current_page)
        pages_col.addLayout(range_row)
        pages_col.addWidget(self.range_error)

        self.copies = Stepper(1, 999, 1, "", "Copies")
        self.copies.set_tokens(tokens)
        self.collate = QCheckBox("Collate")
        self.collate.setChecked(True)
        copies_row = QHBoxLayout()
        copies_row.addWidget(self.copies)
        copies_row.addWidget(self.collate)
        copies_row.addStretch()

        # page setup
        self.paper = QComboBox()
        self.paper.setAccessibleName("Paper")
        self.orientation = QComboBox()
        self.orientation.addItems(ORIENTATIONS)
        self.orientation.setAccessibleName("Orientation")
        self.orientation.setToolTip("Automatic turns each page to use the whole sheet.")
        self.fit = QRadioButton("Fit to page")
        self.actual = QRadioButton("Actual size")
        self.fit.setChecked(True)
        scale_group = QButtonGroup(self)
        scale_group.addButton(self.fit)
        scale_group.addButton(self.actual)
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.fit)
        scale_row.addWidget(self.actual)
        scale_row.addStretch()
        self.duplex = QComboBox()
        self.duplex.addItems(list(DUPLEX))
        self.duplex.setAccessibleName("Two-sided")
        self.color = QComboBox()
        self.color.addItems(["Colour", "Black and white"])
        self.color.setAccessibleName("Colour")

        left = QFormLayout()
        left.setSpacing(SPACING * 3 // 2)
        left.addRow("Printer", self.printer_box)
        left.addRow("", self.printer_note)
        left.addRow("Pages", pages_col)
        left.addRow("Copies", copies_row)
        right = QFormLayout()
        right.setSpacing(SPACING * 3 // 2)
        right.addRow("Paper", self.paper)
        right.addRow("Orientation", self.orientation)
        right.addRow("Scaling", scale_row)
        right.addRow("Two-sided", self.duplex)
        right.addRow("Colour", self.color)
        columns = QHBoxLayout()
        columns.setSpacing(SPACING * 4)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)

        # snap without CUPS access
        self.snap_banner = QFrame()
        self.snap_banner.setObjectName("Banner")
        banner_row = QHBoxLayout(self.snap_banner)
        banner_text = QLabel(SNAP_PRINT_MESSAGE)
        banner_text.setWordWrap(True)
        banner_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_command = QPushButton("Copy")
        self.copy_command.setAccessibleName("Copy the snap connect command")
        self.copy_command.clicked.connect(self._copy_command)
        banner_row.addWidget(banner_text, 1)
        banner_row.addWidget(self.copy_command)
        self.snap_banner.setVisible(self.blocked)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.print_button = QPushButton("Print")
        self.print_button.setProperty("primary", True)
        self.print_button.setDefault(True)
        self.print_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.print_button)

        column = QVBoxLayout(self)
        column.setContentsMargins(SPACING * 3, SPACING * 3, SPACING * 3, SPACING * 2)
        column.setSpacing(SPACING * 2)
        column.addWidget(self.snap_banner)
        column.addLayout(columns)
        column.addLayout(buttons)

        self.printer_box.currentIndexChanged.connect(self._printer_changed)
        self._printer_changed()
        self._validate()

    # --- state ---------------------------------------------------------------

    def _info(self) -> QPrinterInfo | None:
        name = self.printer_box.currentData()
        return next((i for i in self.printers if i.printerName() == name), None)

    def _printer_changed(self, *_: object) -> None:
        info = self._info()
        previous = self.paper.currentData()
        self.paper.clear()
        sizes = info.supportedPageSizes() if info is not None else []
        if not sizes:  # Save as PDF (or a printer that lists none)
            ids = QPageSize.PageSizeId
            sizes = [QPageSize(i) for i in (ids.A4, ids.Letter, ids.Legal, ids.A3, ids.A5)]
        for size in sizes:
            self.paper.addItem(size.name(), size)
        wanted = previous if isinstance(previous, QPageSize) else None
        if wanted is None:  # the printer's default, else the locale's (A4 or Letter)
            wanted = info.defaultPageSize() if info is not None else locale_page_size()
        for index in range(self.paper.count()):
            if wanted is not None and self.paper.itemData(index).isEquivalentTo(wanted):
                self.paper.setCurrentIndex(index)
                break
        duplex_modes = info.supportedDuplexModes() if info is not None else []
        two_sided = any(m != QPrinter.DuplexMode.DuplexNone for m in duplex_modes)
        self.duplex.setEnabled(two_sided)
        if not two_sided:
            self.duplex.setCurrentIndex(0)
        if info is None:
            self.printer_note.setText("Choose where to save the PDF after pressing Print.")
        else:
            details = [d for d in (info.location(), info.makeAndModel()) if d]
            self.printer_note.setText(" · ".join(details))

    def _validate(self, *_: object) -> None:
        bad = self.range_pages.isChecked() and self.selected_pages() is None
        self.range_error.setVisible(bad)
        self.print_button.setEnabled(not bad)

    def _copy_command(self) -> None:
        from pdr_sign.ui.canvas import clipboard

        clipboard().setText(SNAP_PRINT_COMMAND)
        self.copy_command.setText("Copied")

    def selected_pages(self) -> list[int] | None:
        if self.current_page.isChecked():
            return [self.current]
        if self.range_pages.isChecked():
            return parse_ranges(self.range_field.text(), self.page_count)
        return list(range(self.page_count))

    def choices(self) -> PrintChoices:
        pages = self.selected_pages() or []
        orientation = self.orientation.currentText()
        landscape = orientation == "Landscape"
        return PrintChoices(
            printer=str(self.printer_box.currentData()),
            pages=pages,
            copies=self.copies.value(),
            collate=self.collate.isChecked(),
            fit=self.fit.isChecked(),
            auto_rotate=orientation == "Automatic",
            orientation=QPageLayout.Orientation.Landscape
            if landscape
            else QPageLayout.Orientation.Portrait,
            page_size=self.paper.currentData(),
            duplex=DUPLEX[self.duplex.currentText()],
            grayscale=self.color.currentIndex() == 1,
        )


def apply_choices(printer: QPrinter, choices: PrintChoices) -> None:
    """Configure ``printer`` (output file is set by the caller for PDF_TARGET)."""
    if choices.printer == PDF_TARGET:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    else:
        printer.setOutputFormat(QPrinter.OutputFormat.NativeFormat)
        printer.setOutputFileName("")
        printer.setPrinterName(choices.printer)
    printer.setPageSize(choices.page_size)
    printer.setPageOrientation(choices.orientation)
    printer.setCopyCount(choices.copies)
    printer.setCollateCopies(choices.collate)
    printer.setDuplex(choices.duplex)
    printer.setColorMode(
        QPrinter.ColorMode.GrayScale if choices.grayscale else QPrinter.ColorMode.Color
    )
