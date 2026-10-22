"""Panel strip of saved signatures (or initials): pick one to place, add, delete."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QGridLayout, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget

from pdr_sign.services.signatures import MAX_PER_KIND, SignatureKind
from pdr_sign.ui import icons
from pdr_sign.ui.signature_library import LibraryItem
from pdr_sign.ui.theme import SPACING, Tokens

THUMB = QSize(64, 28)
COLUMNS = 3


class SavedStrip(QWidget):
    chosen = Signal(str, str)  # kind, id
    new_requested = Signal(str)  # kind
    delete_requested = Signal(str, str)  # kind, id

    def __init__(self, kind: SignatureKind, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        noun = "Initials" if kind == "initials" else "Signatures"
        self.title = QLabel(noun)
        self.title.setObjectName("SectionTitle")
        self.grid = QGridLayout()
        self.grid.setSpacing(SPACING // 2)
        # Fixed-size tiles packed from the left, so rows line up whatever their count.
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.add_button = QToolButton()
        self.add_button.setObjectName("SavedAdd")
        self.add_button.setToolTip(f"New {kind}…")
        self.add_button.setAccessibleName(f"New {kind}")
        self.add_button.setFixedSize(THUMB + QSize(12, 12))
        self.add_button.clicked.connect(lambda: self.new_requested.emit(self.kind))
        self.buttons: list[QToolButton] = []
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING // 2)
        column.addWidget(self.title)
        column.addLayout(self.grid)
        self.set_items([])

    def set_tokens(self, t: Tokens) -> None:
        self.add_button.setIcon(icons.icon("plus", t.text, 16))

    def set_items(self, items: list[LibraryItem]) -> None:
        for button in self.buttons:
            self.grid.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        noun = "initials" if self.kind == "initials" else "signature"
        for n, item in enumerate(items):
            pixmap = QPixmap()
            pixmap.loadFromData(item.png, "PNG")
            button = QToolButton()
            button.setObjectName("SavedSignature")
            button.setIcon(QIcon(pixmap))
            button.setIconSize(THUMB)
            button.setFixedSize(THUMB + QSize(12, 12))
            where = "saved on this computer" if item.saved else "this session only"
            button.setToolTip(f"Place this {noun} ({where}). Right-click to delete.")
            button.setAccessibleName(f"{noun.capitalize()} {n + 1}")
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.clicked.connect(lambda _=False, i=item.id: self.chosen.emit(self.kind, i))
            button.customContextMenuRequested.connect(
                lambda pos, b=button, i=item.id: self._menu(b, pos, i)
            )
            self.grid.addWidget(button, n // COLUMNS, n % COLUMNS)
            self.buttons.append(button)
        self.grid.removeWidget(self.add_button)
        n = len(items)
        self.grid.addWidget(self.add_button, n // COLUMNS, n % COLUMNS)
        full = sum(1 for i in items if i.saved) >= MAX_PER_KIND
        self.add_button.setToolTip(
            f"New {noun}… (you have {MAX_PER_KIND}; saving another replaces the oldest)"
            if full
            else f"New {noun}…"
        )

    def _menu(self, button: QToolButton, pos: QPoint, item_id: str) -> None:
        menu = QMenu(self)
        delete = menu.addAction("Delete")
        delete.triggered.connect(lambda: self.delete_requested.emit(self.kind, item_id))
        menu.exec(button.mapToGlobal(pos))
