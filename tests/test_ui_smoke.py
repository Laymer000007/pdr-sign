from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign import APP_NAME
from pdr_sign.app import build_window, configure, load_fonts
from pdr_sign.resources import ICONS_DIR
from pdr_sign.services.settings import Settings
from pdr_sign.ui import icons, theme


def test_bundled_fonts_load(qapp: QApplication) -> None:
    families = load_fonts()
    for family in ("Inter", "Caveat", "Dancing Script"):
        assert any(f.startswith(family) for f in families), families


def test_every_icon_renders(qapp: QApplication) -> None:
    for path in ICONS_DIR.glob("*.svg"):
        assert b"currentColor" not in icons.svg_data(path.stem, "#123456")
        assert not icons.pixmap(path.stem, "#123456", 18, 2.0).toImage().isNull()


def test_window_opens_with_empty_state(qtbot: QtBot, qapp: QApplication) -> None:
    controller = configure(qapp, Settings(theme="light"))
    window = build_window(controller)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    assert window.windowTitle() == APP_NAME
    assert window.header.height() == theme.HEADER_HEIGHT
    assert window.empty_state.isVisible()


def test_theme_switch_updates_palette(qtbot: QtBot, qapp: QApplication) -> None:
    controller = configure(qapp, Settings(theme="light"))
    window = build_window(controller)
    qtbot.addWidget(window)
    role = QPalette.ColorRole.Window
    assert qapp.palette().color(role).name().upper() == theme.LIGHT.window
    controller.set_override("dark")
    assert qapp.palette().color(role).name().upper() == theme.DARK.window
    assert window.tokens == theme.DARK
