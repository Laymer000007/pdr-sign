"""Item 1: several windows in one process. Real mouse/keyboard where it's an interaction."""

from __future__ import annotations

import configparser
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign import APP_ID
from pdr_sign.app import build_window, configure
from pdr_sign.services.instance import send_to_running
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui import dialogs
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.single_instance import InstanceServer
from pdr_sign.ui.windows import WindowManager
from tests import ui_helpers as ui
from tests.conftest import make_text_pdf, trigger_shortcut

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_slide(monkeypatch: pytest.MonkeyPatch) -> None:
    ui.no_slide_animation(monkeypatch)


@pytest.fixture
def first(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    settings = Settings(theme="light", signature_dir=str(tmp_path / "sigs"))
    w = build_window(configure(qapp, settings), settings, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.resize(1000, 760)
    w.show()
    qtbot.waitExposed(w)
    yield w
    for window in list(w.manager.windows):
        for tab in list(window.tabs):
            window.close_tab(tab, ask=False)
        window.close()


def pdfs(tmp_path: Path, n: int) -> list[Path]:
    return [make_text_pdf(tmp_path / f"doc{i}.pdf", 2) for i in range(n)]


def activate(qtbot: QtBot, window: MainWindow) -> None:
    """Focus ``window`` for real and wait for the window system to confirm it. (On a
    desktop session the window manager may refuse to focus a test window: skip then,
    as the focus tests elsewhere do.)"""
    window.raise_()
    window.activateWindow()
    try:
        qtbot.waitUntil(window.isActiveWindow, timeout=2000)
    except qtbot.TimeoutError:
        pytest.skip("the window manager wouldn't focus the test window")
    QApplication.processEvents()


def test_ctrl_n_opens_a_new_empty_window(qtbot: QtBot, first: MainWindow) -> None:
    trigger_shortcut(first, "Ctrl+N")
    manager: WindowManager = first.manager
    assert len(manager.windows) == 2
    second = manager.windows[1]
    qtbot.waitExposed(second)
    assert second.isVisible() and second.tabs == [] and second.windowTitle() == "PDR Sign"
    assert second is not first


def test_header_menu_has_new_window(first: MainWindow) -> None:
    menu = first.header.menu_button.menu()
    action = next(a for a in menu.actions() if a.text().replace("&", "") == "New Window")
    action.trigger()
    assert len(first.manager.windows) == 2


def test_move_tab_to_new_window_keeps_its_state(
    qtbot: QtBot, first: MainWindow, tmp_path: Path
) -> None:
    a, b = pdfs(tmp_path, 2)
    first.open_paths([str(a), str(b)])
    tab_b = first.current_tab()
    assert tab_b is not None and tab_b.doc.path == b.resolve()
    tab_b.model.add_item(OverlayItem("check", 0, (100, 40, 114, 54), font_size=14))
    first.set_fill_mode(True)
    menu = first.tab_bar.menu_for(first.tabs.index(tab_b))
    move = next(x for x in menu.actions() if x.text().replace("&", "") == "Move to New Window")
    move.trigger()
    QApplication.processEvents()
    second = first.manager.windows[1]
    assert [t.doc.path for t in first.tabs] == [a.resolve()]
    assert second.tabs == [tab_b] and second.current_tab() is tab_b
    assert second.windowTitle() == f"• {tab_b.doc.display_name} – PDR Sign"
    assert first.windowTitle() == f"{first.tabs[0].doc.display_name} – PDR Sign"
    # its own undo history came along; Fill & Sign is per window
    tab_b.model.undo_stack.undo()
    assert tab_b.model.items == {}
    assert not second.fill_mode and first.fill_mode
    tab_b.fill_done.emit()  # "Done" in the moved tab's panel affects only its window
    assert first.fill_mode
    # and nothing still talks to the old window
    tab_b.model.add_item(OverlayItem("dot", 0, (100, 80, 114, 94), font_size=14))
    assert first.tab_bar.tabText(0) == first.tabs[0].doc.path.name


def test_dragging_a_tab_out_opens_it_in_a_new_window(
    qtbot: QtBot, first: MainWindow, tmp_path: Path
) -> None:
    a, b = pdfs(tmp_path, 2)
    first.open_paths([str(a), str(b)])
    bar = first.tab_bar
    start = bar.tabRect(1).center()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 13):  # down and out of the tab bar, into the page
        QTest.mouseMove(bar, start + QPoint(step * 4, step * 12))
    QTest.mouseRelease(
        bar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(48, 144)
    )
    QApplication.processEvents()
    assert len(first.manager.windows) == 2
    second = first.manager.windows[1]
    assert [t.doc.path for t in second.tabs] == [b.resolve()]
    assert [t.doc.path for t in first.tabs] == [a.resolve()]


def test_dragging_within_the_bar_only_reorders(
    qtbot: QtBot, first: MainWindow, tmp_path: Path
) -> None:
    a, b = pdfs(tmp_path, 2)
    first.open_paths([str(a), str(b)])
    bar = first.tab_bar
    start, end = bar.tabRect(1).center(), bar.tabRect(0).center()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 11):
        QTest.mouseMove(bar, start + (end - start) * step / 10)
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    QApplication.processEvents()
    assert len(first.manager.windows) == 1


def test_open_with_goes_to_the_most_recently_focused_window(
    qtbot: QtBot, first: MainWindow, tmp_path: Path
) -> None:
    a, b, c = pdfs(tmp_path, 3)
    manager = first.manager
    second = manager.new_window()
    qtbot.waitExposed(second)
    activate(qtbot, second)
    manager.open_paths([str(a)])
    assert [t.doc.path for t in second.tabs] == [a.resolve()] and first.tabs == []
    activate(qtbot, first)
    manager.open_paths([str(b)])
    assert [t.doc.path for t in first.tabs] == [b.resolve()]
    # a file already open elsewhere is shown there, not opened twice
    manager.open_paths([str(a)])
    assert len(first.tabs) == 1 and len(second.tabs) == 1
    assert manager.last_active is second
    manager.open_paths([str(c)], new_window=True)
    assert len(manager.windows) == 3 and manager.windows[2].tabs[0].doc.path == c.resolve()


def test_second_launch_with_new_window_flag(
    qtbot: QtBot, first: MainWindow, tmp_path: Path
) -> None:
    sock = tmp_path / "pdr.sock"
    server = InstanceServer(sock)
    assert server.start()
    server.files_received.connect(first.manager.open_paths)
    server.new_window_requested.connect(lambda p: first.manager.open_paths(p, new_window=True))
    (a,) = pdfs(tmp_path, 1)
    result: list[bool] = []
    thread = threading.Thread(
        target=lambda: result.append(send_to_running([str(a)], sock, new_window=True))
    )
    thread.start()
    qtbot.waitUntil(lambda: len(first.manager.windows) == 2, timeout=3000)
    thread.join(3)
    server.stop()
    assert result == [True]
    assert [t.doc.path for t in first.manager.windows[1].tabs] == [a.resolve()]


def test_unsaved_prompts_are_per_window_and_last_window_quits(
    qtbot: QtBot, first: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = pdfs(tmp_path, 2)
    first.open_paths([str(a)])
    second = first.manager.open_paths([str(b)], new_window=True)
    assert second is not None
    second.current_tab().model.add_item(  # type: ignore[union-attr]
        OverlayItem("dot", 0, (100, 80, 114, 94), font_size=14)
    )
    asked: list[str] = []
    monkeypatch.setattr(dialogs, "ask_unsaved", lambda _w, name: asked.append(name) or "discard")
    first.close()  # nothing unsaved here: no question
    assert asked == []
    assert first.manager.windows == [second]
    assert QApplication.quitOnLastWindowClosed()
    second.close()
    assert asked == [b.name]
    assert first.manager.windows == []


def test_desktop_file_has_a_new_window_action() -> None:
    entry = configparser.ConfigParser(interpolation=None)
    entry.optionxform = str  # type: ignore[assignment,method-assign]
    entry.read(ROOT / "packaging" / "linux" / f"{APP_ID}.desktop", encoding="utf-8")
    assert "new-window" in entry["Desktop Entry"]["Actions"].split(";")
    action = entry["Desktop Action new-window"]
    assert action["Name"] == "New Window"
    assert action["Exec"] == "pdr-sign --new-window"
