"""Welcome & support: shown once on first launch, and from the header's coffee button.

Non-modal and never shown again automatically: it must never get in the way.
"""

from __future__ import annotations

import io

import segno
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign import APP_NAME
from pdr_sign.resources import APP_ICON
from pdr_sign.services.support import (
    FEEDBACK_EMAIL,
    ISSUES_URL,
    MILESTONES,
    ZCASH_ADDRESS,
    mailto_url,
    zcash_uri,
)
from pdr_sign.ui import desktop
from pdr_sign.ui.action_toast import ActionToast
from pdr_sign.ui.theme import SPACING

TITLE = f"Welcome to {APP_NAME}"
INTRO = (
    f"Thank you for trying {APP_NAME}, a fast, private PDF reader with Fill & Sign for "
    "Ubuntu. Your documents never leave your computer."
)
FREE = (
    f"{APP_NAME} is free and open source, and always will be. No ads, no subscriptions, "
    "no paywalled features."
)
ASK = (
    f"If {APP_NAME} saves you time, please consider buying me a coffee. Your support "
    "funds what's next:"
)
COFFEE = "Buy me a coffee with Zcash (ZEC)"
QR_PX = 152
WIDTH = 620  # fits the address in one line next to the QR code


def qr_pixmap(data: str, size: int, dpr: float) -> QPixmap:
    """Black modules on a white tile (both themes), crisp at the screen's scale."""
    code = segno.make(data, error="m")
    modules = code.symbol_size(border=4)[0]
    scale = max(1, round(size * dpr / modules))
    buffer = io.BytesIO()
    code.save(buffer, kind="png", scale=scale, border=4, dark="#000000", light="#ffffff")
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    # The screen's own ratio, so nothing rescales (and blurs) the modules; the logical
    # size is then within one module of ``size``.
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _text(html: str, muted: bool = False) -> QLabel:
    label = QLabel(html)
    label.setWordWrap(True)
    if muted:
        label.setObjectName("Muted")
    return label


class WelcomeDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.setModal(False)
        self.setFixedWidth(WIDTH)
        dpr = self.devicePixelRatioF()

        logo = QLabel()
        icon = QPixmap(str(APP_ICON)).scaled(
            round(64 * dpr),
            round(64 * dpr),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        icon.setDevicePixelRatio(dpr)
        logo.setPixmap(icon)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(TITLE)
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        milestones = _text("<br>".join(f"•&nbsp; {m}" for m in MILESTONES))
        milestones.setContentsMargins(SPACING * 2, 0, 0, 0)

        # Zcash: QR on a white tile, the address to copy
        self.qr = QLabel()
        self.qr.setObjectName("QrTile")
        self.qr.setPixmap(qr_pixmap(zcash_uri(), QR_PX, dpr))
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side = round(self.qr.pixmap().width() / dpr) + SPACING * 2
        self.qr.setFixedSize(side, side)
        self.qr.setAccessibleName(f"QR code for the Zcash address {ZCASH_ADDRESS}")
        self.address = QLineEdit(ZCASH_ADDRESS)
        self.address.setObjectName("Mono")
        self.address.setReadOnly(True)
        self.address.setAccessibleName("Zcash address")
        self.address.setCursorPosition(0)
        self.copy_address = QPushButton("Copy address")
        self.copy_address.clicked.connect(self._copy_address)
        coffee_col = QVBoxLayout()
        coffee_col.setSpacing(SPACING)
        heading = QLabel(f"<b>{COFFEE}</b>")
        heading.setWordWrap(True)
        coffee_col.addWidget(heading)
        coffee_col.addWidget(self.address)
        copy_row = QHBoxLayout()
        copy_row.addWidget(self.copy_address)
        copy_row.addStretch()
        coffee_col.addLayout(copy_row)
        coffee_col.addStretch()
        coffee = QHBoxLayout()
        coffee.setSpacing(SPACING * 2)
        coffee.addWidget(self.qr)
        coffee.addLayout(coffee_col, 1)

        rule = QFrame()
        rule.setObjectName("Divider")
        rule.setFixedHeight(1)

        self.feedback = _text(
            f'Ideas or feedback? I\'d love to hear from you: <a href="{mailto_url()}">'
            f"{FEEDBACK_EMAIL}</a>"
        )
        self.issues = _text(f'<a href="{ISSUES_URL}">Report a problem</a>')
        for label in (self.feedback, self.issues):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            label.linkActivated.connect(self.open_link)

        self.start = QPushButton(f"Start using {APP_NAME}")
        self.start.setProperty("primary", True)
        self.start.setDefault(True)
        self.start.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.start)

        column = QVBoxLayout(self)
        column.setContentsMargins(SPACING * 4, SPACING * 4, SPACING * 4, SPACING * 3)
        column.setSpacing(SPACING * 2)
        column.addWidget(logo)
        column.addWidget(title)
        column.addWidget(_text(INTRO))
        column.addWidget(_text(FREE))
        column.addWidget(_text(ASK))
        column.addWidget(milestones)
        column.addLayout(coffee)
        column.addWidget(rule)
        column.addWidget(self.feedback)
        column.addWidget(self.issues)
        column.addLayout(buttons)

        self.toast = ActionToast(self)
        # Word-wrapped labels make Qt underestimate a top-level's height; with the width
        # fixed, take the height the layout needs for it.
        self.setFixedHeight(column.totalHeightForWidth(WIDTH))
        self.start.setFocus()

    def _copy_address(self) -> None:
        from pdr_sign.ui.canvas import clipboard

        clipboard().setText(ZCASH_ADDRESS)
        self.toast.show_actions("Address copied", [])

    def open_link(self, url: str) -> None:
        """Mail and web links go to the desktop (portal in the snap). With no mail app,
        copy the address instead and say so."""
        if desktop.open_url(url):
            return
        if url.startswith("mailto:"):
            from pdr_sign.ui.canvas import clipboard

            clipboard().setText(FEEDBACK_EMAIL)
            self.toast.show_actions("No mail app found, so the address was copied", [])
        else:
            self.toast.show_actions(f"Couldn't open {url}", [])
