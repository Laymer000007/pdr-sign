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


# The icon's medium blue. Filled accent surfaces use it in both themes, with white on top.
ACCENT = "#0000CD"


def mix(a: str, b: str, amount: float) -> str:
    """``a`` moved ``amount`` (0..1) of the way towards ``b``."""
    ca, cb = QColor(a), QColor(b)
    channels = (
        round(x + (y - x) * amount)
        for x, y in ((ca.red(), cb.red()), (ca.green(), cb.green()), (ca.blue(), cb.blue()))
    )
    return "#{:02X}{:02X}{:02X}".format(*channels)


@dataclass(frozen=True)
class Tokens:
    scheme: Scheme
    window: str
    surface: str
    canvas: str
    text: str
    muted: str
    border: str
    # Accent *text and outlines* on this theme's surfaces (links, focus rings, tab
    # underline, accent text): 4.5:1 against window, surface, canvas, hover, pressed.
    accent_fg: str
    # Derived helpers for hover/pressed states. These are neutral, not accent.
    hover: str
    pressed: str
    # Filled accent (primary buttons, active tools, Fill & Sign toggle, selection), the
    # same in both themes. Also used for marks drawn on pages and paper, which are light
    # in both themes.
    accent: str = ACCENT
    accent_hover: str = "#0000A8"
    accent_pressed: str = "#00008B"
    on_accent: str = "#FFFFFF"
    # Search highlights are drawn on (white) pages, so both themes share them. Amber
    # rather than accent: the accent is reserved for selection and focus.
    search_hit: str = "#FCD34D"
    search_current: str = "#F59E0B"
    # Fillable form fields: a soft cool tint so they read as "type here", opaque enough
    # to cover the PDF's own (possibly stale) field appearance underneath.
    field_fill: str = mix(ACCENT, "#FFFFFF", 0.91)
    field_border: str = mix(ACCENT, "#FFFFFF", 0.6)
    # Paper: where black/blue ink is shown outside a page (draw pad, upload preview,
    # saved signature tiles). Light in both themes so dark ink stays readable.
    paper: str = "#FFFFFF"
    paper_border: str = "#E3E3E3"
    paper_muted: str = "#6B6B6B"


LIGHT = Tokens(
    scheme="light",
    window="#FAFAFA",
    surface="#FFFFFF",
    canvas="#EDEDED",
    text="#1F1F1F",
    muted="#6B6B6B",
    border="#E3E3E3",
    accent_fg=ACCENT,
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
    accent_fg="#9696FF",  # lightest-needed blue of the same hue for 4.5:1 on pressed
    hover="#2E2E2E",
    pressed="#383838",
)


def disabled_color(t: Tokens) -> str:
    """Icon colour for disabled controls: clearly dimmer than ``text`` in both themes."""
    return mix(t.text, t.window, 0.6)


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


def gsettings_get(schema: str, key: str) -> str | None:
    """Read one GNOME setting, unquoted. None when gsettings is unavailable."""
    exe = shutil.which("gsettings")
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, "get", schema, key], capture_output=True, text=True, timeout=1, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return out.strip().strip("'\"")


def gnome_color_scheme() -> Scheme | None:
    """Read ``org.gnome.desktop.interface color-scheme``. None when unavailable."""
    value = gsettings_get("org.gnome.desktop.interface", "color-scheme")
    if value == "prefer-dark":
        return "dark"
    if value in ("prefer-light", "default"):
        return "light"
    return None


_animations: bool | None = None


def animations_enabled() -> bool:
    """False when the desktop asks for reduced motion. Read once, then cached."""
    global _animations
    if _animations is None:
        value = gsettings_get("org.gnome.desktop.interface", "enable-animations")
        _animations = value != "false"
    return _animations


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
        role.Link: t.accent_fg,
        role.Mid: t.border,
    }
    for r, color in pairs.items():
        p.setColor(r, QColor(color))
    disabled = QPalette.ColorGroup.Disabled
    for r in (role.WindowText, role.Text, role.ButtonText):
        p.setColor(disabled, r, QColor(t.muted))
    return p


def build_qss(t: Tokens) -> str:
    from pdr_sign.ui.icons import svg_file

    r = RADIUS
    arrow = svg_file("chevron-down", t.muted)
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
QToolButton:focus, QPushButton:focus {{ border: 1px solid {t.accent_fg}; }}
QToolButton:checked {{ background: {t.pressed}; }}

QPushButton[primary="true"], QToolButton[primary="true"] {{
    background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent};
    /* Qt drops a radius larger than half the height, so keep min-height in step. */
    border-radius: 14px; min-height: 18px; padding: 6px 16px; font-weight: 600;
}}
QPushButton[primary="true"]:hover, QToolButton[primary="true"]:hover {{
    background: {t.accent_hover}; border-color: {t.accent_hover};
}}
QPushButton[primary="true"]:pressed, QToolButton[primary="true"]:pressed {{
    background: {t.accent_pressed}; border-color: {t.accent_pressed};
}}
QPushButton[primary="true"]:focus, QToolButton[primary="true"]:focus {{
    border: 2px solid {t.text};
}}

QLineEdit, QComboBox, QSpinBox {{
    background: {t.surface}; border: 1px solid {t.border};
    border-radius: {r}px; padding: 4px 8px;
    selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {t.accent_fg}; }}
QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 8px;
    border: 1px solid {t.muted}; background: {t.surface};
}}
QRadioButton::indicator:checked {{
    /* same 16 px outer size as unchecked: 6 + 2 * 5 */
    width: 6px; height: 6px; border: 5px solid {t.accent}; background: {t.on_accent};
}}
QRadioButton::indicator:focus {{ border-color: {t.accent_fg}; }}
QDialog QComboBox {{ padding-right: 28px; min-height: 20px; }}
QDialog QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 24px; border: none;
}}
QDialog QComboBox::down-arrow {{ image: url({arrow}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{
    background: {t.surface}; border: 1px solid {t.border}; outline: none;
    selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}

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
#DropZone[dragActive="true"] {{ border-color: {t.accent_fg}; }}
#DropZoneTitle {{ font-size: 17px; font-weight: 600; }}
#Muted {{ color: {t.muted}; }}

QToolButton::menu-indicator {{ image: none; width: 0; }}
#PageField {{ padding: 4px 4px; }}

#Sidebar {{ background: {t.window}; }}
#Divider {{ background: {t.border}; }}
QTabWidget::pane {{ border: none; }}
QTabBar {{ background: {t.window}; }}
QTabBar::tab {{
    background: transparent; color: {t.muted};
    padding: 8px 12px; border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent_fg}; }}
QTabBar::tab:hover {{ color: {t.text}; }}
#SidebarTabs QTabBar::tab {{ padding: 8px 6px; }}
#DocumentTabs {{ border-bottom: 1px solid {t.border}; }}
#DocumentTabs::tab {{ max-width: 220px; padding: 6px 8px 6px 12px; }}
#TabClose {{ padding: 2px; border-radius: 4px; }}

#Thumbnails, QTreeWidget {{ background: {t.window}; border: none; outline: none; }}
#Thumbnails::item {{
    color: {t.muted}; border: 2px solid transparent; border-radius: {r}px; padding: 4px;
}}
#Thumbnails::item:selected {{
    color: {t.text}; border-color: {t.accent_fg}; background: transparent;
}}
#Thumbnails::item:hover {{ background: {t.hover}; }}
QTreeWidget::item {{ padding: 4px 2px; border-radius: 4px; }}
QTreeWidget::item:selected {{ background: {t.hover}; color: {t.text}; }}

#SearchBar {{ background: {t.window}; border-bottom: 1px solid {t.border}; }}
#SearchResults {{ background: {t.window}; border: none; outline: none; }}
#SearchResults::item {{ padding: 6px 8px; border-radius: 4px; }}
#SearchResults::item:selected {{ background: {t.hover}; color: {t.text}; }}

#FillToggle:checked {{ background: {t.accent}; border-color: {t.accent}; }}
#FillToggle:checked:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
#FillToggle:checked:pressed {{ background: {t.accent_pressed}; border-color: {t.accent_pressed}; }}
#FillSignPanel, #FillSignContent, #FillSignScroll {{ background: {t.window}; }}
#PanelTitle {{ font-size: 15px; font-weight: 600; }}
#ToolButton {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: {r}px;
    padding: 4px 2px; color: {t.text};
}}
#SavedSignature {{
    background: {t.paper}; border: 1px solid {t.paper_border}; border-radius: {r}px;
    padding: 4px;
}}
#SavedSignature:hover {{ border-color: {t.accent}; }}
#SavedAdd {{ border: 1px dashed {t.border}; border-radius: {r}px; }}
#ToolButton:hover {{ background: {t.hover}; }}
#ToolButton:checked {{ background: {t.accent}; border-color: {t.accent}; color: {t.on_accent}; }}
#ToolButton:checked:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
#ToolButton:checked:pressed {{ background: {t.accent_pressed}; border-color: {t.accent_pressed}; }}
#Stepper {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {r}px; }}
#Stepper QToolButton {{ padding: 4px; border-radius: 6px; }}
#Swatch {{ border: 2px solid {t.border}; border-radius: 12px; }}
#Swatch:checked {{ border: 2px solid {t.accent_fg}; }}
#FieldList {{ background: {t.window}; border: none; outline: none; }}
#FieldList::item {{ padding: 4px 4px; border-radius: 4px; }}
#FieldList::item:selected {{ background: {t.hover}; color: {t.text}; }}

#ActionToast {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: {r}px;
}}
#ToastAction {{ color: {t.accent_fg}; font-weight: 600; }}
#Banner {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}

#ZoomIndicator {{
    background: {t.surface}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 14px; padding: 4px 12px;
}}
#EmptyStateBody {{ background: {t.canvas}; }}
#SectionTitle {{ color: {t.muted}; font-weight: 600; }}
#RecentCard {{ padding: 8px; color: {t.text}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t.border}; border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:hover {{ background: {t.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
