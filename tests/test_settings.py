import json
from dataclasses import asdict
from pathlib import Path

import pytest

from pdr_sign.services import settings as s


def test_defaults_when_missing(tmp_path: Path) -> None:
    assert s.load(tmp_path / "nope.json") == s.Settings()


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    value = s.Settings(theme="dark", default_zoom="fit-page", open_links_without_asking=True)
    s.save(value, path)
    assert s.load(path) == value
    assert not list(tmp_path.glob(".settings-*")), "temp file left behind"


def test_corrupt_file_falls_back(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert s.load(path) == s.Settings()


def test_invalid_values_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "neon", "default_zoom": 7, "license_key": 5, "extra": 1}))
    assert s.load(path) == s.Settings()


def test_old_license_key_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "dark", "license_key": "abc"}))
    loaded = s.load(path)
    assert loaded.theme == "dark"
    assert not hasattr(loaded, "license_key")
    assert json.loads(path.read_text()) == asdict(loaded)  # rewritten without it
    assert "license_key" not in path.read_text()


def test_welcome_flag_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert not s.load(path).welcome_shown
    s.save(s.Settings(welcome_shown=True), path)
    assert s.load(path).welcome_shown


def test_default_paths_follow_xdg(tmp_path: Path) -> None:
    assert s.settings_path() == tmp_path / "config" / "pdr-sign" / "settings.json"
    assert s.data_dir() == tmp_path / "data" / "pdr-sign"


def test_snap_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNAP_USER_DATA", str(tmp_path / "snap"))
    assert s.config_dir() == tmp_path / "snap" / "config"
    assert s.data_dir() == tmp_path / "snap"
