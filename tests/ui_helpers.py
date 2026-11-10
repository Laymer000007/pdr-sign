"""Real-mouse helpers shared by the interaction tests (clicks and drags on the canvas)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.ui.document_tab import DocumentTab
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.overlay.base import OverlayGraphic

LEFT = Qt.MouseButton.LeftButton


def make_window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    settings = Settings(theme="light", signature_dir=str(tmp_path / "sigs"))
    w = build_window(configure(qapp, settings), settings, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.resize(1100, 800)
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
    return tab


def at(tab: DocumentTab, x: float, y: float, page: int = 0) -> QPoint:
    """Viewport position of page point (x, y)."""
    view = tab.view
    return view.mapFromScene(view.page_items[page].mapToScene(QPointF(x, y)))


def centre_of(graphic: OverlayGraphic) -> QPoint:
    view = graphic.scene().views()[0]
    return view.mapFromScene(graphic.mapToScene(graphic.content_rect().center()))


def click(tab: DocumentTab, pos: QPoint, modifiers: Qt.KeyboardModifier | None = None) -> None:
    mods = modifiers if modifiers is not None else Qt.KeyboardModifier.NoModifier
    QTest.mouseClick(tab.view.viewport(), LEFT, mods, pos)
    QApplication.processEvents()


def double_click(tab: DocumentTab, pos: QPoint) -> None:
    QTest.mouseDClick(tab.view.viewport(), LEFT, Qt.KeyboardModifier.NoModifier, pos)
    QApplication.processEvents()


def drag(tab: DocumentTab, start: QPoint, end: QPoint, steps: int = 10) -> None:
    vp = tab.view.viewport()
    QTest.mousePress(vp, LEFT, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, steps + 1):
        QTest.mouseMove(vp, start + (end - start) * step / steps)
    QTest.mouseRelease(vp, LEFT, Qt.KeyboardModifier.NoModifier, end)
    QApplication.processEvents()
