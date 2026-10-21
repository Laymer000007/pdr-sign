"""Create a signature or initials: Draw | Type | Upload."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services import sigimage
from pdr_sign.services.signatures import SignatureKind
from pdr_sign.ui import icons
from pdr_sign.ui.draw_pad import DrawPad, image_to_png
from pdr_sign.ui.theme import SPACING, Tokens
from pdr_sign.ui.upload_pad import UploadPad

TYPE_FONTS = ("Caveat", "Dancing Script")
TYPE_PX = 160  # render size for typed signatures (crisp when scaled down on the page)


def render_typed(text: str, family: str, color: QColor, px: int = TYPE_PX) -> bytes:
    """A typed name in a handwriting font, as a trimmed transparent PNG."""
    font = QFont(family)
    font.setPixelSize(px)
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(text) + px
    height = metrics.height() + px * 0.5
    image = QImage(
        QSize(max(1, round(width)), max(1, round(height))),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return sigimage.trim_png(image_to_png(image))


def segmented(
    labels: list[tuple[str, str]], group_parent: QWidget
) -> tuple[QHBoxLayout, dict[str, QToolButton]]:
    row = QHBoxLayout()
    row.setSpacing(SPACING // 2)
    group = QButtonGroup(group_parent)
    buttons: dict[str, QToolButton] = {}
    for key, text in labels:
        button = QToolButton()
        button.setObjectName("Segment")
        button.setText(text)
        button.setCheckable(True)
        button.setAccessibleName(text)
        group.addButton(button)
        row.addWidget(button)
        buttons[key] = button
    return row, buttons


class TypePad(QWidget):
    def __init__(self, kind: SignatureKind, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ink = QColor(*sigimage.INK_COLORS["black"])
        self.name = QLineEdit()
        self.name.setPlaceholderText("Your initials" if kind == "initials" else "Type your name")
        self.name.setAccessibleName(self.name.placeholderText())
        self.name.setMaxLength(60)
        self.tiles: dict[str, QToolButton] = {}
        tiles = QHBoxLayout()
        group = QButtonGroup(self)
        for family in TYPE_FONTS:
            tile = QToolButton()
            tile.setObjectName("StyleTile")
            tile.setCheckable(True)
            tile.setAccessibleName(f"{family} style")
            tile.setToolTip(family)
            tile.setMinimumSize(260, 120)
            tile.setIconSize(QSize(240, 96))
            group.addButton(tile)
            tiles.addWidget(tile)
            self.tiles[family] = tile
        self.tiles[TYPE_FONTS[0]].setChecked(True)
        self.name.textChanged.connect(lambda _: self.refresh())
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.name)
        column.addLayout(tiles, 1)
        self.refresh()

    @property
    def family(self) -> str:
        return next((f for f, t in self.tiles.items() if t.isChecked()), TYPE_FONTS[0])

    def refresh(self) -> None:
        text = self.name.text().strip() or "Your name"
        for family, tile in self.tiles.items():
            png = render_typed(text, family, self.ink, px=64)
            image = QImage.fromData(png, "PNG")  # type: ignore[arg-type]  # stub: bytes; runtime: str
            tile.setIcon(QIcon(QPixmap.fromImage(image)))

    def png(self) -> bytes | None:
        text = self.name.text().strip()
        return render_typed(text, self.family, self.ink) if text else None


class SignatureDialog(QDialog):
    """``exec()`` then read ``result_png`` and ``remember``."""

    def __init__(self, kind: SignatureKind, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        noun = "initials" if kind == "initials" else "signature"
        self.setWindowTitle(f"Create {noun}")
        self.setMinimumSize(760, 520)
        self.result_png: bytes | None = None

        self.draw = DrawPad()
        pen_row, self.pen_buttons = segmented(
            [("fine", "Fine"), ("medium", "Medium"), ("bold", "Bold")], self
        )
        self.pen_buttons["medium"].setChecked(True)
        for key, button in self.pen_buttons.items():
            button.clicked.connect(lambda _=False, k=key: self.draw.set_pen_width(k))
        ink_row, self.ink_buttons = segmented([("black", "Black"), ("blue", "Blue")], self)
        self.ink_buttons["black"].setChecked(True)
        for key, button in self.ink_buttons.items():
            button.clicked.connect(lambda _=False, k=key: self._set_ink(k))
        self.undo_button = QToolButton()
        self.undo_button.setText("Undo stroke")
        self.undo_button.setToolTip("Undo the last stroke (Ctrl+Z)")
        self.undo_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.undo_button.clicked.connect(self.draw.undo)
        self.clear_button = QToolButton()
        self.clear_button.setText("Clear")
        self.clear_button.setToolTip("Start again")
        self.clear_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.clear_button.clicked.connect(self.draw.clear)
        QShortcut(QKeySequence.StandardKey.Undo, self.draw, self.draw.undo)

        draw_tools = QHBoxLayout()
        draw_tools.addWidget(QLabel("Pen"))
        draw_tools.addLayout(pen_row)
        draw_tools.addSpacing(SPACING * 2)
        draw_tools.addWidget(QLabel("Ink"))
        draw_tools.addLayout(ink_row)
        draw_tools.addStretch()
        draw_tools.addWidget(self.undo_button)
        draw_tools.addWidget(self.clear_button)
        draw_tab = QWidget()
        draw_column = QVBoxLayout(draw_tab)
        draw_column.addWidget(self.draw, 1)
        draw_column.addLayout(draw_tools)

        self.type = TypePad(kind)
        type_tab = QWidget()
        type_column = QVBoxLayout(type_tab)
        type_column.addWidget(self.type, 1)
        type_hint = QLabel("Uses the ink colour chosen on the Draw tab.")
        type_hint.setObjectName("Muted")
        type_column.addWidget(type_hint)

        self.upload = UploadPad()
        upload_tab = QWidget()
        QVBoxLayout(upload_tab).addWidget(self.upload)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(draw_tab, "Draw")
        self.tabs.addTab(type_tab, "Type")
        self.tabs.addTab(upload_tab, "Upload")

        self.remember_box = QCheckBox(f"Remember this {noun}")
        self.remember_box.setChecked(True)
        self.remember_box.setToolTip(
            "Keep it for next time (up to 5), stored only on this computer"
        )
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.use_button = QPushButton(f"Use {noun}")
        self.use_button.setProperty("primary", True)
        self.use_button.setDefault(True)
        self.use_button.clicked.connect(self._accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.remember_box)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.use_button)
        column = QVBoxLayout(self)
        column.setContentsMargins(SPACING * 2, SPACING * 2, SPACING * 2, SPACING * 2)
        column.addWidget(self.tabs, 1)
        column.addLayout(buttons)

        for signal in (
            self.draw.changed,
            self.upload.changed,
            self.type.name.textChanged,
            self.tabs.currentChanged,
        ):
            signal.connect(lambda *_: self._update_use())
        self.set_tokens(tokens)
        self._update_use()

    @property
    def remember(self) -> bool:
        return self.remember_box.isChecked()

    def set_tokens(self, t: Tokens) -> None:
        self.undo_button.setIcon(icons.icon("undo-2", t.text, 16))
        self.clear_button.setIcon(icons.icon("eraser", t.text, 16))
        self.upload.set_tokens(t)

    def _set_ink(self, key: str) -> None:
        color = QColor(*sigimage.INK_COLORS[key])
        self.draw.set_ink(color)
        self.type.ink = color
        self.type.refresh()

    def current_png(self) -> bytes | None:
        tab = self.tabs.currentIndex()
        if tab == 0:
            return None if self.draw.is_empty else self.draw.to_png()
        if tab == 1:
            return self.type.png()
        return self.upload.png

    def _update_use(self) -> None:
        tab = self.tabs.currentIndex()
        ready = (
            (tab == 0 and not self.draw.is_empty)
            or (tab == 1 and bool(self.type.name.text().strip()))
            or (tab == 2 and self.upload.png is not None)
        )
        self.use_button.setEnabled(ready)

    def _accept(self) -> None:
        self.result_png = self.current_png()
        if self.result_png:
            self.accept()


def ask_signature(
    kind: SignatureKind, tokens: Tokens, parent: QWidget | None
) -> tuple[bytes, bool] | None:
    """Show the dialog; the PNG and whether to remember it, or None if cancelled."""
    dialog = SignatureDialog(kind, tokens, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_png:
        return dialog.result_png, dialog.remember
    return None
