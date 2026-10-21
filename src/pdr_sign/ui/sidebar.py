"""Left sidebar: page thumbnails and the document outline."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services.document import Document, OutlineEntry
from pdr_sign.ui.render_scheduler import RenderRequest, RenderScheduler
from pdr_sign.ui.theme import SIDEBAR_WIDTH

THUMB_WIDTH = 120
PAGE_ROLE = Qt.ItemDataRole.UserRole
Y_ROLE = Qt.ItemDataRole.UserRole + 1


def untinted_icon(pixmap: QPixmap) -> QIcon:
    """Same pixmap for every mode, so Qt doesn't tint the selected thumbnail."""
    icon = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
        icon.addPixmap(pixmap, mode)
    return icon


class ThumbnailList(QListWidget):
    page_activated = Signal(int)

    def __init__(self, doc: Document, scheduler: RenderScheduler) -> None:
        super().__init__()
        self.doc = doc
        self.scheduler = scheduler
        self.owner = f"thumbs-{id(self)}"
        self.setObjectName("Thumbnails")
        self.setAccessibleName("Page thumbnails")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setWrapping(False)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(False)
        self.setSpacing(6)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        tallest = max(p.height / p.width for p in doc.pages)
        self.setIconSize(QSize(THUMB_WIDTH, round(THUMB_WIDTH * tallest)))
        for info in doc.pages:
            item = QListWidgetItem(info.label)
            item.setData(PAGE_ROLE, info.index)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setIcon(self._placeholder(info.width, info.height))
            thumb_h = round(THUMB_WIDTH * info.height / info.width)
            item.setSizeHint(QSize(SIDEBAR_WIDTH - 28, thumb_h + 32))
            self.addItem(item)
        self.set_current(0)

        self._timer = QTimer(self, singleShot=True, interval=30)
        self._timer.timeout.connect(self.request_visible)
        # Not connect(self._timer.start): the int argument would become the interval.
        self.verticalScrollBar().valueChanged.connect(lambda _: self._timer.start())
        self.itemClicked.connect(lambda it: self.page_activated.emit(it.data(PAGE_ROLE)))
        self.itemActivated.connect(lambda it: self.page_activated.emit(it.data(PAGE_ROLE)))
        scheduler.tile_ready.connect(self._on_ready)

    def _key(self, index: int) -> tuple[int, int, str, int, float]:
        return (self.doc.id, index, "thumb", THUMB_WIDTH, round(self.devicePixelRatioF(), 2))

    def _placeholder(self, w: float, h: float) -> QIcon:
        px = QPixmap(QSize(THUMB_WIDTH, round(THUMB_WIDTH * h / w)))
        px.fill(QColor("white"))
        return untinted_icon(px)

    def set_current(self, index: int) -> None:
        item = self.item(index)
        if item is not None and self.currentRow() != index:
            self.blockSignals(True)
            self.setCurrentRow(index)
            self.blockSignals(False)
            self.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._timer.start()

    def request_visible(self) -> None:
        if not self.isVisible() or self.count() == 0:
            return
        top = self.indexAt(self.viewport().rect().topLeft() + self._probe()).row()
        bottom = self.indexAt(self.viewport().rect().bottomLeft() + self._probe(-1)).row()
        top = max(0, top)
        bottom = self.count() - 1 if bottom < 0 else bottom
        dpr = self.devicePixelRatioF()
        requests = []
        for index in range(top, min(self.count(), bottom + 3)):
            info = self.doc.pages[index]
            key = self._key(index)
            if self.scheduler.pixmap(key) is not None:
                self._apply(index)
                continue
            zoom = THUMB_WIDTH / info.width
            requests.append(RenderRequest(key, self.doc, index, zoom, dpr))
        self.scheduler.set_wanted(self.owner, requests, priority=1)

    def _probe(self, dy: int = 1) -> QPoint:
        return QPoint(self.viewport().width() // 2, dy * 8)

    def _on_ready(self, key: object) -> None:
        if isinstance(key, tuple) and len(key) == 5 and key[0] == self.doc.id and key[2] == "thumb":
            self._apply(key[1])

    def _apply(self, index: int) -> None:
        pixmap = self.scheduler.pixmap(self._key(index))
        item = self.item(index)
        if pixmap is not None and item is not None:
            pixmap.setDevicePixelRatio(self.devicePixelRatioF())
            item.setIcon(untinted_icon(pixmap))

    def release(self) -> None:
        self.scheduler.forget(self.owner)
        self.scheduler.tile_ready.disconnect(self._on_ready)


class OutlineTree(QStackedWidget):
    destination_activated = Signal(int, object)  # page, y | None

    def __init__(self, entries: list[OutlineEntry]) -> None:
        super().__init__()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        self.tree.setAccessibleName("Document outline")
        self.tree.setUniformRowHeights(True)
        empty = QLabel("This document has no outline")
        empty.setObjectName("Muted")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        self.addWidget(self.tree)
        self.addWidget(empty)
        self._populate(entries)
        self.tree.expandToDepth(0)
        self.setCurrentIndex(0 if entries else 1)
        self.tree.itemActivated.connect(self._activate)
        self.tree.itemClicked.connect(self._activate)

    def _populate(self, entries: list[OutlineEntry]) -> None:
        parents: list[QTreeWidgetItem] = []
        for entry in entries:
            depth = max(0, min(entry.level - 1, len(parents)))
            del parents[depth:]
            item = QTreeWidgetItem([entry.title])
            item.setToolTip(0, entry.title)
            item.setData(0, PAGE_ROLE, entry.page)
            item.setData(0, Y_ROLE, entry.y)
            if parents:
                parents[-1].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            parents.append(item)

    def _activate(self, item: QTreeWidgetItem) -> None:
        page = item.data(0, PAGE_ROLE)
        if isinstance(page, int) and page >= 0:
            self.destination_activated.emit(page, item.data(0, Y_ROLE))


class Sidebar(QWidget):
    def __init__(self, doc: Document, scheduler: RenderScheduler) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.thumbnails = ThumbnailList(doc, scheduler)
        self.outline = OutlineTree(doc.outline())
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.thumbnails, "Thumbnails")
        self.tabs.addTab(self.outline, "Outline")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
