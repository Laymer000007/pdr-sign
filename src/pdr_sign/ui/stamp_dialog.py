"""Add a company stamp: upload a scan or photo, set its real size, keep it for later."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services import sigimage
from pdr_sign.services.stamps import STAMP_DEFAULT_MM
from pdr_sign.ui.stepper import Stepper
from pdr_sign.ui.theme import SPACING, Tokens
from pdr_sign.ui.upload_pad import STAMP_HINT, STAMP_INKS, STAMP_OPTIONS, UploadPad

MIN_MM, MAX_MM = 10, 200


class StampDialog(QDialog):
    """``exec()`` then read ``result_png`` (with its real width inside) and ``remember``."""

    def __init__(self, tokens: Tokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add stamp")
        self.setMinimumSize(780, 560)
        self.result_png: bytes | None = None

        self.upload = UploadPad(inks=STAMP_INKS, base=STAMP_OPTIONS, hint=STAMP_HINT)
        self.width_box = Stepper(MIN_MM, MAX_MM, round(STAMP_DEFAULT_MM), " mm", "Stamp width")
        size_hint = QLabel("Width as printed on paper. Measure the real stamp for a true fit.")
        size_hint.setObjectName("Muted")
        self.warning = QLabel("")
        self.warning.setObjectName("Muted")
        self.warning.setWordWrap(True)
        self.warning.hide()

        self.remember_box = QCheckBox("Remember this stamp")
        self.remember_box.setChecked(True)
        self.remember_box.setToolTip(
            "Keep it for next time (up to 5), stored only on this computer"
        )
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.use_button = QPushButton("Use stamp")
        self.use_button.setProperty("primary", True)
        self.use_button.setDefault(True)
        self.use_button.clicked.connect(self._accept)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Actual size"))
        size_row.addWidget(self.width_box)
        size_row.addWidget(size_hint, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.remember_box)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.use_button)
        column = QVBoxLayout(self)
        column.setContentsMargins(SPACING * 2, SPACING * 2, SPACING * 2, SPACING * 2)
        column.addWidget(self.upload, 1)
        column.addLayout(size_row)
        column.addWidget(self.warning)
        column.addLayout(buttons)

        self.upload.changed.connect(self._update)
        self.upload.set_tokens(tokens)
        self.width_box.set_tokens(tokens)
        self._update()

    @property
    def remember(self) -> bool:
        return self.remember_box.isChecked()

    def _update(self) -> None:
        png = self.upload.png
        self.use_button.setEnabled(png is not None)
        if png is not None and sigimage.is_low_res(png):
            width = sigimage.load(png).width
            self.warning.setText(
                f"This image is only {width} px wide, so the stamp may print soft. "
                "A sharper photo or a 600 dpi scan helps."
            )
            self.warning.show()
        else:
            self.warning.hide()

    def current_png(self) -> bytes | None:
        png = self.upload.png
        return sigimage.with_width_mm(png, self.width_box.value()) if png else None

    def _accept(self) -> None:
        self.result_png = self.current_png()
        if self.result_png:
            self.accept()


def ask_stamp(tokens: Tokens, parent: QWidget | None) -> tuple[bytes, bool] | None:
    dialog = StampDialog(tokens, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_png:
        return dialog.result_png, dialog.remember
    return None
