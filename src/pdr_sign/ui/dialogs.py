"""Small dialogs: password prompt, external-link confirmation, About."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from pdr_sign import APP_NAME, LICENSE_SPDX, SOURCE_URL, TAGLINE, __version__
from pdr_sign.resources import APP_ICON
from pdr_sign.ui.theme import SPACING

THIRD_PARTY = (
    "Qt for Python (PySide6) — LGPL-3.0",
    "PyMuPDF and MuPDF — AGPL-3.0",
    "Pillow — MIT-CMU",
    "Inter, Caveat, Dancing Script — SIL Open Font License 1.1",
    "Lucide icons — ISC",
)


def ask_password(parent: QWidget | None, filename: str, retry: bool) -> str | None:
    """Prompt for a document password. None when the user cancels."""
    prompt = f"“{filename}” is password protected."
    if retry:
        prompt = f"That password didn't work.\n{prompt}"
    text, ok = QInputDialog.getText(
        parent, "Password required", f"{prompt}\n\nPassword:", QLineEdit.EchoMode.Password
    )
    return text if ok else None


def confirm_external_link(parent: QWidget | None, uri: str) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle("Open link?")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("This document links to an outside address.")
    box.setInformativeText(uri)
    box.setStandardButtons(QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    return box.exec() == QMessageBox.StandardButton.Open


def show_error(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.warning(parent, title, message)


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About PDR")
        self.setMinimumWidth(380)

        logo = QLabel()
        dpr = self.devicePixelRatioF()
        pixmap = QPixmap(str(APP_ICON)).scaled(
            round(72 * dpr),
            round(72 * dpr),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(dpr)
        logo.setPixmap(pixmap)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name = QLabel(APP_NAME)
        name.setObjectName("DropZoneTitle")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        meta = QLabel(f"Version {__version__}<br>{TAGLINE}")
        meta.setObjectName("Muted")
        meta.setAlignment(Qt.AlignmentFlag.AlignCenter)

        licence = QLabel(
            f"Free software under the GNU Affero General Public License "
            f"({LICENSE_SPDX}). You can get, change and share the source code.<br><br>"
            f'<a href="{SOURCE_URL}">Source code</a> · '
            f'<a href="https://www.gnu.org/licenses/agpl-3.0.html">Licence</a>'
        )
        licence.setWordWrap(True)
        licence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        licence.setOpenExternalLinks(True)
        licence.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        credits_ = QLabel("<b>Third-party components</b><br>" + "<br>".join(THIRD_PARTY))
        credits_.setObjectName("Muted")
        credits_.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credits_.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING * 3, SPACING * 3, SPACING * 3, SPACING * 2)
        layout.setSpacing(SPACING * 2)
        for widget in (logo, name, meta, licence, credits_):
            layout.addWidget(widget)
        layout.addWidget(buttons)
