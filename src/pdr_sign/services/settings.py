"""User settings, stored as JSON. Qt-free."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Literal, get_args

from pdr_sign import APP_COMMAND

ThemeChoice = Literal["system", "light", "dark"]
ZoomChoice = Literal["fit-width", "fit-page", "100"]

THEME_CHOICES: tuple[str, ...] = get_args(ThemeChoice)
ZOOM_CHOICES: tuple[str, ...] = get_args(ZoomChoice)


@dataclass
class Settings:
    theme: ThemeChoice = "system"
    default_zoom: ZoomChoice = "fit-width"
    default_text_color: str = "#000000"
    # None means the default location from ``data_dir() / "signatures"``.
    signature_dir: str | None = None
    open_links_without_asking: bool = False
    # Reserved for a possible future paid build. No licensing logic exists.
    license_key: str | None = None


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


def config_dir() -> Path:
    """Directory for settings.json. Uses $SNAP_USER_DATA inside a snap."""
    snap = os.environ.get("SNAP_USER_DATA")
    if snap:
        return Path(snap) / "config"
    return _xdg("XDG_CONFIG_HOME", ".config") / APP_COMMAND


def data_dir() -> Path:
    """Directory for user data (signatures, recent-file thumbnails)."""
    snap = os.environ.get("SNAP_USER_DATA")
    if snap:
        return Path(snap)
    return _xdg("XDG_DATA_HOME", ".local/share") / APP_COMMAND


def settings_path() -> Path:
    return config_dir() / "settings.json"


def _coerce(raw: dict[str, Any]) -> Settings:
    defaults = Settings()
    values: dict[str, Any] = {}
    for f in fields(Settings):
        if f.name not in raw:
            continue
        value = raw[f.name]
        default = getattr(defaults, f.name)
        if f.name == "theme" and value not in THEME_CHOICES:
            continue
        if f.name == "default_zoom" and value not in ZOOM_CHOICES:
            continue
        if default is not None and not isinstance(value, type(default)):
            continue
        if default is None and value is not None and not isinstance(value, str):
            continue
        values[f.name] = value
    return Settings(**values)


def load(path: Path | None = None) -> Settings:
    """Load settings. Missing, corrupt or invalid values fall back to defaults."""
    path = path or settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    return _coerce(raw)


def save(settings: Settings, path: Path | None = None) -> None:
    """Write settings atomically (temp file + rename)."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(settings), fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
