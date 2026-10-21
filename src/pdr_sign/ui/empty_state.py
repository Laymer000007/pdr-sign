"""Shown when no document is open: a drop zone and a grid of recent files."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services.recent import RecentEntry, thumbnail_path
from pdr_sign.ui import icons
from pdr_sign.ui.theme import SPACING, Tokens

CARD_THUMB = QSize(112, 150)
GRID_COLUMNS = 4


class EmptyState(QScrollArea):
    open_requested = Signal()
    recent_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        body = QWidget()
        body.setObjectName("EmptyStateBody")
        self.setWidget(body)

        self.zone = QWidget(body)
        self.zone.setObjectName("DropZone")
        self.zone.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.zone.setFixedSize(420, 220)
        self.glyph = QLabel(self.zone)
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Open a PDF or drop it here", self.zone)
        title.setObjectName("DropZoneTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browse = QPushButton("Open…", self.zone)
        self.browse.setProperty("primary", True)
        self.browse.setToolTip("Open a PDF (Ctrl+O)")
        self.browse.clicked.connect(self.open_requested)
        inner = QVBoxLayout(self.zone)
        inner.setSpacing(SPACING + SPACING // 2)
        inner.addStretch()
        inner.addWidget(self.glyph)
        inner.addWidget(title)
        inner.addWidget(self.browse, 0, Qt.AlignmentFlag.AlignHCenter)
        inner.addStretch()

        self.recent_title = QLabel("Recent")
        self.recent_title.setObjectName("SectionTitle")
        self.recent_grid = QGridLayout()
        self.recent_grid.setSpacing(SPACING * 2)

        outer = QVBoxLayout(body)
        outer.setContentsMargins(SPACING * 4, SPACING * 6, SPACING * 4, SPACING * 4)
        outer.setSpacing(SPACING * 3)
        outer.addStretch(1)
        outer.addWidget(self.zone, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self.recent_title, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(self.recent_grid)
        outer.addStretch(2)
        self.set_recent([])

    def set_tokens(self, t: Tokens) -> None:
        self.glyph.setPixmap(icons.pixmap("file-text", t.muted, 40, self.devicePixelRatioF()))

    def set_drag_active(self, active: bool) -> None:
        self.zone.setProperty("dragActive", active)
        self.zone.style().unpolish(self.zone)
        self.zone.style().polish(self.zone)

    def set_recent(self, entries: list[RecentEntry]) -> None:
        while self.recent_grid.count():
            item = self.recent_grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self.recent_title.setVisible(bool(entries))
        for n, entry in enumerate(entries):
            card = self._card(entry)
            self.recent_grid.addWidget(card, n // GRID_COLUMNS, n % GRID_COLUMNS)
        self.recent_grid.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    def _card(self, entry: RecentEntry) -> QToolButton:
        card = QToolButton()
        card.setObjectName("RecentCard")
        card.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        card.setIconSize(CARD_THUMB)
        card.setFixedWidth(CARD_THUMB.width() + SPACING * 3)
        name = entry.name if len(entry.name) <= 18 else entry.name[:16] + "…"
        card.setText(name)
        card.setToolTip(entry.path)
        card.setAccessibleName(f"Open recent file {entry.name}")
        thumb = thumbnail_path(entry.path)
        if thumb.is_file():
            card.setIcon(QIcon(QPixmap(str(thumb))))
        path = str(Path(entry.path))
        card.clicked.connect(lambda: self.recent_requested.emit(path))
        return card
