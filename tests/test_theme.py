import re
import subprocess
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
    assert (LIGHT.accent, DARK.accent) == ("#4F46E5", "#818CF8")


@BOTH
def test_text_contrast(t: Tokens) -> None:
    for fg, bg in [
        (t.text, t.window),
        (t.text, t.surface),
        (t.muted, t.window),
        (t.muted, t.surface),
        (t.on_accent, t.accent),
    ]:
        assert contrast_ratio(fg, bg) >= 4.5, (fg, bg)


@BOTH
def test_accent_is_visible_as_focus_ring(t: Tokens) -> None:
    # WCAG non-text contrast: 3:1 against adjacent colours.
    assert contrast_ratio(t.accent, t.window) >= 3
    assert contrast_ratio(t.accent, t.surface) >= 3


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
