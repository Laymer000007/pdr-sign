"""Item 5: a text item must never get stuck (selected/editing, unmovable, undeletable)
when tabs switch while it's being edited or dragged. Real mouse and keyboard events,
random interleavings with fixed seeds."""

from __future__ import annotations

import random
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.base import OverlayGraphic
from pdr_sign.ui.overlay.text_item import TextGraphic
from tests import ui_helpers as ui
from tests.conftest import make_text_pdf

LEFT = Qt.MouseButton.LeftButton
# Where new text boxes go: apart from each other and the two starting items, so the
# final click on each box can only hit that box.
SLOTS = [(x, y) for y in (120.0, 170.0, 220.0) for x in (400.0, 500.0)]


@pytest.fixture(autouse=True)
def no_slide_animation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The panel slides in over 150 ms; positions measured mid-slide would miss. (The
    desktop's reduced-motion setting does the same.)"""
    from pdr_sign.ui import document_tab

    monkeypatch.setattr(document_tab, "animations_enabled", lambda: False)


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    yield from ui.make_window(qtbot, qapp, tmp_path)


def two_tabs(window: MainWindow, tmp_path: Path) -> list[DocumentTab]:
    tabs = []
    for name in ("a.pdf", "b.pdf"):
        tab = ui.open_tab(window, make_text_pdf(tmp_path / name, 1))
        for i, y in enumerate((40.0, 790.0)):
            item = OverlayItem("text", 0, (300, y, 380, y + 17), text=f"{name[0]} item {i}")
            tab.model.add_item(item)
        tabs.append(tab)
    window.set_fill_mode(True)
    QApplication.processEvents()
    return tabs


def texts(tab: DocumentTab) -> list[TextGraphic]:
    layer = tab.view.fill_layer
    assert layer is not None
    return [g for g in layer.graphics.values() if isinstance(g, TextGraphic) and g.scene()]


def show(window: MainWindow, tab: DocumentTab) -> None:
    window.tab_bar.setCurrentIndex(window.tabs.index(tab))
    QApplication.processEvents()


def visible_pos(tab: DocumentTab, graphic: OverlayGraphic) -> QPoint:
    tab.view.reveal(graphic.item.page, graphic.scene_rect_in_page())
    QApplication.processEvents()
    return ui.centre_of(graphic)


def assert_released(tab: DocumentTab) -> None:
    """Nothing in a tab you've left is still being edited, grabbed or half-pressed."""
    view = tab.view
    assert view.scene().mouseGrabberItem() is None, "a mouse grab outlived the tab switch"
    assert not view._press_to_items, "the canvas still thinks a press is going on"
    assert view.fill_layer is not None and view.fill_layer.draft is None
    for graphic in texts(tab):
        assert not graphic.editing, f"{graphic.item.text!r} is still in edit mode"
        assert graphic.flags() & graphic.GraphicsItemFlag.ItemIsMovable


def assert_usable(window: MainWindow, tab: DocumentTab) -> None:
    """Every item can be selected, moved and deleted with the real mouse/keyboard."""
    show(window, tab)
    ui.click(tab, ui.at(tab, 560, 30))  # like a user: click empty page to finish typing
    # Topmost first (items may legitimately overlap after the random drags); each is
    # deleted after its check, so the next one is always the top one at its centre.
    stacked = [i for i in tab.view.scene().items() if isinstance(i, TextGraphic)]
    assert set(stacked) == set(texts(tab))
    for graphic in stacked:
        pos = visible_pos(tab, graphic)
        ui.click(tab, pos)
        assert graphic.isSelected(), f"{graphic.item.text!r} can't be selected"
        before = graphic.pos()
        ui.drag(tab, pos, pos + QPoint(12, 0))
        assert graphic.pos() != before, f"{graphic.item.text!r} can't be moved"
        ui.click(tab, ui.centre_of(graphic))
        QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Delete)
        QApplication.processEvents()
        assert graphic.scene() is None, f"{graphic.item.text!r} can't be deleted"


def step(rng: random.Random, window: MainWindow, tabs: list[DocumentTab]) -> str:
    tab = window.current_tab()
    assert tab is not None
    action = rng.choice(
        ["edit", "type", "drag-start", "place", "switch", "switch", "panel", "deactivate"]
    )
    items = texts(tab)
    vp = tab.view.viewport()
    if action == "edit" and items:
        ui.double_click(tab, visible_pos(tab, rng.choice(items)))
    elif action == "type":
        QTest.keyClicks(vp, "xy")
    elif action == "drag-start" and items:
        pos = visible_pos(tab, rng.choice(items))
        QTest.mousePress(vp, LEFT, Qt.KeyboardModifier.NoModifier, pos)
        QTest.mouseMove(vp, pos + QPoint(6, 4))
        QTest.mouseMove(vp, pos + QPoint(14, 9))  # still held: the switch comes mid-drag
    elif action == "place":
        layer = tab.view.fill_layer
        assert layer is not None
        taken = {(round(g.pos().x()), round(g.pos().y())) for g in items}
        free = [
            s for s in SLOTS if not any(abs(s[0] - x) < 90 and abs(s[1] - y) < 40 for x, y in taken)
        ]
        if free:
            layer.set_tool("text")
            ui.click(tab, ui.at(tab, *free[0]))
            QTest.keyClicks(vp, "new")
    elif action == "switch":
        window._cycle_tab(1)  # what Ctrl+Tab does, whatever the mouse is doing
    elif action == "panel":
        window.set_fill_mode(not window.fill_mode)
    elif action == "deactivate":
        QApplication.sendEvent(window, QEvent(QEvent.Type.WindowDeactivate))
        QApplication.sendEvent(window, QEvent(QEvent.Type.WindowActivate))
    QApplication.processEvents()
    for other in tabs:
        if other is not window.current_tab():
            assert_released(other)
    return action


@pytest.mark.parametrize("seed", range(30))
def test_switching_tabs_mid_edit_or_drag_never_sticks(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, seed: int
) -> None:
    tabs = two_tabs(window, tmp_path)
    rng = random.Random(seed)
    for _ in range(40):
        step(rng, window, tabs)
    window.set_fill_mode(True)
    for tab in tabs:  # finally: end any held press, then every item must still work
        QTest.mouseRelease(tab.view.viewport(), LEFT)
        assert_usable(window, tab)


def test_switch_while_dragging_releases_the_grab(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    a, _b = two_tabs(window, tmp_path)
    show(window, a)
    graphic = texts(a)[0]
    pos = visible_pos(a, graphic)
    vp = a.view.viewport()
    QTest.mousePress(vp, LEFT, Qt.KeyboardModifier.NoModifier, pos)
    QTest.mouseMove(vp, pos + QPoint(10, 10))
    window._cycle_tab(1)
    QApplication.processEvents()
    assert_released(a)
    assert_usable(window, a)


def test_switch_while_editing_finishes_the_edit(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    a, _b = two_tabs(window, tmp_path)
    show(window, a)
    graphic = texts(a)[0]
    ui.double_click(a, visible_pos(a, graphic))
    assert graphic.editing
    QTest.keyClicks(a.view.viewport(), " more")
    window._cycle_tab(1)
    QApplication.processEvents()
    assert_released(a)
    assert a.model.items[graphic.item.id].text.endswith(" more")
    assert_usable(window, a)
