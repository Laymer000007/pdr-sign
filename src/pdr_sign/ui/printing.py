"""Printing: each page is rendered at 300 dpi and painted on the printer.

With "Automatic" orientation (the default), pages whose orientation doesn't match the
paper are turned 90° so they use the whole sheet. Scaling is "Fit to page" (default)
or "Actual size". The dialog itself is ``print_dialog.PrintDialog``.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QDialog, QProgressDialog, QWidget

from pdr_sign.services.document import Document, DocumentError
from pdr_sign.ui import dialogs
from pdr_sign.ui.print_dialog import PDF_TARGET, PrintDialog, apply_choices
from pdr_sign.ui.theme import LIGHT, Tokens

PRINT_DPI = 300


def render_page(doc: Document, index: int, dpi: int = PRINT_DPI) -> QImage:
    tile = doc.render_tile(index, dpi / 72, 1.0)
    return QImage(
        tile.data, tile.width, tile.height, tile.stride, QImage.Format.Format_RGB888
    ).copy()


def placement(
    page_w: float, page_h: float, paper: QRectF, dpi: float, fit: bool, auto_rotate: bool = True
) -> tuple[QRectF, bool]:
    """Target rect (centred on the origin, device px) and whether to rotate by 90°."""
    rotate = auto_rotate and (page_w > page_h) != (paper.width() > paper.height())
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
    auto_rotate: bool = True,
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
            target, rotate = placement(info.width, info.height, paper, dpi, fit, auto_rotate)
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


def run_print_dialog(
    parent: QWidget, printer: QPrinter, doc: Document, current: int, tokens: Tokens = LIGHT
) -> None:
    """Ask for printer, pages and page setup, then print with a cancellable progress."""
    title = f"Print “{doc.path.name}”"
    dialog = PrintDialog(title, doc.page_count, current, parent=parent, tokens=tokens)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    choices = dialog.choices()
    dialog.deleteLater()
    if not accepted:
        return
    if choices.printer == PDF_TARGET:
        target = dialogs.ask_save_path(
            parent, "Save as PDF", doc.path.with_name(f"{doc.path.stem} (printed).pdf")
        )
        if target is None:
            return
        printer.setOutputFileName(str(target))
    apply_choices(printer, choices)
    pages = choices.pages
    progress = QProgressDialog("Preparing pages…", "Cancel", 0, len(pages), parent)
    progress.setWindowTitle("Printing")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(400)

    def step(done: int) -> bool:
        progress.setValue(done)
        progress.setLabelText(f"Page {done} of {len(pages)}")
        return not progress.wasCanceled()

    print_document(doc, printer, pages, choices.fit, step, choices.auto_rotate)
    progress.close()
    progress.deleteLater()
