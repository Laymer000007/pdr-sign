"""Item 2: copy, cut, paste, duplicate and multi-select placed items. Real mouse and
keyboard where it's an interaction; the clipboard is the test double."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.services import sigimage
from pdr_sign.services.sigimage import PhotoOptions
from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.base import OverlayGraphic
from pdr_sign.ui.overlay.text_item import TextGraphic
from tests import ui_helpers as ui
from tests.conftest import FakeClipboard, make_text_pdf, trigger_shortcut
from tests.sigphoto import phone_photo

CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


@pytest.fixture(autouse=True)
def no_slide(monkeypatch: pytest.MonkeyPatch) -> None:
    ui.no_slide_animation(monkeypatch)


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    yield from ui.make_window(qtbot, qapp, tmp_path)


@pytest.fixture(scope="module")
def png() -> bytes:
    return sigimage.clean_photo(phone_photo(3), PhotoOptions(ink="blue")).png


def sample(kind: str, png: bytes) -> OverlayItem:
    if kind in ("signature", "initials"):
        return OverlayItem(kind, 0, (100, 300, 220, 336), image=png)  # type: ignore[arg-type]
    if kind == "stamp":
        return OverlayItem("stamp", 0, (100, 300, 200, 360), image=png, rotation=-12, opacity=0.7)
    if kind == "line":
        return OverlayItem("line", 0, (100, 320, 220, 330), font_size=16, color="#1D4ED8")
    if kind in ("check", "cross", "dot"):
        return OverlayItem(kind, 0, (100, 300, 118, 318), font_size=18, color="#1D4ED8")  # type: ignore[arg-type]
    return OverlayItem(
        kind,
        0,
        (100, 300, 200, 318),
        text="Copied text",
        font_size=14,  # type: ignore[arg-type]
        color="#1D4ED8",
    )


def setup(window: MainWindow, path: Path, items: list[OverlayItem]) -> DocumentTab:
    tab = ui.open_tab(window, path)
    window.set_fill_mode(True)
    for item in items:
        tab.model.add_item(item)
    tab.model.undo_stack.clear()
    tab.view.scene().clearSelection()
    QApplication.processEvents()
    return tab


def graphics(tab: DocumentTab) -> list[OverlayGraphic]:
    layer = tab.view.fill_layer
    assert layer is not None
    return [g for g in layer.graphics.values() if g.scene() is not None]


def pointer_to(tab: DocumentTab, x: float, y: float) -> None:
    """Hover the pointer over page point (x, y): a mouse-move event to the canvas. (Not
    QTest.mouseMove: on a real X display that moves the system pointer, whose events
    arrive late; and Qt drops a move to where the pointer already is.)"""
    vp = tab.view.viewport()
    pos = QPointF(ui.at(tab, x, y))
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos,
        QPointF(vp.mapToGlobal(pos.toPoint())),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(vp, event)
    QApplication.processEvents()


def same_but_moved(a: OverlayItem, b: OverlayItem) -> bool:
    keep = ("kind", "text", "font_size", "color", "image", "rotation", "opacity")
    if any(getattr(a, k) != getattr(b, k) for k in keep) or a.id == b.id:
        return False
    wa, ha = a.rect[2] - a.rect[0], a.rect[3] - a.rect[1]
    wb, hb = b.rect[2] - b.rect[0], b.rect[3] - b.rect[1]
    return abs(wa - wb) < 0.01 and abs(ha - hb) < 0.01


KINDS = ["text", "date", "check", "cross", "dot", "line", "signature", "initials", "stamp"]


@pytest.mark.parametrize("kind", KINDS)
def test_copy_paste_each_kind_at_the_pointer(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes, kind: str
) -> None:
    original = sample(kind, png)
    tab = setup(window, text_pdf, [original])
    (graphic,) = graphics(tab)
    original = graphic.item.moved_to(graphic.scene_rect_in_page())  # as drawn (text fits)
    ui.click(tab, ui.centre_of(graphic))
    assert graphic.isSelected()
    trigger_shortcut(window, "Ctrl+C")
    pointer_to(tab, 400, 600)
    trigger_shortcut(window, "Ctrl+V")
    items = list(tab.model.items.values())
    assert len(items) == 2
    copy = next(i for i in items if i.id != original.id)
    assert same_but_moved(original, copy)
    x0, y0 = min(copy.rect[0], copy.rect[2]), min(copy.rect[1], copy.rect[3])
    assert (x0, y0) == pytest.approx((400, 600), abs=1.0)  # top-left at the pointer
    tab.model.undo_stack.undo()  # one step takes the whole paste back
    assert list(tab.model.items) == [original.id]


def test_paste_without_pointer_on_a_page_offsets_by_10pt(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes
) -> None:
    original = sample("check", png)
    tab = setup(window, text_pdf, [original])
    (graphic,) = graphics(tab)
    ui.click(tab, ui.centre_of(graphic))
    trigger_shortcut(window, "Ctrl+C")
    QApplication.sendEvent(tab.view.viewport(), _leave())  # pointer leaves the canvas
    trigger_shortcut(window, "Ctrl+V")
    copy = next(i for i in tab.model.items.values() if i.id != original.id)
    assert copy.rect[0] == pytest.approx(original.rect[0] + 10)
    assert copy.rect[1] == pytest.approx(original.rect[1] + 10)


def _leave() -> object:
    from PySide6.QtCore import QEvent

    return QEvent(QEvent.Type.Leave)


def test_cut_then_paste(qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes) -> None:
    tab = setup(window, text_pdf, [sample("text", png)])
    (graphic,) = graphics(tab)
    original = graphic.item.moved_to(graphic.scene_rect_in_page())  # as drawn
    ui.click(tab, ui.centre_of(graphic))
    trigger_shortcut(window, "Ctrl+X")
    assert tab.model.items == {}
    pointer_to(tab, 300, 500)
    trigger_shortcut(window, "Ctrl+V")
    (copy,) = tab.model.items.values()
    assert same_but_moved(original, copy)


def test_duplicate_offsets_and_leaves_the_clipboard_alone(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes, fake_clipboard: FakeClipboard
) -> None:
    fake_clipboard.setText("something else")
    original = sample("stamp", png)
    tab = setup(window, text_pdf, [original])
    ui.click(tab, ui.centre_of(graphics(tab)[0]))
    trigger_shortcut(window, "Ctrl+D")
    copy = next(i for i in tab.model.items.values() if i.id != original.id)
    assert same_but_moved(original, copy)
    assert copy.rect[0] == pytest.approx(original.rect[0] + 10)
    assert fake_clipboard.text() == "something else"
    assert next(g for g in graphics(tab) if g.isSelected()).item.id == copy.id


def test_context_menu_actions(qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes) -> None:
    original = sample("dot", png)
    tab = setup(window, text_pdf, [original])
    (graphic,) = graphics(tab)
    menu = tab.view.item_menu(ui.centre_of(graphic))
    labels = [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]
    assert labels[:5] == ["Copy", "Cut", "Paste", "Duplicate", "Delete"]
    assert graphic.isSelected()  # right-click selects what's under it
    actions = {a.text(): a for a in menu.actions()}
    actions["Duplicate"].trigger()
    assert len(tab.model.items) == 2
    actions["Delete"].trigger()  # deletes the selection (now the duplicate)
    assert list(tab.model.items) == [original.id]


def test_paste_across_tabs(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, tmp_path: Path, png: bytes
) -> None:
    original = sample("signature", png)
    a = setup(window, text_pdf, [original])
    ui.click(a, ui.centre_of(graphics(a)[0]))
    trigger_shortcut(window, "Ctrl+C")
    b = ui.open_tab(window, make_text_pdf(tmp_path / "other.pdf", 2))
    pointer_to(b, 150, 200)
    trigger_shortcut(window, "Ctrl+V")
    (copy,) = b.model.items.values()
    assert same_but_moved(original, copy)


# --- several at once -----------------------------------------------------------------


def three(window: MainWindow, path: Path, png: bytes) -> tuple[DocumentTab, list[OverlayGraphic]]:
    items = [  # below the page's text: a drag from empty space here is a band
        OverlayItem("check", 0, (100, 790, 118, 808), font_size=18),
        OverlayItem("text", 0, (160, 790, 240, 807), text="Two"),
        OverlayItem("dot", 0, (260, 790, 278, 808), font_size=18),
    ]
    tab = setup(window, path, items)
    by_id = {g.item.id: g for g in graphics(tab)}
    return tab, [by_id[i.id] for i in items]


@pytest.mark.parametrize("modifier", [SHIFT, CTRL], ids=["shift", "ctrl"])
def test_modifier_click_adds_to_the_selection(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes, modifier: Qt.KeyboardModifier
) -> None:
    tab, (a, b, c) = three(window, text_pdf, png)
    ui.click(tab, ui.centre_of(a))
    ui.click(tab, ui.centre_of(c), modifier)
    assert a.isSelected() and c.isSelected() and not b.isSelected()
    ui.click(tab, ui.centre_of(a), modifier)  # and toggles off again
    assert not a.isSelected() and c.isSelected()


def test_rubber_band_selects_moves_and_deletes_together(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes
) -> None:
    tab, group = three(window, text_pdf, png)
    ui.drag(tab, ui.at(tab, 90, 780), ui.at(tab, 290, 815))  # empty space around all three
    assert all(g.isSelected() for g in group)
    assert tab.view.selection.is_empty  # a band, not a page-text selection
    before = {g.item.id: g.pos() for g in group}
    start = ui.centre_of(group[0])
    ui.drag(tab, start, start + QPoint(40, -60))
    for g in group:
        shift = g.pos() - before[g.item.id]
        assert (shift.x(), shift.y()) == pytest.approx((40, -60), abs=1)  # all moved together
        assert tab.model.items[g.item.id].rect[0] == pytest.approx(g.pos().x(), abs=0.01)
    tab.model.undo_stack.undo()  # the group move is one step
    assert all(g.pos() == before[g.item.id] for g in group)
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Delete)
    assert tab.model.items == {}
    tab.model.undo_stack.undo()  # and the group delete is one step too
    assert len(tab.model.items) == 3


def test_copy_paste_several_keeps_their_layout(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes
) -> None:
    tab, group = three(window, text_pdf, png)
    ui.drag(tab, ui.at(tab, 90, 780), ui.at(tab, 290, 815))
    trigger_shortcut(window, "Ctrl+C")
    pointer_to(tab, 100, 600)
    trigger_shortcut(window, "Ctrl+V")
    new = [i for i in tab.model.items.values() if i.id not in {g.item.id for g in group}]
    assert sorted(i.kind for i in new) == ["check", "dot", "text"]
    old_x = sorted(g.item.rect[0] for g in group)
    new_x = sorted(i.rect[0] for i in new)
    assert [n - new_x[0] for n in new_x] == pytest.approx([o - old_x[0] for o in old_x])
    assert {round(i.rect[1]) for i in new} == {600}
    tab.model.undo_stack.undo()
    assert len(tab.model.items) == 3


# --- from other apps; text selection keeps working -----------------------------------


def test_pasting_an_image_from_another_app_makes_a_stamp(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, fake_clipboard: FakeClipboard
) -> None:
    tab = setup(window, text_pdf, [])
    image = QImage(200, 100, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    fake_clipboard.setImage(image)
    pointer_to(tab, 200, 400)
    trigger_shortcut(window, "Ctrl+V")
    (item,) = tab.model.items.values()
    assert item.kind == "stamp" and item.image
    assert (item.rect[0], item.rect[1]) == pytest.approx((200, 400), abs=1)
    assert (item.rect[2] - item.rect[0]) / (item.rect[3] - item.rect[1]) == pytest.approx(2.0)


def test_pasting_plain_text_from_another_app_makes_a_text_item(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, fake_clipboard: FakeClipboard
) -> None:
    tab = setup(window, text_pdf, [])
    fake_clipboard.setText("12 Kloof Street")
    pointer_to(tab, 200, 400)
    trigger_shortcut(window, "Ctrl+V")
    (item,) = tab.model.items.values()
    assert (item.kind, item.text) == ("text", "12 Kloof Street")
    assert (item.rect[0], item.rect[1]) == pytest.approx((200, 400), abs=1)


def test_ctrl_c_on_selected_page_text_still_copies_text(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes, fake_clipboard: FakeClipboard
) -> None:
    tab = setup(window, text_pdf, [sample("check", png)])
    ui.drag(tab, ui.at(tab, 80, 118), ui.at(tab, 400, 160))  # page text (panel open too)
    assert not tab.view.selection.is_empty
    trigger_shortcut(window, "Ctrl+C")
    assert "quick brown fox" in fake_clipboard.text()


def test_ctrl_c_while_typing_in_an_item_copies_its_text_not_the_item(
    qtbot: QtBot, window: MainWindow, text_pdf: Path, png: bytes, fake_clipboard: FakeClipboard
) -> None:
    tab = setup(window, text_pdf, [sample("text", png)])
    (graphic,) = graphics(tab)
    assert isinstance(graphic, TextGraphic)
    ui.double_click(tab, ui.centre_of(graphic))
    assert graphic.editing
    cursor = graphic.editor.textCursor()
    cursor.select(cursor.SelectionType.Document)
    graphic.editor.setTextCursor(cursor)
    tab.view.copy_any()  # what Ctrl+C runs
    assert fake_clipboard.text() == "Copied text"
    assert not fake_clipboard.mime.hasFormat("application/x-pdr-sign-items")
