import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from pdr_sign.ui import theme
from pdr_sign.ui.theme import DARK, LIGHT, Tokens, contrast_ratio

BOTH = pytest.mark.parametrize("t", [LIGHT, DARK], ids=["light", "dark"])


def test_spec_colours() -> None:
    assert (LIGHT.window, LIGHT.surface, LIGHT.canvas) == ("#FAFAFA", "#FFFFFF", "#EDEDED")
    assert (LIGHT.text, LIGHT.muted, LIGHT.border) == ("#1F1F1F", "#6B6B6B", "#E3E3E3")
    assert (DARK.window, DARK.surface, DARK.canvas) == ("#1E1E1E", "#262626", "#141414")
    assert (DARK.text, DARK.muted, DARK.border) == ("#EDEDED", "#A0A0A0", "#333333")


def test_accent_is_the_icon_blue() -> None:
    for t in (LIGHT, DARK):
        assert (t.accent, t.accent_hover, t.accent_pressed) == ("#0000CD", "#0000A8", "#00008B")
        assert t.on_accent == "#FFFFFF"
    assert LIGHT.accent_fg == "#0000CD"
    assert DARK.accent_fg == "#9696FF"


def _surfaces(t: Tokens) -> list[str]:
    return [t.window, t.surface, t.canvas, t.hover, t.pressed]


@BOTH
def test_white_reads_on_every_accent_fill(t: Tokens) -> None:
    for fill in (t.accent, t.accent_hover, t.accent_pressed):
        assert contrast_ratio(t.on_accent, fill) >= 4.5, fill


@BOTH
def test_accent_foreground_reads_on_every_surface(t: Tokens) -> None:
    for bg in _surfaces(t):
        assert contrast_ratio(t.accent_fg, bg) >= 4.5, (t.accent_fg, bg)


def test_dark_accent_foreground_is_the_closest_passing_shade() -> None:
    # Same hue as the icon blue; one step darker would fail on some dark surface.
    darker = "#9595FF"
    assert min(contrast_ratio(darker, bg) for bg in _surfaces(DARK)) < 4.5


@BOTH
def test_page_marks_read_on_paper(t: Tokens) -> None:
    # Selection outlines and field focus are drawn on white pages in both themes.
    assert contrast_ratio(t.accent, t.paper) >= 4.5


@BOTH
def test_text_contrast(t: Tokens) -> None:
    for fg, bg in [
        (t.text, t.window),
        (t.text, t.surface),
        (t.muted, t.window),
        (t.muted, t.surface),
    ]:
        assert contrast_ratio(fg, bg) >= 4.5, (fg, bg)


@BOTH
def test_accent_is_visible_as_focus_ring(t: Tokens) -> None:
    # WCAG non-text contrast: 3:1 against adjacent colours.
    assert contrast_ratio(t.accent_fg, t.window) >= 3
    assert contrast_ratio(t.accent_fg, t.surface) >= 3


@BOTH
def test_qss_uses_only_token_colours(t: Tokens) -> None:
    qss = theme.build_qss(t)
    allowed = {v.upper() for k, v in vars(t).items() if k != "scheme"}
    used = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", qss)}
    assert used <= allowed


def test_override_wins() -> None:
    assert theme.resolve_scheme("dark") == "dark"
    assert theme.resolve_scheme("light") == "light"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("'prefer-dark'\n", "dark"),
        ("'prefer-light'\n", "light"),
        ("'default'\n", "light"),
        ("'weird'\n", None),
    ],
)
def test_gnome_detection(monkeypatch: pytest.MonkeyPatch, raw: str, expected: str | None) -> None:
    monkeypatch.setattr(theme.shutil, "which", lambda _: "/usr/bin/gsettings")

    def fake_run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=raw)

    monkeypatch.setattr(theme.subprocess, "run", fake_run)
    assert theme.gnome_color_scheme() == expected


def test_gnome_detection_without_gsettings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(theme.shutil, "which", lambda _: None)
    assert theme.gnome_color_scheme() is None


@BOTH
def test_disabled_icons_are_dimmer_than_text(t: Tokens) -> None:
    dim = theme.disabled_color(t)
    assert contrast_ratio(dim, t.window) < contrast_ratio(t.text, t.window) / 2
    assert contrast_ratio(dim, t.window) > 1.5  # still visible


def test_ink_is_readable_on_paper_tiles() -> None:
    from pdr_sign.services import sigimage

    for ink in sigimage.INK_COLORS.values():
        hex_ink = "#{:02X}{:02X}{:02X}".format(*ink)
        for t in (LIGHT, DARK):
            assert contrast_ratio(hex_ink, t.paper) >= 4.5, (hex_ink, t.scheme)
    assert LIGHT.paper == DARK.paper  # the same light tile in both themes


def test_no_old_indigo_remains() -> None:
    root = Path(__file__).resolve().parents[1]
    old = ["#" + "4F46E5", "#" + "818CF8"]  # split so this file doesn't match itself
    files = [
        f
        for folder in ("src", "packaging", "tests", ".github")
        for f in (root / folder).rglob("*")
        if f.is_file() and f.suffix in {".py", ".svg", ".xml", ".desktop", ".yaml", ".yml", ".qss"}
    ] + [root / "README.md"]
    hits = [
        str(f.relative_to(root))
        for f in files
        if any(o.lower() in f.read_text(encoding="utf-8").lower() for o in old)
    ]
    assert not hits
