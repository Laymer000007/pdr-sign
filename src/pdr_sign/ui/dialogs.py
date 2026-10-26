"""Small dialogs: password prompt, external-link confirmation, About."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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
        self.setWindowTitle(f"About {APP_NAME}")
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


def ask_save_path(parent: QWidget | None, title: str, suggested: Path) -> Path | None:
    """A Save As file dialog. Adds ``.pdf`` when the name has no extension."""
    name, _ = QFileDialog.getSaveFileName(parent, title, str(suggested), "PDF files (*.pdf)")
    if not name:
        return None
    path = Path(name)
    return path if path.suffix.lower() == ".pdf" else path.with_name(path.name + ".pdf")


def confirm_signed(parent: QWidget | None) -> str:
    """The document carries a digital signature: "save_as", "save" or "cancel"."""
    box = QMessageBox(parent)
    box.setWindowTitle("Signed document")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText("This document has a digital signature.")
    box.setInformativeText(
        "Saving changes into it will invalidate that signature. "
        "Save a copy instead to keep the signed original as it is."
    )
    save_as = box.addButton("Save As…", QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    anyway = box.addButton("Save anyway", QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(save_as)
    box.exec()
    clicked = box.clickedButton()
    return "save_as" if clicked is save_as else "save" if clicked is anyway else "cancel"


def ask_unsaved(parent: QWidget | None, name: str) -> str:
    """Closing with unsaved changes: "save", "discard" or "cancel"."""
    box = QMessageBox(parent)
    box.setWindowTitle("Unsaved changes")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(f"Save the changes to “{name}” before closing?")
    box.setInformativeText("If you don't save, your filled-in fields and signatures are lost.")
    box.setStandardButtons(
        QMessageBox.StandardButton.Save
        | QMessageBox.StandardButton.Discard
        | QMessageBox.StandardButton.Cancel
    )
    box.setDefaultButton(QMessageBox.StandardButton.Save)
    answer = box.exec()
    if answer == QMessageBox.StandardButton.Save:
        return "save"
    if answer == QMessageBox.StandardButton.Discard:
        return "discard"
    return "cancel"


SIGNED_COPY_TITLE = "Save signed copy?"
SIGNED_COPY_BODY = (
    "PDR Sign will create a new file: {name}\n\n"
    "Your original stays unchanged, so you can still make corrections and save another "
    "signed copy later.\n\n"
    "In the new copy, everything you filled in, signed and stamped is locked into the "
    "page. Fields, text, signatures and stamps can no longer be edited or removed in "
    "normal PDF readers.\n\n"
    "Please check the document carefully before continuing."
)
SIGNED_COPY_ACCEPT = "Save signed copy"


def signed_copy_box(parent: QWidget | None, new_name: str) -> QMessageBox:
    """The confirmation shown before writing a signed copy (Cancel is the default)."""
    box = QMessageBox(parent)
    box.setWindowTitle(SIGNED_COPY_TITLE)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(SIGNED_COPY_BODY.format(name=new_name))
    cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.addButton(SIGNED_COPY_ACCEPT, QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box


def confirm_signed_copy(parent: QWidget | None, new_name: str) -> bool:
    box = signed_copy_box(parent, new_name)
    box.exec()
    clicked = box.clickedButton()
    return clicked is not None and clicked.text() == SIGNED_COPY_ACCEPT
