"""QApplication setup: fonts, theme, main window."""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from pdr_sign import APP_ID, APP_NAME, APP_SHORT_NAME, __version__
from pdr_sign.resources import APP_ICON, FONTS_DIR, SIGNATURE_FONT_FILES, UI_FONT_FILES
from pdr_sign.services import settings as settings_service
from pdr_sign.services.recent import RecentFiles
from pdr_sign.ui import theme
from pdr_sign.ui.main_window import MainWindow
from pdr_sign.ui.single_instance import InstanceServer


@cache
def load_fonts() -> tuple[str, ...]:
    """Register bundled fonts once. Returns the family names that loaded."""
    families: list[str] = []
    for name in (*UI_FONT_FILES, *SIGNATURE_FONT_FILES):
        font_id = QFontDatabase.addApplicationFont(str(FONTS_DIR / name))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return tuple(families)


class ThemeController:
    """Applies tokens to the app and follows live system light/dark switches."""

    def __init__(self, app: QApplication, override: str) -> None:
        self.app = app
        self.override = override
        self.window: MainWindow | None = None
        self.tokens = theme.tokens_for(theme.resolve_scheme(override))
        self._apply()
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_change)

    def set_override(self, override: str) -> None:
        self.override = override
        self.refresh()

    def refresh(self) -> None:
        tokens = theme.tokens_for(theme.resolve_scheme(self.override))
        if tokens != self.tokens:
            self.tokens = tokens
            self._apply()

    def _on_system_change(self, *_: object) -> None:
        if self.override == "system":
            self.refresh()

    def _apply(self) -> None:
        self.app.setPalette(theme.build_palette(self.tokens))
        self.app.setStyleSheet(theme.build_qss(self.tokens))
        if self.window is not None:
            self.window.set_tokens(self.tokens)


def configure(app: QApplication, user_settings: settings_service.Settings) -> ThemeController:
    """Apply identity, style, fonts and theme to an existing QApplication."""
    app.setApplicationName(APP_SHORT_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(APP_ICON)))

    load_fonts()
    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(theme.FONT_SIZE_PX)
    app.setFont(font)
    return ThemeController(app, user_settings.theme)


def build_window(
    controller: ThemeController,
    user_settings: settings_service.Settings | None = None,
    recent: RecentFiles | None = None,
) -> MainWindow:
    window = MainWindow(controller.tokens, user_settings, recent)
    controller.window = window
    return window


def run(argv: Sequence[str], files: list[str]) -> int:
    QGuiApplication.setDesktopFileName(APP_ID)
    app = QApplication(list(argv))
    user_settings = settings_service.load()
    controller = configure(app, user_settings)
    window = build_window(controller, user_settings)

    server = InstanceServer(parent=app)
    server.files_received.connect(window.open_paths)
    server.start()
    app.aboutToQuit.connect(server.stop)

    window.show()
    if files:
        window.open_paths(files)
    return app.exec()
