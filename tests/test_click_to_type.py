"""Item 4: a plain click on empty page space starts typing there. Real mouse."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.text_item import TextGraphic
from tests import ui_helpers as ui


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    yield from ui.make_window(qtbot, qapp, tmp_path)


def boxes(tab: DocumentTab) -> list[TextGraphic]:
    layer = tab.view.fill_layer
    assert layer is not None
    return [g for g in layer.graphics.values() if isinstance(g, TextGraphic) and g.scene()]


def test_click_on_empty_space_opens_panel_and_types_there(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab = ui.open_tab(window, text_pdf)
    assert not window.fill_mode
    ui.click(tab, ui.at(tab, 350, 60))  # right of "Page 1", above the body text
    assert window.fill_mode, "Fill & Sign should open"
    (box,) = boxes(tab)
    assert box.editing and box.pending
    x0, y0, _, _ = box.scene_rect_in_page()
    assert x0 == pytest.approx(350, abs=3) and y0 == pytest.approx(60, abs=12)
    assert tab.view.fill_layer is not None and tab.view.fill_layer.tool == ""  # one-shot
    if window.isActiveWindow():  # keyboard focus needs an active window
        QTest.keyClicks(tab.view.viewport(), "Paid in full")
        ui.click(tab, ui.at(tab, 500, 810))  # click away: committed as one item
        assert [i.text for i in tab.model.items.values()] == ["Paid in full"]


def test_empty_box_vanishes_without_an_undo_step(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab = ui.open_tab(window, text_pdf)
    ui.click(tab, ui.at(tab, 350, 60))
    (box,) = boxes(tab)
    box.end_editing()  # focus leaves an empty box
    QApplication.processEvents()
    assert boxes(tab) == [] and tab.model.items == {}
    assert tab.model.undo_stack.count() == 0


def test_drag_selects_text_and_opens_nothing(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab = ui.open_tab(window, text_pdf)
    ui.drag(tab, ui.at(tab, 80, 118), ui.at(tab, 400, 160))
    assert not tab.view.selection.is_empty
    assert not window.fill_mode and boxes(tab) == []


def test_click_on_page_text_makes_no_box(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    tab = ui.open_tab(window, text_pdf)
    ui.click(tab, ui.at(tab, 100, 118))  # on a word: double-click word selection stays
    assert not window.fill_mode and boxes(tab) == []


def test_click_on_link_follows_it_and_makes_no_box(
    qtbot: QtBot, window: MainWindow, rich_pdf: Path
) -> None:
    tab = ui.open_tab(window, rich_pdf)
    ui.click(tab, ui.at(tab, 160, 110))  # the internal link (right of its text)
    assert tab.view.current_page == 2
    assert not window.fill_mode and boxes(tab) == []


def test_click_on_field_keeps_field_behaviour(
    qtbot: QtBot, window: MainWindow, form_pdf: Path
) -> None:
    tab = ui.open_tab(window, form_pdf)
    ui.click(tab, ui.at(tab, 186, 82))  # the "name" text field
    assert window.fill_mode  # (fields open the panel, as before)
    assert boxes(tab) == []


def test_click_on_placed_item_selects_it(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    tab = ui.open_tab(window, text_pdf)
    tab.model.add_item(OverlayItem("check", 0, (350, 40, 364, 54), font_size=14))
    layer = tab.view.fill_layer
    assert layer is not None
    (mark,) = layer.graphics.values()
    tab.view.scene().clearSelection()
    ui.click(tab, ui.centre_of(mark))
    assert mark.isSelected() and boxes(tab) == []


def test_click_with_something_selected_only_clears_it(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab = ui.open_tab(window, text_pdf)
    tab.model.add_item(OverlayItem("check", 0, (300, 40, 314, 54), font_size=14))
    layer = tab.view.fill_layer
    assert layer is not None
    (mark,) = layer.graphics.values()
    mark.setSelected(True)
    ui.click(tab, ui.at(tab, 450, 60))
    assert not mark.isSelected() and boxes(tab) == []
    ui.drag(tab, ui.at(tab, 80, 118), ui.at(tab, 400, 160))  # page text selected
    ui.click(tab, ui.at(tab, 450, 60))
    assert tab.view.selection.is_empty and boxes(tab) == []
    ui.click(tab, ui.at(tab, 450, 60))  # now nothing is selected: this one types
    assert len(boxes(tab)) == 1
