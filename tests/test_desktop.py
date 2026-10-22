"""Show in folder: FileManager1 when it answers, otherwise the folder via the desktop."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from pdr_sign.ui import desktop


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    seen: dict[str, list[Any]] = {"run": [], "open": []}
    monkeypatch.setattr(desktop.shutil, "which", lambda _name: "/usr/bin/dbus-send")
    monkeypatch.setattr(desktop.QDesktopServices, "openUrl", lambda url: seen["open"].append(url))
    monkeypatch.delenv("SNAP_NAME", raising=False)
    return seen


def test_file_manager_answer_selects_the_file(
    calls: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(desktop.subprocess, "run", lambda args, **_: calls["run"].append(args))
    desktop.show_in_folder(tmp_path / "a.pdf")
    assert "--print-reply" in calls["run"][0]
    assert calls["open"] == []


def test_refused_call_opens_the_folder(
    calls: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(args: list[str], **_: object) -> None:
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(desktop.subprocess, "run", refuse)
    desktop.show_in_folder(tmp_path / "a.pdf")
    assert calls["open"][0].toLocalFile() == str(tmp_path)


def test_snap_skips_file_manager(
    calls: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SNAP_NAME", "pdr-sign")
    monkeypatch.setattr(desktop.subprocess, "run", lambda args, **_: calls["run"].append(args))
    desktop.show_in_folder(tmp_path / "a.pdf")
    assert calls["run"] == []
    assert calls["open"][0].toLocalFile() == str(tmp_path)
