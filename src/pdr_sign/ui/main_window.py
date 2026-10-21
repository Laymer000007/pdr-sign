"""Top-level window. Phase 0: header bar and the empty state only."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from pdr_sign import APP_NAME, APP_SHORT_NAME
from pdr_sign.ui import icons
from pdr_sign.ui.theme import HEADER_HEIGHT, SPACING, Tokens


class EmptyState(QWidget):
    """Centred drop zone shown when no document is open."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        zone = QWidget(self)
        zone.setObjectName("DropZone")
        zone.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        zone.setFixedSize(420, 240)

        self.glyph = QLabel(zone)
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Open a PDF or drop it here", zone)
        title.setObjectName("DropZoneTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Press Ctrl+O to browse", zone)
        hint.setObjectName("Muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        inner = QVBoxLayout(zone)
        inner.setSpacing(SPACING)
        inner.addStretch()
        inner.addWidget(self.glyph)
        inner.addWidget(title)
        inner.addWidget(hint)
        inner.addStretch()

        outer = QVBoxLayout(self)
        outer.addStretch()
        outer.addWidget(zone, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()

    def set_tokens(self, t: Tokens) -> None:
        self.glyph.setPixmap(icons.pixmap("file-text", t.muted, 40, self.devicePixelRatioF()))


class HeaderBar(QWidget):
    """48 px header. Controls arrive in Phase 1 (``ui/header_bar.py``)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(HEADER_HEIGHT)
        title = QLabel(APP_SHORT_NAME, self)
        title.setObjectName("HeaderTitle")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING * 2, 0, SPACING * 2, 0)
        layout.addStretch()
        layout.addWidget(title)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self, tokens: Tokens) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 780)
        self.setMinimumSize(640, 480)

        self.header = HeaderBar(self)
        self.empty_state = EmptyState(self)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.empty_state, 1)
        self.setCentralWidget(central)

        self.tokens = tokens
        self.set_tokens(tokens)

    def set_tokens(self, t: Tokens) -> None:
        """Re-apply theme-dependent bits that QSS can't reach (icon colours)."""
        self.tokens = t
        self.empty_state.set_tokens(t)
