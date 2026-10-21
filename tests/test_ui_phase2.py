"""Search, text selection and printing (Phase 2)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPageSize
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services.document import Document
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.printing import pages_to_print, placement, print_document
from tests.conftest import FakeClipboard, trigger_shortcut


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    from pdr_sign.ui import dialogs

    monkeypatch.setattr(dialogs, "confirm_external_link", lambda *_: False)
    monkeypatch.setattr(dialogs, "show_error", lambda *_: None)


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    settings = Settings(theme="light", show_sidebar=True)
    w = build_window(configure(qapp, settings), settings, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w.show()
    qtbot.waitExposed(w)
    yield w
    for tab in list(w.tabs):
        w.close_tab(tab)


def open_tab(window: MainWindow, path: Path) -> DocumentTab:
    window.open_paths([str(path)])
    tab = window.current_tab()
    assert tab is not None
    return tab


# --- search -----------------------------------------------------------------


def test_search_streams_results_and_steps(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    trigger_shortcut(window, "Ctrl+F")
    assert tab.search_bar.isVisible()
    QTest.keyClicks(tab.search_bar.field, "page")
    QTest.keyClick(tab.search_bar.field, Qt.Key.Key_Return)  # search now, skip debounce
    qtbot.waitUntil(lambda: not tab.search.running and len(tab.search.hits) == 3, timeout=3000)
    qtbot.waitUntil(lambda: tab.search_bar.count.text() == "1 of 3", timeout=1000)
    assert [h.page for h in tab.search.hits] == [0, 1, 2]

    # Every hit is highlighted on its page; the current one separately.
    assert all(item.search_rects for item in tab.view.page_items)
    assert tab.view.page_items[0].current_hit is not None

    QTest.keyClick(tab.search_bar.field, Qt.Key.Key_Return)
    assert tab.search.current_index == 1 and tab.view.current_page == 1
    QTest.keyClick(tab.search_bar.field, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert tab.search.current_index == 0
    tab.search.step(-1)  # wraps
    assert tab.search.current_index == 2

    qtbot.waitUntil(lambda: tab.sidebar.search.list.count() == 3, timeout=1000)
    assert tab.sidebar.tabs.currentWidget() is tab.sidebar.search
    tab.sidebar.search.hit_activated.emit(1)
    assert tab.search.current_index == 1

    QTest.keyClick(tab.search_bar.field, Qt.Key.Key_Escape)
    assert not tab.search_bar.isVisible()
    assert not any(item.search_rects for item in tab.view.page_items)


def test_search_starts_at_current_page(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    tab.view.set_zoom(0.5)
    tab.view.go_to_page(2)
    tab.search.start("page", tab.view.current_page)
    qtbot.waitUntil(lambda: not tab.search.running, timeout=3000)
    current = tab.search.current
    assert current is not None and current.page == 2


def test_no_matches(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    tab.open_search()
    tab.search_bar.field.setText("zebra")
    QTest.keyClick(tab.search_bar.field, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: tab.search_bar.count.text() == "No matches", timeout=3000)


# --- selection ----------------------------------------------------------------


def test_drag_selects_and_copies(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, fake_clipboard: FakeClipboard
) -> None:
    tab = open_tab(window, text_pdf)
    view = tab.view
    view.set_zoom(1.0)
    view.go_to_page(0)
    words = tab.doc.words(0)
    first, last = words[0], words[3]  # "Page", "1", "The", "quick"

    def at(rect: tuple[float, float, float, float]) -> QPointF:
        return QPointF((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)

    start = view.mapFromScene(view.page_items[0].mapToScene(at(first.rect)))
    end = view.mapFromScene(view.page_items[0].mapToScene(at(last.rect)))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    for k in range(1, 5):
        QTest.mouseMove(view.viewport(), start + (end - start) * k / 4)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert view.selection.text() == "Page 1\nThe quick"
    assert view.page_items[0].selection_rects

    assert fake_clipboard.texts["selection"] == "Page 1\nThe quick"  # middle-click paste
    trigger_shortcut(window, "Ctrl+C")
    assert fake_clipboard.text() == "Page 1\nThe quick"

    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=end)  # click clears
    assert view.selection.is_empty and not view.page_items[0].selection_rects


def test_double_click_selects_word(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    view = tab.view
    view.set_zoom(1.0)
    view.go_to_page(0)
    word = next(w for w in tab.doc.words(0) if w.text == "quick")
    centre = QPointF((word.rect[0] + word.rect[2]) / 2, (word.rect[1] + word.rect[3]) / 2)
    pos = view.mapFromScene(view.page_items[0].mapToScene(centre))
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    assert view.selection.text() == "quick"


def test_selection_spans_pages(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    sel = tab.view.selection
    last = tab.doc.words(0)[-1]
    assert sel.begin(0, last.rect[0] + 1, last.rect[1] + 1)
    two = tab.doc.words(1)[1]  # "Page 2" heading on the next page: the "2"
    sel.extend(1, two.rect[0] + 1, two.rect[1] + 1)
    assert sel.text().startswith(last.text + "\n")
    assert sel.text().endswith("\nPage 2")


# --- printing -----------------------------------------------------------------


def pdf_printer(path: Path) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setOutputFileName(str(path))
    return printer


def test_print_to_pdf(qapp: QApplication, rich_pdf: Path, tmp_path: Path) -> None:
    doc = Document.open(rich_pdf)
    out = tmp_path / "out.pdf"
    seen: list[int] = []
    assert print_document(
        doc, pdf_printer(out), [0, 3], fit=True, progress=lambda n: seen.append(n) is None
    )
    assert seen == [1, 2]
    printed = pymupdf.open(out)
    assert printed.page_count == 2
    (portrait,) = printed[0].get_image_info()
    (landscape,) = printed[1].get_image_info()  # turned to fill the portrait sheet
    for info in (portrait, landscape):
        x0, y0, x1, y1 = info["bbox"]
        assert y1 - y0 > x1 - x0
        assert info["width"] >= 595 * 300 / 72 - 2 or info["height"] >= 595 * 300 / 72 - 2
    doc.close()


def test_print_cancel(qapp: QApplication, text_pdf: Path, tmp_path: Path) -> None:
    doc = Document.open(text_pdf)
    assert not print_document(
        doc, pdf_printer(tmp_path / "x.pdf"), [0, 1, 2], progress=lambda n: n < 2
    )
    doc.close()


def test_page_range_selection(qapp: QApplication) -> None:
    printer = QPrinter()
    assert pages_to_print(printer, 4, current=2) == [0, 1, 2, 3]
    printer.setPrintRange(QPrinter.PrintRange.CurrentPage)
    assert pages_to_print(printer, 4, current=2) == [2]
    printer.setPrintRange(QPrinter.PrintRange.PageRange)
    printer.setFromTo(2, 9)
    assert pages_to_print(printer, 4, current=0) == [1, 2, 3]


def test_actual_size_placement() -> None:
    from PySide6.QtCore import QRectF

    paper = QRectF(0, 0, 2480, 3508)  # A4 at 300 dpi
    target, rotate = placement(595, 842, paper, 300, fit=False)
    assert not rotate
    assert target.width() == pytest.approx(595 / 72 * 300)
    target, rotate = placement(842, 595, paper, 300, fit=True)
    assert rotate
    assert target.width() <= 3508 + 1 and target.height() <= 2480 + 1
