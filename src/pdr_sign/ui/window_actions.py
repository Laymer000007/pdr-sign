"""Window-level actions kept out of main_window.py: settings, links, printing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QToolButton

from pdr_sign.services.settings import Settings
from pdr_sign.services.signatures import SignatureStore
from pdr_sign.ui import dialogs, icons, printing
from pdr_sign.ui.settings_dialog import SettingsDialog

if TYPE_CHECKING:
    from pdr_sign.ui.document_tab import DocumentTab
    from pdr_sign.ui.main_window import MainWindow

SAFE_LINK_SCHEMES = {"http", "https", "mailto"}


def open_settings(window: MainWindow) -> None:
    SettingsDialog(window.settings, lambda s, key: apply_setting(window, s, key), window).exec()


def apply_setting(window: MainWindow, settings: Settings, key: str) -> None:
    """A setting changed in the dialog (already saved): make it take effect now."""
    if key == "theme" and window.theme_controller is not None:
        window.theme_controller.set_override(settings.theme)
    elif key == "default_text_color":
        for tab in window.tabs:
            tab.set_default_ink(settings.default_text_color)
    elif key == "signature_dir":
        window.signatures.set_store(SignatureStore(settings.signature_dir))


def open_external_link(window: MainWindow, uri: str) -> None:
    url = QUrl(uri)
    if url.scheme().lower() not in SAFE_LINK_SCHEMES:
        message = f"PDR only opens web and email links.\n\n{uri}"
        dialogs.show_error(window, "Link not opened", message)
        return
    if window.settings.open_links_without_asking or dialogs.confirm_external_link(window, uri):
        QDesktopServices.openUrl(url)


def print_current(window: MainWindow) -> None:
    tab = window.current_tab()
    if tab is None:
        return
    if window._printer is None:  # kept so printer choices persist
        window._printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printing.run_print_dialog(window, window._printer, tab.doc, tab.view.current_page)


def close_button(window: MainWindow, tab: DocumentTab) -> QToolButton:
    button = QToolButton()
    button.setObjectName("TabClose")
    button.setAutoRaise(True)
    button.setAccessibleName(f"Close {tab.doc.path.name}")
    button.setToolTip("Close (Ctrl+W)")
    button.setIcon(icons.icon("x", window.tokens.muted, 14))
    button.clicked.connect(lambda: window.close_tab(tab))
    return button
