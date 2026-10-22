"""Settings: theme (live), default zoom, default ink, signature folder, links.

Every change applies and saves immediately; there's no OK/Apply step.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdr_sign.services import settings as settings_service
from pdr_sign.services.settings import Settings
from pdr_sign.services.signatures import default_dir
from pdr_sign.services.stamps import TEXT_COLORS
from pdr_sign.ui.theme import SPACING


def segmented(
    options: list[tuple[str, str]], current: str, on_pick: Callable[[str], None], parent: QWidget
) -> tuple[QHBoxLayout, dict[str, QToolButton]]:
    row = QHBoxLayout()
    row.setSpacing(SPACING // 2)
    group = QButtonGroup(parent)
    buttons: dict[str, QToolButton] = {}
    for key, label in options:
        button = QToolButton()
        button.setObjectName("Segment")
        button.setText(label)
        button.setCheckable(True)
        button.setChecked(key == current)
        button.setAccessibleName(label)
        button.clicked.connect(lambda _=False, k=key: on_pick(k))
        group.addButton(button)
        row.addWidget(button)
        buttons[key] = button
    row.addStretch()
    return row, buttons


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        on_change: Callable[[Settings, str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.settings = settings
        self.on_change = on_change

        theme_row, self.theme_buttons = segmented(
            [("system", "System"), ("light", "Light"), ("dark", "Dark")],
            settings.theme,
            lambda v: self._set("theme", v),
            self,
        )
        zoom_row, self.zoom_buttons = segmented(
            [("fit-width", "Fit width"), ("fit-page", "Fit page"), ("100", "100 %")],
            settings.default_zoom,
            lambda v: self._set("default_zoom", v),
            self,
        )
        current_ink = next(
            (k for k, v in TEXT_COLORS.items() if v == settings.default_text_color), "black"
        )
        ink_row, self.ink_buttons = segmented(
            [("black", "Black"), ("blue", "Blue")],
            current_ink,
            lambda k: self._set("default_text_color", TEXT_COLORS[k]),
            self,
        )

        self.folder_label = QLabel()
        self.folder_label.setObjectName("Muted")
        self.folder_label.setWordWrap(True)
        choose = QToolButton()
        choose.setText("Choose…")
        choose.clicked.connect(self._choose_folder)
        reset = QToolButton()
        reset.setText("Default")
        reset.setToolTip(str(default_dir()))
        reset.clicked.connect(lambda: self._set("signature_dir", None))
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(choose)
        folder_row.addWidget(reset)

        self.links = QCheckBox("Open web and email links without asking")
        self.links.setChecked(settings.open_links_without_asking)
        self.links.toggled.connect(lambda on: self._set("open_links_without_asking", on))

        form = QFormLayout()
        form.setSpacing(SPACING * 2)
        form.addRow("Appearance", theme_row)
        form.addRow("Default zoom", zoom_row)
        form.addRow("Default ink", ink_row)
        form.addRow("Signatures and stamps", folder_row)
        form.addRow("", self.links)
        note = QLabel("Changes apply straight away.")
        note.setObjectName("Muted")
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        column = QVBoxLayout(self)
        column.setContentsMargins(SPACING * 3, SPACING * 3, SPACING * 3, SPACING * 2)
        column.addLayout(form)
        column.addWidget(note)
        column.addWidget(close)
        self._show_folder()

    def _show_folder(self) -> None:
        folder = self.settings.signature_dir or str(default_dir())
        self.folder_label.setText(folder)
        self.folder_label.setToolTip(folder)

    def _choose_folder(self) -> None:
        start = self.settings.signature_dir or str(default_dir())
        folder = QFileDialog.getExistingDirectory(self, "Folder for signatures and stamps", start)
        if folder:
            self._set("signature_dir", str(Path(folder)))

    def _set(self, key: str, value: object) -> None:
        setattr(self.settings, key, value)
        settings_service.save(self.settings)
        self._show_folder()
        self.on_change(self.settings, key)
