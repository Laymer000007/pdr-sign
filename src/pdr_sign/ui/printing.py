"""Printing through QPrintDialog: each page is rendered at 300 dpi and painted on the printer.

Pages whose orientation doesn't match the paper are turned 90° so they use the
whole sheet. Scaling is "Fit to page" (default) or "Actual size".
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QButtonGroup,
    QProgressDialog,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services.document import Document, DocumentError

PRINT_DPI = 300


def pages_to_print(printer: QPrinter, page_count: int, current: int) -> list[int]:
    """0-based page indices chosen in the dialog (all, a range list, or the current one)."""
    mode = printer.printRange()
    if mode == QPrinter.PrintRange.CurrentPage:
        return [current]
    if mode == QPrinter.PrintRange.PageRange:
        pages: list[int] = []
        for r in printer.pageRanges().toRangeList():
            for number in range(max(1, r.from_), min(page_count, r.to) + 1):
                if number - 1 not in pages:
                    pages.append(number - 1)
        return pages
    return list(range(page_count))


def render_page(doc: Document, index: int, dpi: int = PRINT_DPI) -> QImage:
    tile = doc.render_tile(index, dpi / 72, 1.0)
    return QImage(
        tile.data, tile.width, tile.height, tile.stride, QImage.Format.Format_RGB888
    ).copy()


def placement(
    page_w: float, page_h: float, paper: QRectF, dpi: float, fit: bool
) -> tuple[QRectF, bool]:
    """Target rect (centred on the origin, device px) and whether to rotate by 90°."""
    rotate = (page_w > page_h) != (paper.width() > paper.height())
    w_in, h_in = (page_h, page_w) if rotate else (page_w, page_h)
    w, h = w_in / 72 * dpi, h_in / 72 * dpi  # actual size in device pixels
    if fit:
        scale = min(paper.width() / w, paper.height() / h)
        w, h = w * scale, h * scale
    if rotate:
        w, h = h, w  # drawn in the rotated coordinate system
    return QRectF(-w / 2, -h / 2, w, h), rotate


def print_document(
    doc: Document,
    printer: QPrinter,
    pages: list[int],
    fit: bool = True,
    progress: Callable[[int], bool] | None = None,
) -> bool:
    """Paint ``pages`` onto ``printer``. Returns False if cancelled or it failed."""
    if not pages:
        return False
    painter = QPainter()
    if not painter.begin(printer):
        return False
    try:
        paper = QRectF(painter.viewport())
        dpi = printer.resolution()
        for n, index in enumerate(pages):
            if n and not printer.newPage():
                return False
            info = doc.pages[index]
            target, rotate = placement(info.width, info.height, paper, dpi, fit)
            image = render_page(doc, index)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.translate(paper.center())
            if rotate:
                painter.rotate(-90)  # top edge to the left, as CUPS does for landscape
            painter.drawImage(target, image)
            painter.restore()
            if progress is not None and not progress(n + 1):
                printer.abort()
                return False
        return True
    except (DocumentError, RuntimeError, ValueError):
        printer.abort()
        return False
    finally:
        painter.end()


class ScalingOptions(QWidget):
    """Extra tab in the print dialog."""

    def __init__(self, fit: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Scaling")
        self.fit = QRadioButton("Fit to page")
        self.actual = QRadioButton("Actual size")
        (self.fit if fit else self.actual).setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.fit)
        group.addButton(self.actual)
        layout = QVBoxLayout(self)
        layout.addWidget(self.fit)
        layout.addWidget(self.actual)
        layout.addStretch()


def run_print_dialog(parent: QWidget, printer: QPrinter, doc: Document, current: int) -> None:
    """Ask for printer, range and scaling, then print with a cancellable progress dialog."""
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(f"Print “{doc.path.name}”")
    option = QAbstractPrintDialog.PrintDialogOption
    dialog.setOptions(option.PrintPageRange | option.PrintCurrentPage | option.PrintToFile)
    dialog.setMinMax(1, doc.page_count)
    scaling = ScalingOptions()
    dialog.setOptionTabs([scaling])
    if dialog.exec() != QPrintDialog.DialogCode.Accepted:
        return
    pages = pages_to_print(printer, doc.page_count, current)
    progress = QProgressDialog("Preparing pages…", "Cancel", 0, len(pages), parent)
    progress.setWindowTitle("Printing")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(400)

    def step(done: int) -> bool:
        progress.setValue(done)
        progress.setLabelText(f"Page {done} of {len(pages)}")
        return not progress.wasCanceled()

    print_document(doc, printer, pages, scaling.fit.isChecked(), step)
    progress.close()
