"""Fill & Sign (Phase 3): form-field editors, overlay tools, undo/redo."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QListWidget, QPlainTextEdit
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services import forms, stamps
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.check_item import MarkGraphic
from pdr_sign.ui.overlay.field_widgets import FieldProxy, ToggleField
from pdr_sign.ui.overlay.text_item import TextGraphic
from tests.conftest import trigger_shortcut


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    from pdr_sign.ui import dialogs

    monkeypatch.setattr(dialogs, "show_error", lambda *_: None)


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
        w.close_tab(tab)


def needs_focus(window: MainWindow) -> None:
    """Focus-in/out only happens in an active window. A desktop session (xcb on a real
    display) may refuse to activate a test window; offscreen and xvfb don't."""
    if not window.isActiveWindow():
        pytest.skip("window could not be activated, so keyboard focus can't be tested")


def open_tab(window: MainWindow, path: Path) -> DocumentTab:
    window.open_paths([str(path)])
    tab = window.current_tab()
    assert tab is not None
    tab.view.set_zoom(1.0)
    tab.view.go_to_page(0)
    return tab


def proxies(tab: DocumentTab) -> dict[str, FieldProxy]:
    layer = tab.view.field_layer
    assert layer is not None
    return {g.field.name: g for g in layer.graphics if isinstance(g, FieldProxy)}


def toggles(tab: DocumentTab, name: str) -> list[ToggleField]:
    layer = tab.view.field_layer
    assert layer is not None
    return [g for g in layer.by_name[name] if isinstance(g, ToggleField)]


def view_pos(tab: DocumentTab, page: int, point: QPointF) -> object:
    view = tab.view
    return view.mapFromScene(view.page_items[page].mapToScene(point))


# --- form fields --------------------------------------------------------------


def test_every_fillable_field_gets_an_editor(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    p = proxies(tab)
    assert isinstance(p["name"].widget(), QLineEdit)
    assert isinstance(p["notes"].widget(), QPlainTextEdit)
    assert isinstance(p["country"].widget(), QComboBox)
    assert p["city"].widget().isEditable()  # type: ignore[attr-defined]
    assert isinstance(p["fruit"].widget(), QListWidget)
    assert "ref" not in p  # read-only: shown by the page itself
    assert "signature" not in p
    assert len(toggles(tab, "colour")) == 3 and len(toggles(tab, "agree")) == 1
    # Editors sit exactly on the field rectangles (page points).
    field = p["name"].field
    assert p["name"].geometry().getCoords() == pytest.approx(field.rect)


def test_typing_in_fields_updates_model_with_undo(
    qtbot: QtBot, window: MainWindow, form_pdf: Path
) -> None:
    tab = open_tab(window, form_pdf)
    line = proxies(tab)["name"].widget()
    assert isinstance(line, QLineEdit)
    line.setText("Jane")
    line.editingFinished.emit()
    assert tab.model.values["name"] == "Jane"
    assert tab.model.dirty
    assert window.tab_bar.tabText(0).startswith("• ") or window.windowTitle().startswith("• ")

    trigger_shortcut(window, "Ctrl+Z")
    assert tab.model.values["name"] == "" and line.text() == ""
    assert not tab.model.dirty
    trigger_shortcut(window, "Ctrl+Shift+Z")
    assert line.text() == "Jane"


def test_checkbox_radio_combo_list(window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    (agree,) = toggles(tab, "agree")
    agree.toggled.emit()
    assert tab.model.values["agree"] == "Yes" and agree.checked
    agree.toggled.emit()
    assert tab.model.values["agree"] == ""

    red, green, blue = toggles(tab, "colour")
    green.toggled.emit()
    assert tab.model.values["colour"] == "green"
    assert (red.checked, green.checked, blue.checked) == (False, True, False)
    blue.toggled.emit()
    assert (green.checked, blue.checked) == (False, True)

    combo = proxies(tab)["country"].widget()
    assert isinstance(combo, QComboBox)
    combo.setCurrentIndex(combo.findData("DE"))
    combo.activated.emit(combo.currentIndex())
    assert tab.model.values["country"] == "DE"

    box = proxies(tab)["fruit"].widget()
    assert isinstance(box, QListWidget)
    box.item(0).setSelected(True)
    assert tab.model.values["fruit"] == ("apple",)


def test_space_toggles_and_tab_order(qtbot: QtBot, window: MainWindow, form_pdf: Path) -> None:
    tab = open_tab(window, form_pdf)
    (agree,) = toggles(tab, "agree")
    agree.setFocus()
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Space)
    assert tab.model.values["agree"] == "Yes"
    layer = tab.view.field_layer
    assert layer is not None
    order = [g.field.order for g in layer.graphics]
    assert order == sorted(order)  # tab chain follows the PDF's field order


def test_panel_lists_fields_and_focuses_them(window: MainWindow, form_pdf: Path) -> None:
    needs_focus(window)
    tab = open_tab(window, form_pdf)
    window.set_fill_mode(True)
    names = [tab.panel.fields.item(i).text() for i in range(tab.panel.fields.count())]
    assert names[0] == "Full name" and "city_again" in names
    assert "ref" not in names and "signature" not in names
    tab.panel.field_activated.emit("city_again")  # on page 2
    assert tab.view.current_page == 1


# --- overlay tools ------------------------------------------------------------------


def test_check_tool_places_moves_and_undoes(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab = open_tab(window, text_pdf)
    trigger_shortcut(window, "Ctrl+E")
    assert window.fill_mode and tab.panel_visible
    tab.panel._buttons["check"].click()
    layer = tab.view.fill_layer
    assert layer is not None and layer.tool == "check"
    pos = view_pos(tab, 0, QPointF(200, 300))
    QTest.mouseClick(tab.view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    QTest.mouseClick(
        tab.view.viewport(), Qt.MouseButton.LeftButton, pos=view_pos(tab, 0, QPointF(260, 300))
    )
    assert len(tab.model.items) == 2  # the mark tool stays active
    first = next(iter(tab.model.items.values()))
    assert first.kind == "check"
    assert (first.rect[0] + first.rect[2]) / 2 == pytest.approx(200)

    graphic = layer.graphics[first.id]
    assert isinstance(graphic, MarkGraphic)
    graphic.setPos(graphic.pos() + QPointF(30, 40))
    graphic.commit()
    moved = tab.model.items[first.id]
    assert moved.rect[1] == pytest.approx(first.rect[1] + 40)

    trigger_shortcut(window, "Ctrl+Z")  # undo the move
    assert tab.model.items[first.id].rect == pytest.approx(first.rect)
    assert graphic.pos().y() == pytest.approx(first.rect[1])
    trigger_shortcut(window, "Ctrl+Z")
    trigger_shortcut(window, "Ctrl+Z")
    assert tab.model.items == {}
    assert not tab.model.dirty


def test_delete_key_removes_selected_item(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("cross")
    graphic = layer.place(0, QPointF(100, 100))
    assert graphic is not None and graphic.isSelected()
    layer.set_tool("")
    graphic.setFocus()
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Delete)
    assert tab.model.items == {}
    trigger_shortcut(window, "Ctrl+Z")
    assert len(tab.model.items) == 1


def test_text_tool_creates_item_only_when_typed(window: MainWindow, text_pdf: Path) -> None:
    needs_focus(window)
    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("text")
    empty = layer.place(0, QPointF(100, 100))
    assert isinstance(empty, TextGraphic) and empty.editing
    assert layer.tool == ""  # one-shot
    empty.editor.clearFocus()
    assert tab.model.items == {} and empty.scene() is None  # nothing typed: gone

    layer.set_tool("text")
    graphic = layer.place(0, QPointF(100, 200))
    assert isinstance(graphic, TextGraphic)
    graphic.editor.setPlainText("Hello\nworld")
    graphic.editor.clearFocus()
    (item,) = tab.model.items.values()
    assert item.text == "Hello\nworld" and item.kind == "text"
    assert item.rect[3] - item.rect[1] > item.font_size * 2  # grew to two lines

    layer.apply_style(18, stamps.TEXT_COLORS["blue"])  # panel restyles the selection
    restyled = tab.model.items[item.id]
    assert (restyled.font_size, restyled.color) == (18, stamps.TEXT_COLORS["blue"])


def test_date_tool_uses_locale_date(window: MainWindow, text_pdf: Path) -> None:
    from pdr_sign.ui.fill_layer import today_text

    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("date")
    layer.place(1, QPointF(300, 400))
    (item,) = tab.model.items.values()
    assert item.kind == "date" and item.page == 1 and item.text == today_text()


def test_items_stay_on_the_page(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("dot")
    graphic = layer.place(0, QPointF(1, 1))
    assert graphic is not None
    x0, y0, _, _ = graphic.scene_rect_in_page()
    assert x0 >= 0 and y0 >= 0
    graphic.setPos(QPointF(5000, 5000))
    x0, y0, x1, y1 = graphic.scene_rect_in_page()
    assert x1 <= 595 + 1e-6 and y1 <= 842 + 1e-6


def test_drag_selects_text_only_without_a_tool(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("check")
    start, end = view_pos(tab, 0, QPointF(80, 80)), view_pos(tab, 0, QPointF(200, 130))
    QTest.mousePress(tab.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(tab.view.viewport(), end)
    QTest.mouseRelease(tab.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert tab.view.selection.is_empty and len(tab.model.items) == 1


def test_filled_values_apply_to_the_pdf(window: MainWindow, form_pdf: Path, tmp_path: Path) -> None:
    """What Save will do in Phase 5: the model's changes written into a copy."""
    tab = open_tab(window, form_pdf)
    tab.model.set_field_value("name", "Jane")
    tab.model.set_field_value("colour", "blue")
    forms.apply_values(tab.doc, tab.model.changed_values())
    with tab.doc.locked() as pdf:
        pdf.save(tmp_path / "out.pdf")
    from pdr_sign.services.document import Document

    values = forms.field_values(forms.list_fields(Document.open(tmp_path / "out.pdf")))
    assert values["name"] == "Jane" and values["colour"] == "blue"


# --- real pointer and keyboard input -------------------------------------------------


def test_mouse_drag_moves_and_handle_resizes(
    qtbot: QtBot, window: MainWindow, text_pdf: Path
) -> None:
    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("check")
    graphic = layer.place(0, QPointF(200, 300))
    layer.set_tool("")
    assert graphic is not None
    (item,) = tab.model.items.values()
    vp = tab.view.viewport()

    start = view_pos(tab, 0, QPointF(200, 300))
    end = view_pos(tab, 0, QPointF(250, 340))
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=start)
    for k in range(1, 6):
        QTest.mouseMove(vp, start + (end - start) * k / 5)
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=end)
    moved = tab.model.items[item.id]
    assert moved.rect[0] == pytest.approx(item.rect[0] + 50, abs=1.5)
    assert moved.rect[1] == pytest.approx(item.rect[1] + 40, abs=1.5)
    assert tab.model.undo_stack.count() == 2  # add + one move, not one per mouse step

    # Drag the bottom-right handle: a mark keeps its square shape.
    graphic.setSelected(True)
    corner = QPointF(moved.rect[2], moved.rect[3])
    start = view_pos(tab, 0, corner)
    end = view_pos(tab, 0, corner + QPointF(20, 6))
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=start)
    for k in range(1, 6):
        QTest.mouseMove(vp, start + (end - start) * k / 5)
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=end)
    resized = tab.model.items[item.id]
    w, h = resized.rect[2] - resized.rect[0], resized.rect[3] - resized.rect[1]
    assert w > 14 and w == pytest.approx(h, abs=0.01)
    assert resized.font_size == pytest.approx(h, abs=0.01)


def test_keyboard_typing_into_a_field(qtbot: QtBot, window: MainWindow, form_pdf: Path) -> None:
    needs_focus(window)
    tab = open_tab(window, form_pdf)
    proxy = proxies(tab)["name"]
    x0, y0, x1, y1 = proxy.field.rect
    pos = view_pos(tab, 0, QPointF((x0 + x1) / 2, (y0 + y1) / 2))
    QTest.mouseClick(tab.view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    QTest.keyClicks(tab.view.viewport(), "Ada")
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Home)  # moves the cursor, not the page
    QTest.keyClicks(tab.view.viewport(), "Dr ")
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Tab)  # commit, move to the next field
    assert tab.model.values["name"] == "Dr Ada"
    assert tab.view.current_page == 0


def test_double_click_edits_existing_text(qtbot: QtBot, window: MainWindow, text_pdf: Path) -> None:
    needs_focus(window)
    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("text")
    graphic = layer.place(0, QPointF(100, 200))
    assert isinstance(graphic, TextGraphic)
    graphic.editor.setPlainText("Draft")
    graphic.editor.clearFocus()
    x0, y0, x1, y1 = graphic.scene_rect_in_page()
    pos = view_pos(tab, 0, QPointF((x0 + x1) / 2, (y0 + y1) / 2))
    QTest.mouseDClick(tab.view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    assert graphic.editing
    QTest.keyClicks(tab.view.viewport(), " two")
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Escape)
    (item,) = tab.model.items.values()
    assert item.text == "Draft two"


# --- line tool ------------------------------------------------------------------------


def line_points(tab: DocumentTab) -> list[tuple[float, float, float, float]]:
    return [i.rect for i in tab.model.items.values() if i.kind == "line"]


def drag(tab: DocumentTab, start: QPointF, end: QPointF, shift: bool = False) -> None:
    """Press, move in steps, release, with Shift held throughout if asked.

    QTest.mouseMove can't carry keyboard modifiers, so the moves are real events.
    """
    vp = tab.view.viewport()
    mod = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    a, b = view_pos(tab, 0, start), view_pos(tab, 0, end)
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, mod, a)
    for k in range(1, 6):
        pos = QPointF(a + (b - a) * k / 5)
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            pos,
            QPointF(vp.mapToGlobal(pos)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            mod,
        )
        QApplication.sendEvent(vp, move)
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, mod, b)


def test_line_tool_click_places_default_line(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    window.set_fill_mode(True)
    button = tab.panel._buttons["line"]
    assert button.toolTip() == "Line"
    button.click()
    vp = tab.view.viewport()
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=view_pos(tab, 0, QPointF(100, 200)))
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=view_pos(tab, 0, QPointF(100, 260)))
    lines = line_points(tab)
    assert len(lines) == 2  # the tool stays active
    x1, y1, x2, y2 = lines[0]
    assert (x1, y1) == pytest.approx((100, 200), abs=1)
    assert (x2 - x1, y2 - y1) == pytest.approx((stamps.LINE_LENGTH, 0), abs=0.01)


def test_line_tool_drag_sets_length_and_shift_allows_angle(
    window: MainWindow, text_pdf: Path
) -> None:
    from pdr_sign.ui.overlay.line_item import angle_degrees

    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("line")
    drag(tab, QPointF(100, 300), QPointF(250, 340))  # no Shift: stays horizontal
    drag(tab, QPointF(100, 400), QPointF(200, 500), shift=True)
    flat, angled = (tab.model.items[k] for k in tab.model.items)
    assert flat.rect[2] - flat.rect[0] == pytest.approx(150, abs=1.5)
    assert flat.rect[1] == flat.rect[3]
    assert angle_degrees(angled) == pytest.approx(45, abs=1.5)


def test_line_handles_move_delete_undo(window: MainWindow, text_pdf: Path) -> None:
    from pdr_sign.ui.overlay.line_item import LineGraphic

    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("line")
    QTest.mouseClick(
        tab.view.viewport(), Qt.MouseButton.LeftButton, pos=view_pos(tab, 0, QPointF(100, 200))
    )
    layer.set_tool("")
    (item,) = tab.model.items.values()
    graphic = layer.graphics[item.id]
    assert isinstance(graphic, LineGraphic) and graphic.isSelected()

    # Drag the end handle out to 120 pt; without Shift it stays level.
    drag(tab, QPointF(140, 200), QPointF(220, 230))
    stretched = tab.model.items[item.id]
    assert stretched.rect == pytest.approx((100, 200, 220, 200), abs=1.5)

    # Drag the middle to move the whole line.
    drag(tab, QPointF(160, 200), QPointF(160, 260))
    moved = tab.model.items[item.id]
    assert moved.rect == pytest.approx((100, 260, 220, 260), abs=1.5)

    graphic.setFocus()
    QTest.keyClick(tab.view.viewport(), Qt.Key.Key_Delete)
    assert tab.model.items == {}
    for expected in (moved.rect, stretched.rect, item.rect):
        trigger_shortcut(window, "Ctrl+Z")
        assert tab.model.items[item.id].rect == pytest.approx(expected, abs=1.5)
        shown = layer.graphics[item.id]  # undoing the delete makes a fresh graphic
        assert shown.scene_rect_in_page() == pytest.approx(expected, abs=1.5)


def test_line_takes_ink_and_size_from_panel(window: MainWindow, text_pdf: Path) -> None:
    tab = open_tab(window, text_pdf)
    window.set_fill_mode(True)
    tab.panel.colors[stamps.TEXT_COLORS["blue"]].click()
    tab.panel.size_box.set_value(24, emit=True)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("line")
    QTest.mouseClick(
        tab.view.viewport(), Qt.MouseButton.LeftButton, pos=view_pos(tab, 0, QPointF(100, 200))
    )
    (item,) = tab.model.items.values()
    assert item.color == stamps.TEXT_COLORS["blue"] and item.font_size == 24
    tab.panel.size_box.set_value(8, emit=True)  # restyles the selected line
    assert tab.model.items[item.id].font_size == 8


def test_line_saves_and_reopens_from_the_ui(
    window: MainWindow, text_pdf: Path, tmp_path: Path
) -> None:
    from pdr_sign.services.document import Document

    tab = open_tab(window, text_pdf)
    layer = tab.view.fill_layer
    assert layer is not None
    layer.set_tool("line")
    drag(tab, QPointF(100, 300), QPointF(200, 360), shift=True)
    (item,) = tab.model.items.values()
    stamps.write_overlays(tab.doc, list(tab.model.items.values()))
    with tab.doc.locked() as pdf:
        pdf.save(tmp_path / "out.pdf")
    (back,) = stamps.read_overlays(Document.open(tmp_path / "out.pdf"))
    assert back.rect == pytest.approx(item.rect, abs=0.01)
