"""Bundled data files (fonts, icons, app icon). Qt-free path helpers."""

from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent
FONTS_DIR = RESOURCES_DIR / "fonts"
ICONS_DIR = RESOURCES_DIR / "icons"
APP_ICON = RESOURCES_DIR / "pdr-sign.svg"

UI_FONT_FILES = ("Inter-Variable.ttf",)
SIGNATURE_FONT_FILES = ("Caveat-Variable.ttf", "DancingScript-Variable.ttf")
