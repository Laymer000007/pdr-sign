"""Item 6: with a placing tool active, a click ON a placed item selects it; a click on
empty page space places a new one. Real mouse and keyboard."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.base import OverlayGraphic
from tests import ui_helpers as ui


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    yield from ui.make_window(qtbot, qapp, tmp_path)


def with_items(window: MainWindow, path: Path) -> tuple[DocumentTab, dict[str, OverlayGraphic]]:
    tab = ui.open_tab(window, path)
    window.set_fill_mode(True)
    for item in (
        OverlayItem("check", 0, (100, 40, 114, 54), font_size=14),
        OverlayItem("text", 0, (200, 40, 280, 57), text="Placed text"),
        OverlayItem("line", 0, (330, 48, 430, 48)),
    ):
        tab.model.add_item(item)
    layer = tab.view.fill_layer
    assert layer is not None
    graphics = {g.item.kind: g for g in layer.graphics.values()}
    tab.view.scene().clearSelection()
    QApplication.processEvents()
    return tab, graphics


@pytest.mark.parametrize("tool", ["dot", "check", "cross", "date"])
def test_click_on_placed_item_selects_it_instead_of_placing(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, tool: str
) -> None:
    tab, graphics = with_items(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool(tool)
    count = len(tab.model.items)
    target = graphics["check"]
    ui.click(tab, ui.centre_of(target))
    assert len(tab.model.items) == count, "a new item was placed on top"
    assert target.isSelected()
    assert layer.tool == tool  # the tool stays on for the next empty-space click
    pos = ui.centre_of(target)  # move it, with the tool still active
    ui.drag(tab, pos, pos + QPoint(30, 20))
    assert len(tab.model.items) == count
    assert tab.model.items[target.item.id].rect[0] == pytest.approx(100 + 30, abs=1.5)
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Delete)  # and delete it
    assert target.item.id not in tab.model.items


def test_line_tool_press_on_item_selects_not_draws(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab, graphics = with_items(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("line")
    count = len(tab.model.items)
    ui.click(tab, ui.centre_of(graphics["text"]))
    assert len(tab.model.items) == count and layer.draft is None
    assert graphics["text"].isSelected()


def test_click_on_empty_space_still_places(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab, _ = with_items(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("dot")
    count = len(tab.model.items)
    ui.click(tab, ui.at(tab, 500, 45))
    assert len(tab.model.items) == count + 1


def test_form_fields_still_lose_to_the_tool(
    qtbot: QtBot, window: MainWindow, form_pdf: Path
) -> None:
    tab = ui.open_tab(window, form_pdf)
    window.set_fill_mode(True)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("check")
    ui.click(tab, ui.at(tab, 186, 82))  # inside the "name" text field
    assert [i.kind for i in tab.model.items.values()] == ["check"]


def test_escape_and_tile_click_turn_the_tool_off(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab, _ = with_items(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("dot")
    assert tab.panel._buttons["dot"].isChecked()  # the active tool shows in the panel
    assert tab.panel.tool_hint.isVisible()
    assert "Esc stops" in tab.panel.tool_hint.text()
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Escape)
    assert layer.tool == "" and not tab.panel._buttons["dot"].isChecked()
    assert not tab.panel.tool_hint.isVisible()
    qtbot.mouseClick(tab.panel._buttons["dot"], Qt.MouseButton.LeftButton)
    assert layer.tool == "dot"
    qtbot.mouseClick(tab.panel._buttons["dot"], Qt.MouseButton.LeftButton)  # again: off
    assert layer.tool == ""
