"""``pdr-sign --self-test FOLDER [--show-in-folder]``: check an installed PDR Sign works.

Meant for packaging checks (snap, .deb, AppImage, test VMs): it runs the real save
pipeline and print path inside whatever runtime the package provides, without
needing anyone to click through dialogs. Everything is written into FOLDER, which is
created if needed; nothing else is touched.
"""

from __future__ import annotations

import io
import os
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

CheckResult = tuple[bool, str]


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    from PIL import Image

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((*rgb, 255), (0, height // 2 - 4, width, height // 2 + 4))
    image.paste((*rgb, 255), (0, 0, 8, height))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _make_form(path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 60), "PDR Sign self-test form", fontsize=16)
    widget = pymupdf.Widget()
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT  # type: ignore[attr-defined]
    widget.field_name = "name"
    widget.rect = pymupdf.Rect(72, 80, 300, 100)
    page.add_widget(widget)
    doc.save(path)
    return path


def run(folder: Path, show_in_folder: bool = False) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from pdr_sign import __version__
    from pdr_sign.services import forms, saving, stamps
    from pdr_sign.services.document import Document
    from pdr_sign.services.saving import SaveRequest
    from pdr_sign.services.stamps import OverlayItem

    _app = QApplication.instance() or QApplication([])  # printing needs one alive
    folder = folder.expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    print(f"PDR Sign {__version__} self-test in {folder}")
    if "SNAP_NAME" in os.environ:
        runtime = f"snap {os.environ['SNAP_NAME']}"
    else:
        runtime = "appimage" if "APPIMAGE" in os.environ else "native"
    print(f"  runtime: {runtime}, Qt platform {QGuiApplication.platformName()}")

    original = _make_form(folder / "pdr-selftest.pdf")
    items = [
        OverlayItem("text", 0, (72, 140, 300, 156), text="Self-test text"),
        OverlayItem("line", 0, (72, 180, 250, 180)),
        OverlayItem("signature", 0, (72, 220, 272, 280), image=_png(400, 120, (0, 0, 0))),
        OverlayItem(
            "stamp",
            0,
            (320, 220, 433, 276),
            image=_png(400, 200, (200, 30, 30)),
            rotation=20,
            opacity=0.7,
        ),
    ]

    def save() -> CheckResult:
        doc = Document.open(original)
        result = saving.save(doc, original, SaveRequest({"name": "Ada"}, items))
        doc.close()
        again = Document.open(original)
        name = forms.field_values(forms.list_fields(again))["name"]
        kinds = sorted(i.kind for i in stamps.read_overlays(again))
        again.close()
        ok = name == "Ada" and kinds == ["line", "text"]
        mode = "incremental" if result.incremental else "full"
        return ok, f"saved ({mode}), reopened: {name!r}, {kinds}"

    def signed_copy() -> CheckResult:
        doc = Document.open(original)
        first = saving.save(
            doc, saving.signed_copy_path(original), SaveRequest(flatten=True), overwrite=False
        )
        second = saving.save(
            doc, saving.signed_copy_path(original), SaveRequest(flatten=True), overwrite=False
        )
        doc.close()
        # A rerun in the same folder numbers on from the copies already there.
        numbered = second.path.stem.endswith(")") and " (" in second.path.stem
        ok = first.path != second.path and first.path.exists() and numbered
        if show_in_folder:  # opens the file manager on the user's screen
            from pdr_sign.ui import desktop

            desktop.show_in_folder(second.path)
        return ok, f"{first.path.name} and {second.path.name}"

    def print_to_pdf() -> CheckResult:
        from PySide6.QtGui import QPageSize
        from PySide6.QtPrintSupport import QPrinter

        from pdr_sign.ui.printing import print_document

        target = folder / "pdr-selftest-print.pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setOutputFileName(str(target))
        doc = Document.open(original)
        ok = print_document(doc, printer, [0])
        doc.close()
        return ok and target.stat().st_size > 1000, f"{target.name}, {target.stat().st_size} bytes"

    def printers() -> CheckResult:
        from PySide6.QtPrintSupport import QPrinterInfo

        names = QPrinterInfo.availablePrinterNames()
        return True, f"{len(names)} system printer(s): {', '.join(names) or 'none configured'}"

    def support_qr() -> CheckResult:
        from pdr_sign.services.support import ZCASH_ADDRESS, is_zcash_transparent_address
        from pdr_sign.ui.welcome_dialog import WelcomeDialog

        dialog = WelcomeDialog()
        size = dialog.qr.pixmap().width()
        dialog.deleteLater()
        ok = size > 0 and is_zcash_transparent_address(ZCASH_ADDRESS)
        return ok, f"QR {size} px, address checksum ok"

    checks: list[tuple[str, Callable[[], CheckResult]]] = [
        ("save + reopen", save),
        ("save signed copy (no overwrite)", signed_copy),
        ("print to PDF", print_to_pdf),
        ("printers (CUPS)", printers),
        ("welcome window (QR code)", support_qr),
    ]
    failed = 0
    for label, check in checks:
        try:
            ok, detail = check()
        except Exception:
            ok, detail = False, traceback.format_exc(limit=3).strip().splitlines()[-1]
        failed += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] {label}: {detail}")
    print("self-test passed" if not failed else f"self-test FAILED ({failed})")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    show = "--show-in-folder" in argv
    rest = [a for a in argv if a != "--show-in-folder"]
    folder = Path(rest[0]) if rest else Path.home() / "pdr-selftest"
    return run(folder, show_in_folder=show)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
