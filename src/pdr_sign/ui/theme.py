"""Design tokens, light/dark detection, and QSS/palette generation."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

Scheme = Literal["light", "dark"]

RADIUS = 8
SPACING = 8  # base grid unit; use multiples of 4
FONT_FAMILY = "Inter"
FONT_SIZE_PX = 13
HEADER_HEIGHT = 48
SIDEBAR_WIDTH = 220
PANEL_WIDTH = 280
PAGE_GAP = 16
ANIMATION_MS = 150


@dataclass(frozen=True)
class Tokens:
    scheme: Scheme
    window: str
    surface: str
    canvas: str
    text: str
    muted: str
    border: str
    accent: str
    on_accent: str
    # Derived helpers for hover/pressed states. These are neutral, not accent.
    hover: str
    pressed: str


LIGHT = Tokens(
    scheme="light",
    window="#FAFAFA",
    surface="#FFFFFF",
    canvas="#EDEDED",
    text="#1F1F1F",
    muted="#6B6B6B",
    border="#E3E3E3",
    accent="#4F46E5",
    on_accent="#FFFFFF",
    hover="#F0F0F0",
    pressed="#E6E6E6",
)

DARK = Tokens(
    scheme="dark",
    window="#1E1E1E",
    surface="#262626",
    canvas="#141414",
    text="#EDEDED",
    muted="#A0A0A0",
    border="#333333",
    accent="#818CF8",
    on_accent="#1E1E1E",
    hover="#2E2E2E",
    pressed="#383838",
)


def tokens_for(scheme: Scheme) -> Tokens:
    return DARK if scheme == "dark" else LIGHT


# --- contrast -----------------------------------------------------------------


def _channel(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


# --- detection ------------------------------------------------------------------


def gnome_color_scheme() -> Scheme | None:
    """Read ``org.gnome.desktop.interface color-scheme``. None when unavailable."""
    exe = shutil.which("gsettings")
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True,
            text=True,
            timeout=1,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.strip().strip("'\"")
    if value == "prefer-dark":
        return "dark"
    if value in ("prefer-light", "default"):
        return "light"
    return None


def qt_color_scheme() -> Scheme:
    """Fallback: ask Qt (portal-backed on GNOME), then guess from the palette."""
    hints = QGuiApplication.styleHints()
    scheme = hints.colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return "dark"
    if scheme == Qt.ColorScheme.Light:
        return "light"
    window = QGuiApplication.palette().color(QPalette.ColorRole.Window)
    return "dark" if window.lightness() < 128 else "light"


def resolve_scheme(override: str) -> Scheme:
    """``override`` is the Settings value: "system", "light" or "dark"."""
    if override == "light":
        return "light"
    if override == "dark":
        return "dark"
    return gnome_color_scheme() or qt_color_scheme()


# --- generation -----------------------------------------------------------------


def build_palette(t: Tokens) -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    pairs = {
        role.Window: t.window,
        role.WindowText: t.text,
        role.Base: t.surface,
        role.AlternateBase: t.window,
        role.Text: t.text,
        role.Button: t.surface,
        role.ButtonText: t.text,
        role.ToolTipBase: t.surface,
        role.ToolTipText: t.text,
        role.PlaceholderText: t.muted,
        role.Highlight: t.accent,
        role.HighlightedText: t.on_accent,
        role.Link: t.accent,
        role.Mid: t.border,
    }
    for r, color in pairs.items():
        p.setColor(r, QColor(color))
    disabled = QPalette.ColorGroup.Disabled
    for r in (role.WindowText, role.Text, role.ButtonText):
        p.setColor(disabled, r, QColor(t.muted))
    return p


def build_qss(t: Tokens) -> str:
    r = RADIUS
    return f"""
* {{
    font-family: "{FONT_FAMILY}";
    font-size: {FONT_SIZE_PX}px;
    color: {t.text};
}}
QMainWindow, QDialog {{ background: {t.window}; }}
QToolTip {{
    background: {t.surface}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 4px; padding: 4px 8px;
}}

#HeaderBar {{
    background: {t.window};
    border-bottom: 1px solid {t.border};
}}
#HeaderTitle {{ font-weight: 600; }}

QToolButton, QPushButton {{
    background: transparent; border: 1px solid transparent;
    border-radius: {r}px; padding: 6px 8px;
}}
QToolButton:hover, QPushButton:hover {{ background: {t.hover}; }}
QToolButton:pressed, QPushButton:pressed {{ background: {t.pressed}; }}
QToolButton:focus, QPushButton:focus {{ border: 1px solid {t.accent}; }}
QToolButton:checked {{ background: {t.pressed}; }}

QPushButton[primary="true"], QToolButton[primary="true"] {{
    background: {t.accent}; color: {t.on_accent};
    border-radius: 16px; padding: 6px 14px; font-weight: 600;
}}
QPushButton[primary="true"]:focus, QToolButton[primary="true"]:focus {{
    border: 2px solid {t.text};
}}

QLineEdit, QComboBox, QSpinBox {{
    background: {t.surface}; border: 1px solid {t.border};
    border-radius: {r}px; padding: 4px 8px;
    selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {t.accent}; }}

QMenu {{
    background: {t.surface}; border: 1px solid {t.border};
    border-radius: {r}px; padding: 4px;
}}
QMenu::item {{ padding: 6px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t.hover}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 8px; }}

#Canvas {{ background: {t.canvas}; }}
#EmptyState {{ background: {t.canvas}; }}
#DropZone {{
    background: {t.surface};
    border: 2px dashed {t.border}; border-radius: {r * 2}px;
}}
#DropZone[dragActive="true"] {{ border-color: {t.accent}; }}
#DropZoneTitle {{ font-size: 17px; font-weight: 600; }}
#Muted {{ color: {t.muted}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t.border}; border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:hover {{ background: {t.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
