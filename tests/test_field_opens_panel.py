"""Clicking a form field opens Fill & Sign; clicking page text doesn't (real mouse)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QListWidget, QPlainTextEdit
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services.forms import FieldInfo
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.field_widgets import FieldProxy, ToggleField

LEFT = Qt.MouseButton.LeftButton


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    settings = Settings(theme="light")
    w = build_window(configure(qapp, settings), settings, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.resize(1100, 760)
    w.show()
    qtbot.waitExposed(w)
    w.activateWindow()
    with contextlib.suppress(qtbot.TimeoutError):
        qtbot.waitUntil(w.isActiveWindow, timeout=1000)
    yield w
    for tab in list(w.tabs):
        w.close_tab(tab, ask=False)


def open_tab(window: MainWindow, path: Path) -> DocumentTab:
    window.open_paths([str(path)])
    tab = window.current_tab()
    assert tab is not None
    tab.view.set_zoom(1.0)
    tab.view.go_to_page(0)
    QApplication.processEvents()
    assert not window.fill_mode
    return tab


def graphic(tab: DocumentTab, name: str, index: int = 0) -> FieldProxy | ToggleField:
    layer = tab.view.field_layer
    assert layer is not None
    return layer.by_name[name][index]


def centre_of(tab: DocumentTab, page: int, rect: tuple[float, float, float, float]) -> QPoint:
    x0, y0, x1, y1 = rect
    view = tab.view
    tab.view.reveal(page, rect)
    QApplication.processEvents()
    point = QPointF((x0 + x1) / 2, (y0 + y1) / 2)
    return view.mapFromScene(view.page_items[page].mapToScene(point))


def click(tab: DocumentTab, pos: QPoint) -> None:
    QTest.mouseClick(tab.view.viewport(), LEFT, pos=pos)
    QApplication.processEvents()


def test_text_field_click_opens_panel_and_edits_field(
    window: MainWindow, form_pdf: Path, qtbot: QtBot
) -> None:
    tab = open_tab(window, form_pdf)
    field = graphic(tab, "name")
    click(tab, centre_of(tab, 0, field.field.rect))
    assert window.fill_mode and window.header.fill_button.isChecked()
    qtbot.waitUntil(lambda: tab.panel.isVisible(), timeout=2000)
    assert isinstance(field, FieldProxy)
    assert tab.view.scene().focusItem() is field  # the click still went to the field
    if window.isActiveWindow():  # typing needs an active window (see test_ui_fill)
        QTest.keyClicks(field.widget(), "Ada")
        field.clearFocus()
        assert tab.model.values["name"] == "Ada"


def test_checkbox_click_opens_panel_and_ticks(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    box = graphic(tab, "agree")
    click(tab, centre_of(tab, 0, box.field.rect))
    assert window.fill_mode
    assert tab.model.values["agree"] not in (False, "Off", "", None)


def test_radio_click_opens_panel_and_selects(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    radio = graphic(tab, "colour", 1)
    click(tab, centre_of(tab, 0, radio.field.rect))
    assert window.fill_mode
    assert tab.model.values["colour"] == radio.field.on_state


def test_dropdown_click_opens_panel(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    combo = graphic(tab, "country")
    assert isinstance(combo, FieldProxy) and isinstance(combo.widget(), QComboBox)
    click(tab, centre_of(tab, 0, combo.field.rect))
    assert window.fill_mode
    combo.widget().hidePopup()  # type: ignore[attr-defined]


def test_list_click_opens_panel_and_selects(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    lst = graphic(tab, "fruit")
    widget = lst.widget()  # type: ignore[union-attr]
    assert isinstance(widget, QListWidget)
    x0, y0, x1, _ = lst.field.rect
    row_h = widget.sizeHintForRow(0) / max(1e-6, tab.view.zoom)
    click(tab, centre_of(tab, 0, (x0, y0, x1, y0 + row_h)))  # first row: "apple"
    assert window.fill_mode
    assert tab.model.values["fruit"] == ("apple",)


def test_signature_field_click_opens_panel(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    signed: list[FieldInfo] = []
    layer = tab.view.field_layer
    assert layer is not None
    layer.on_sign_field = signed.append  # no real signature dialog in tests
    sign_rect = next(f for f in layer.model.fields if f.kind == "signature").rect
    click(tab, centre_of(tab, 1, sign_rect))
    assert window.fill_mode
    assert [f.name for f in signed] == ["signature"]


def test_page_text_click_keeps_panel_closed_and_selects(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    view = tab.view
    start = view.mapFromScene(view.page_items[0].mapToScene(QPointF(80, 118)))
    end = view.mapFromScene(view.page_items[0].mapToScene(QPointF(300, 118)))
    click(tab, start)  # a plain click on text
    assert not window.fill_mode
    QTest.mousePress(view.viewport(), LEFT, pos=start)
    for step in range(1, 11):
        QTest.mouseMove(view.viewport(), start + (end - start) * step / 10)
    QTest.mouseRelease(view.viewport(), LEFT, pos=end)
    QApplication.processEvents()
    assert not window.fill_mode
    assert tab.view.selection.text().strip()  # text selection still works


def test_multiline_editor_is_the_text_widget(window: MainWindow, form_pdf: Path) -> None:
    # Guard for the helper: "notes" is a QPlainTextEdit field, also a FieldProxy.
    tab = open_tab(window, form_pdf)
    notes = graphic(tab, "notes")
    assert isinstance(notes, FieldProxy) and isinstance(notes.widget(), QPlainTextEdit)
    click(tab, centre_of(tab, 0, notes.field.rect))
    assert window.fill_mode
