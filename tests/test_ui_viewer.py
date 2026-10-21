"""pytest-qt smoke tests for the Phase 1 viewer."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.page_item import tile_key


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Modal dialogs would block the test run; record them instead."""
    from pdr_sign.ui import dialogs

    shown: list[str] = []
    monkeypatch.setattr(dialogs, "confirm_external_link", lambda _p, uri: shown.append(uri))
    monkeypatch.setattr(dialogs, "show_error", lambda _p, _t, msg: shown.append(msg))
    monkeypatch.setattr(dialogs, "ask_password", lambda *_: None)
    return shown


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    settings = Settings(theme="light")
    w = build_window(configure(qapp, settings), settings, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w.show()
    qtbot.waitExposed(w)
    yield w
    for tab in list(w.tabs):
        w.close_tab(tab)


def first_tile_ready(w: MainWindow) -> bool:
    tab = w.current_tab()
    assert tab is not None
    v = tab.view
    key = tile_key(tab.doc, 0, v.render_zoom, v.devicePixelRatioF(), 0, 0)
    return w.scheduler.pixmap(key) is not None


def test_open_renders_and_updates_header(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None and tab.doc.page_count == 3
    assert window.header.page_count.text() == "/ 3"
    assert window.header.zoom_button.text() == "Fit width"
    assert not window.tab_bar.isVisible()
    qtbot.waitUntil(lambda: first_tile_ready(window), timeout=3000)


def test_zoom_controls(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None
    tab.view.set_zoom(1.0)
    window.header.zoom_in_button.click()
    assert tab.view.zoom == pytest.approx(1.1)
    assert window.header.zoom_button.text() == "110 %"
    window.header.zoom_out_button.click()
    window.header.zoom_out_button.click()
    assert tab.view.zoom == pytest.approx(0.9)
    window.header.zoom_preset_requested.emit(2.0)
    assert tab.view.zoom == pytest.approx(2.0)
    qtbot.waitUntil(lambda: tab.view.render_zoom == pytest.approx(2.0), timeout=2000)


def test_zoom_keeps_anchor_point(window: MainWindow, text_pdf: Path) -> None:
    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None
    view = tab.view
    view.set_zoom(1.0)
    view.go_to_page(1)
    anchor = QPointF(view.viewport().width() / 2, 200)

    def page_point() -> tuple[int, float, float]:
        assert view.page_layout is not None
        scene = view.mapToScene(anchor.toPoint())
        return view.page_layout.anchor(scene.x(), scene.y())

    page, _, y_before = page_point()
    view.set_zoom(2.0, anchor=anchor)
    page_after, _, y_after = page_point()
    # The same spot on the same page stays under the cursor (within a pixel).
    assert page_after == page
    assert y_after == pytest.approx(y_before, abs=1)


def test_page_navigation(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None
    tab.view.set_zoom(0.5)
    window.header.page_field.setText("3")
    window.header.page_requested.emit(2)
    assert tab.view.current_page == 2
    qtbot.keyClick(tab.view, Qt.Key.Key_Home)
    assert tab.view.current_page == 0
    qtbot.keyClick(tab.view, Qt.Key.Key_End)
    assert tab.view.current_page == 2
    assert window.header.page_field.text() == "3"


def test_sidebar_thumbnails_and_outline(qtbot: QtBot, window: MainWindow, rich_pdf: Path) -> None:
    window.open_paths([str(rich_pdf)])
    tab = window.current_tab()
    assert tab is not None
    window.set_sidebar_visible(True)
    qtbot.waitUntil(lambda: tab.sidebar.width() > 100, timeout=2000)
    assert tab.sidebar.thumbnails.count() == 6
    tab.view.set_zoom(0.5)
    tab.sidebar.thumbnails.page_activated.emit(3)
    assert tab.view.current_page == 3
    tree = tab.sidebar.outline.tree
    assert tree.topLevelItemCount() == 2
    part_two = tree.topLevelItem(1)
    assert part_two is not None and part_two.childCount() == 1
    tab.sidebar.outline.destination_activated.emit(4, None)
    assert tab.view.current_page == 4


def test_internal_link_click(qtbot: QtBot, window: MainWindow, rich_pdf: Path) -> None:
    window.open_paths([str(rich_pdf)])
    tab = window.current_tab()
    assert tab is not None
    view = tab.view
    view.set_zoom(1.0)
    view.go_to_page(0)
    item = view.page_items[0]
    target = view.mapFromScene(item.mapToScene(QPointF(100, 110)))
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    assert view.current_page == 2


def test_external_link_emits_uri(
    qtbot: QtBot, window: MainWindow, rich_pdf: Path, no_modal_dialogs: list[str]
) -> None:
    window.open_paths([str(rich_pdf)])
    tab = window.current_tab()
    assert tab is not None
    view = tab.view
    view.set_zoom(1.0)
    view.go_to_page(0)
    target = view.mapFromScene(view.page_items[0].mapToScene(QPointF(100, 140)))
    with qtbot.waitSignal(view.external_link) as blocker:
        qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    assert blocker.args == ["https://example.org"]
    assert no_modal_dialogs == ["https://example.org"]  # asked before opening


def test_tabs_appear_with_second_document(
    window: MainWindow, text_pdf: Path, rich_pdf: Path
) -> None:
    window.open_paths([str(text_pdf), str(rich_pdf)])
    assert len(window.tabs) == 2 and window.tab_bar.isVisible()
    assert window.tab_bar.tabText(1) == "rich.pdf"
    window.open_paths([str(text_pdf)])  # already open: just switch
    assert len(window.tabs) == 2 and window.tab_bar.currentIndex() == 0
    window._cycle_tab(1)
    assert window.current_tab() is window.tabs[1]
    window.close_tab(window.tabs[1])
    assert len(window.tabs) == 1 and not window.tab_bar.isVisible()
    window.close_tab(window.tabs[0])
    assert window.stack.currentWidget() is window.empty_state


def test_recent_restores_page_and_zoom(window: MainWindow, text_pdf: Path) -> None:
    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None
    tab.view.set_zoom(0.75)
    tab.view.go_to_page(2)
    window.close_tab(tab)
    assert window.recent.entries[0].page == 2
    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None
    assert tab.view.zoom == pytest.approx(0.75)
    assert tab.view.current_page == 2


def test_password_prompt(
    monkeypatch: pytest.MonkeyPatch, window: MainWindow, encrypted_pdf: Path
) -> None:
    from pdr_sign.ui import dialogs
    from tests.conftest import ENCRYPTED_PASSWORD

    answers = iter(["wrong", ENCRYPTED_PASSWORD])
    calls: list[bool] = []

    def fake_ask(_parent: object, _name: str, retry: bool) -> str:
        calls.append(retry)
        return next(answers)

    monkeypatch.setattr(dialogs, "ask_password", fake_ask)
    window.open_paths([str(encrypted_pdf)])
    assert calls == [False, True]
    assert len(window.tabs) == 1


def test_unsafe_link_scheme_is_refused(monkeypatch: pytest.MonkeyPatch, window: MainWindow) -> None:
    from pdr_sign.ui import dialogs

    errors: list[str] = []
    monkeypatch.setattr(dialogs, "show_error", lambda _p, _t, msg: errors.append(msg))
    monkeypatch.setattr(dialogs, "confirm_external_link", lambda *_: pytest.fail("asked"))
    window.open_external_link("file:///etc/passwd")
    assert errors


@pytest.mark.slow
def test_500_pages_first_page_under_a_second(
    qtbot: QtBot, window: MainWindow, long_pdf: Path
) -> None:
    start = time.perf_counter()
    window.open_paths([str(long_pdf)])
    qtbot.waitUntil(lambda: first_tile_ready(window), timeout=3000)
    assert time.perf_counter() - start < 1.0


def test_drop_opens_pdfs_only(window: MainWindow, text_pdf: Path, tmp_path: Path) -> None:
    from PySide6.QtCore import QMimeData, QPoint, QUrl
    from PySide6.QtGui import QDropEvent

    other = tmp_path / "notes.txt"
    other.write_text("x")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(text_pdf)), QUrl.fromLocalFile(str(other))])
    event = QDropEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    assert [t.doc.path.name for t in window.tabs] == ["three-pages.pdf"]
