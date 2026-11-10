"""Item 8: no blue selection highlight outlives its selection (real mouse)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsItem
from pytestqt.qtbot import QtBot

from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.text_item import TextGraphic
from tests import ui_helpers as ui


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    yield from ui.make_window(qtbot, qapp, tmp_path)


def typed_item(qtbot: QtBot, window: MainWindow, path: Path) -> tuple[DocumentTab, TextGraphic]:
    """A text item with "Hello world" typed into it, still being edited."""
    tab = ui.open_tab(window, path)
    window.set_fill_mode(True)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("text")
    ui.click(tab, ui.at(tab, 300, 60))  # empty margin above the page text
    graphic = next(g for g in layer.graphics.values() if isinstance(g, TextGraphic))
    assert graphic.editing
    QTest.keyClicks(graphic.editor.scene().views()[0].viewport(), "")  # focus settles
    graphic.editor.textCursor().insertText("Hello world")
    QApplication.processEvents()
    return tab, graphic


def select_inside(tab: DocumentTab, graphic: TextGraphic) -> None:
    """Drag across the second word inside the editor, with the mouse."""
    r = graphic.content_rect()
    start = tab.view.mapFromScene(graphic.mapToScene(QPointF(r.width() * 0.55, r.height() / 2)))
    end = tab.view.mapFromScene(graphic.mapToScene(QPointF(r.width() - 3, r.height() / 2)))
    ui.drag(tab, start, end)
    assert graphic.editor.textCursor().hasSelection(), "the drag should select text"


def highlighted(graphic: QGraphicsItem) -> bool:
    """Does the scene show solid selection blue where the item is?"""
    scene = graphic.scene()
    assert scene is not None
    rect = graphic.sceneBoundingRect()
    image = QImage(
        int(rect.width() * 4) + 1, int(rect.height() * 4) + 1, QImage.Format.Format_RGB32
    )
    image.fill(QColor("white"))
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, image.width(), image.height()), rect)
    painter.end()
    for y in range(image.height()):
        for x in range(image.width()):
            c = QColor(image.pixel(x, y))
            if c.blue() > 150 and c.red() < 120 and c.green() < 120:  # solid accent blue
                return True
    return False


def assert_clean(graphic: TextGraphic) -> None:
    assert not graphic.editing
    assert not graphic.editor.textCursor().hasSelection()
    # The item may stay selected (dashed accent outline): that's intended, so look
    # without it. What must be gone is the blue block behind the selected words.
    selected = graphic.isSelected()
    graphic.setSelected(False)
    assert not highlighted(graphic.editor)
    graphic.setSelected(selected)


@pytest.mark.parametrize("how", ["click-elsewhere", "escape", "focus-panel"])
def test_in_item_selection_clears_when_editing_ends(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, how: str
) -> None:
    tab, graphic = typed_item(qtbot, window, text_pdf)
    select_inside(tab, graphic)
    assert highlighted(graphic.editor)  # the selection shows while editing
    if how == "click-elsewhere":
        ui.click(tab, ui.at(tab, 450, 790))  # empty page space
    elif how == "escape":
        QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Escape)
        graphic.editor.clearFocus() if graphic.editor.hasFocus() else None
        QApplication.processEvents()
    else:
        tab.panel.setFocus()
        graphic.editor.clearFocus()
        QApplication.processEvents()
    assert_clean(graphic)
    assert tab.view.selection.is_empty  # and no page text got selected either


def test_drag_from_inside_a_text_item_never_selects_page_text(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab, graphic = typed_item(qtbot, window, text_pdf)
    ui.click(tab, ui.at(tab, 450, 790))  # finish editing
    assert not graphic.editing
    # From inside the (not editing) item, across lots of page text below it.
    ui.drag(tab, ui.centre_of(graphic), ui.at(tab, 400, 300))
    assert tab.view.selection.is_empty
    for page in tab.view.page_items:
        assert page.selection_rects == []


def test_page_selection_highlight_goes_with_its_selection(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab = ui.open_tab(window, text_pdf)
    ui.drag(tab, ui.at(tab, 80, 118), ui.at(tab, 400, 160))
    assert not tab.view.selection.is_empty
    assert tab.view.page_items[0].selection_rects
    ui.click(tab, ui.at(tab, 450, 790))  # click elsewhere: selection and highlight go
    assert tab.view.selection.is_empty
    assert tab.view.page_items[0].selection_rects == []
