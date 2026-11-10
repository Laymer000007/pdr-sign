"""The document tab bar: reorder by dragging along it, drag a tab out of it (or use its
right-click menu) to move the document to a new window."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QMenu, QTabBar, QWidget

DETACH_DISTANCE = 40  # px out of the bar, up or down, before a dragged tab leaves


class DocumentTabBar(QTabBar):
    move_to_new_window = Signal(int)  # tab index
    close_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DocumentTabs")
        self.setDocumentMode(True)
        self.setMovable(True)
        self.setExpanding(False)
        self.setElideMode(Qt.TextElideMode.ElideMiddle)
        self._dragged: int = -1

    def menu_for(self, index: int) -> QMenu:
        menu = QMenu(self)
        move = menu.addAction("Move to New Window")
        move.triggered.connect(lambda: self.move_to_new_window.emit(index))
        menu.addSeparator()
        close = menu.addAction("Close")
        close.setShortcut("Ctrl+W")
        close.triggered.connect(lambda: self.close_requested.emit(index))
        return menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        index = self.tabAt(event.pos())
        if index >= 0:
            self.menu_for(index).exec(event.globalPos())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragged = self.tabAt(event.position().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        outside = pos.y() < -DETACH_DISTANCE or pos.y() > self.height() + DETACH_DISTANCE
        if self._dragged >= 0 and event.buttons() & Qt.MouseButton.LeftButton and outside:
            index, self._dragged = self._dragged, -1
            self._end_internal_drag(pos)
            self.move_to_new_window.emit(index)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragged = -1
        super().mouseReleaseEvent(event)

    def _end_internal_drag(self, pos: QPoint) -> None:
        """Let QTabBar finish its own reorder drag (it would otherwise keep the tab
        floating until a release that now goes elsewhere)."""
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(pos),
            QPointF(self.mapToGlobal(pos)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        super().mouseReleaseEvent(release)
