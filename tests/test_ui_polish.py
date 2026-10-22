"""Header buttons and Fill & Sign panel polish."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QPushButton
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.ui import theme
from pdr_sign.ui.fill_sign_panel import TILE, TOOL_BUTTONS
from pdr_sign.ui.main_window import MainWindow
from tests.conftest import trigger_shortcut


def make_window(qtbot: QtBot, qapp: QApplication, tmp_path: Path, scheme: str) -> MainWindow:
    settings = Settings(theme=scheme, signature_dir=str(tmp_path / f"sigs-{scheme}"))
    w = build_window(configure(qapp, settings), settings, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.resize(1180, 800)
    w.show()
    qtbot.waitExposed(w)
    return w


@pytest.fixture(params=["light", "dark"])
def window(
    request: pytest.FixtureRequest, qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> Iterator[MainWindow]:
    w = make_window(qtbot, qapp, tmp_path, request.param)
    yield w
    for tab in list(w.tabs):
        w.close_tab(tab)
    with contextlib.suppress(RuntimeError):
        configure(qapp, Settings(theme="light"))


def centre_pixel(widget: object) -> QColor:
    image = widget.grab().toImage()  # type: ignore[attr-defined]
    return QColor(image.pixel(4, image.height() // 2))


# --- header -------------------------------------------------------------------------


def test_header_left_side_order(window: MainWindow, text_pdf: Path) -> None:
    window.open_paths([str(text_pdf)])
    h = window.header
    layout = h.layout()
    assert layout is not None
    order = [h.open_button, h.sidebar_button, h.print_button, h.fill_button, h.save_button]
    indexes = [layout.indexOf(b) for b in order]
    assert indexes == list(range(indexes[0], indexes[0] + 5))
    assert not h.findChildren(QPushButton)  # the old "Fill & Sign" pill is gone


def test_fill_toggle(window: MainWindow, text_pdf: Path) -> None:
    h = window.header
    button = h.fill_button
    assert button.toolTip() == "Fill & Sign (Ctrl+E)"
    assert button.accessibleName() == "Fill & Sign"
    assert button.isCheckable() and not button.isEnabled()  # no document yet

    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None and button.isEnabled()
    button.click()
    assert window.fill_mode and tab.panel_visible and button.isChecked()
    accent = QColor(window.tokens.accent)
    assert centre_pixel(button).name() == accent.name()  # shows the accent while open
    trigger_shortcut(window, "Ctrl+E")
    assert not window.fill_mode and not button.isChecked()
    button.click()
    tab.panel.done_button.click()
    assert not button.isChecked()


def test_save_button_is_present_but_disabled(window: MainWindow, text_pdf: Path) -> None:
    window.open_paths([str(text_pdf)])
    save = window.header.save_button
    assert save.toolTip() == "Save (Ctrl+S)" and save.accessibleName() == "Save"
    assert save.property("iconName") == "save"
    assert not save.isEnabled()  # wired up in Phase 5


# --- panel ---------------------------------------------------------------------------


def test_check_tool_is_named_check(window: MainWindow, text_pdf: Path) -> None:
    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None
    check = tab.panel._buttons["check"]
    assert check.text() == "Check" and check.accessibleName() == "Check tool"
    assert check.toolTip().startswith("Check")
    assert all("Checkmark" not in (label + hint) for _, label, _, hint in TOOL_BUTTONS)


def test_tool_tiles_are_identical_three_per_row(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    from pdr_sign.ui.theme import PANEL_WIDTH

    window.open_paths([str(text_pdf)])
    window.set_fill_mode(True)
    tab = window.current_tab()
    assert tab is not None
    qtbot.waitUntil(lambda: tab.panel.width() == PANEL_WIDTH, timeout=2000)  # slid in
    buttons = [tab.panel._buttons[t] for t, *_ in TOOL_BUTTONS]
    assert [t for t, *_ in TOOL_BUTTONS] == [
        "text",
        "check",
        "cross",
        "dot",
        "line",
        "date",
        "initials",
        "signature",
        "stamp",
    ]
    assert {b.size().toTuple() for b in buttons} == {TILE.toTuple()}
    rows: dict[int, list[int]] = {}
    for b in buttons:
        rows.setdefault(b.y(), []).append(b.x())
    assert [len(xs) for _, xs in sorted(rows.items())] == [3, 3, 3]
    assert len({tuple(xs[:2]) for xs in rows.values()}) == 1  # columns line up
    assert buttons[2].geometry().right() <= tab.panel.width() - 16  # fits the panel


def test_saved_thumbnails_sit_on_paper_tiles(window: MainWindow, text_pdf: Path) -> None:
    from PySide6.QtGui import QColor as C

    from pdr_sign.ui.signature_dialog import render_typed

    window.signatures.add("signature", render_typed("Ada", "Caveat", C("#000000")), True)
    window.open_paths([str(text_pdf)])
    window.set_fill_mode(True)
    tab = window.current_tab()
    assert tab is not None
    (tile,) = tab.panel.saved["signature"].buttons
    assert tile.objectName() == "SavedSignature"
    # Paper white in both themes, even inside the dark panel.
    assert centre_pixel(tile).name() == QColor(theme.LIGHT.paper).name()


def test_fill_toggle_really_hides_the_panel(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    """Regression: the panel's fixed width pinned its minimum at 280 px, so "hiding"
    (maximum width -> 0) left it on screen while the icon lost its accent."""
    from PySide6.QtCore import Qt

    from pdr_sign.ui.theme import PANEL_WIDTH

    window.open_paths([str(text_pdf)])
    tab = window.current_tab()
    assert tab is not None
    button = window.header.fill_button
    accent = QColor(window.tokens.accent).name()

    def shown() -> bool:
        return tab.panel.isVisible() and tab.panel.width() == PANEL_WIDTH

    def hidden() -> bool:
        return not tab.panel.isVisible() and tab.panel.width() == 0

    def check(open_: bool) -> None:
        qtbot.waitUntil(shown if open_ else hidden, timeout=2000)
        assert button.isChecked() is open_ and window.fill_mode is open_
        assert (centre_pixel(button).name() == accent) is open_

    for expected in (True, False, True, False):  # hide -> show -> hide, by real clicks
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        check(expected)
    trigger_shortcut(window, "Ctrl+E")
    check(True)
    trigger_shortcut(window, "Ctrl+E")
    check(False)
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    check(True)
    qtbot.mouseClick(tab.panel.done_button, Qt.MouseButton.LeftButton)
    check(False)
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)  # and it still opens afterwards
    check(True)
