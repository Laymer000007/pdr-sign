"""``pdr-sign --self-test`` passes, also when rerun in the same folder."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from pdr_sign import selftest


def test_self_test_passes_twice(
    qtbot: QtBot, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert selftest.main([str(tmp_path)]) == 0
    assert selftest.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out
    assert "signed with PDR-sign (4).pdf" in out
