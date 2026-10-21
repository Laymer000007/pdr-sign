"""Shared fixtures. Sample PDFs are generated with PyMuPDF, never checked in."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest

# Headless by default; CI may override with xvfb (QT_QPA_PLATFORM=xcb).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ENCRYPTED_PASSWORD = "pdr-test"


def make_text_pdf(path: Path, pages: int) -> Path:
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        page = doc.new_page(width=595, height=842)  # A4 in points
        page.insert_text((72, 72), f"Page {n}", fontsize=24)
        page.insert_textbox(
            pymupdf.Rect(72, 110, 523, 770),
            "The quick brown fox jumps over the lazy dog. " * 30,
            fontsize=11,
        )
    doc.save(path)
    doc.close()
    return path


@pytest.fixture(autouse=True)
def isolated_user_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep tests away from the real ~/.config and ~/.local/share."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("SNAP_USER_DATA", raising=False)
    yield


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    return make_text_pdf(tmp_path / "three-pages.pdf", 3)


@pytest.fixture(scope="session")
def long_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_text_pdf(tmp_path_factory.mktemp("long") / "five-hundred.pdf", 500)


def make_rich_pdf(path: Path) -> Path:
    """Outline, an internal and an external link, a landscape and a rotated page."""
    doc = pymupdf.open()
    for n in range(1, 7):
        w, h = (842, 595) if n == 4 else (595, 842)
        doc.new_page(width=w, height=h).insert_text((72, 72), f"Chapter {n}", fontsize=20)
    page = doc[0]
    page.insert_link(
        {
            "kind": pymupdf.LINK_GOTO,
            "from": pymupdf.Rect(72, 100, 172, 120),
            "page": 2,
            "to": pymupdf.Point(0, 200),
        }
    )
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(72, 130, 172, 150),
            "uri": "https://example.org",
        }
    )
    doc[4].insert_link(
        {"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(0, 0, 50, 20), "uri": "https://r.example"}
    )
    doc[4].set_rotation(90)
    doc.set_toc([[1, "Part one", 1], [2, "Chapter 2", 2], [1, "Part two", 4], [2, "Five", 5]])
    doc.set_metadata({"title": "Rich sample"})
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def rich_pdf(tmp_path: Path) -> Path:
    return make_rich_pdf(tmp_path / "rich.pdf")


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    src = make_text_pdf(tmp_path / "plain.pdf", 1)
    doc = pymupdf.open(src)
    out = tmp_path / "encrypted.pdf"
    doc.save(
        out,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw=ENCRYPTED_PASSWORD + "-owner",
        user_pw=ENCRYPTED_PASSWORD,
    )
    doc.close()
    return out


class FakeClipboard:
    """Stands in for the system clipboard so tests never overwrite the user's."""

    def __init__(self) -> None:
        self.texts: dict[str, str] = {}

    def setText(self, text: str, mode: object = None) -> None:
        self.texts["selection" if "Selection" in str(mode) else "clipboard"] = text

    def text(self) -> str:
        return self.texts.get("clipboard", "")

    def supportsSelection(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def fake_clipboard(monkeypatch: pytest.MonkeyPatch) -> FakeClipboard:
    board = FakeClipboard()
    monkeypatch.setattr("pdr_sign.ui.canvas.clipboard", lambda: board)
    return board


def trigger_shortcut(widget: object, keys: str) -> None:
    """Fire the action bound to ``keys`` without needing an active window (xcb/xvfb)."""
    from PySide6.QtGui import QKeySequence

    wanted = QKeySequence(keys)
    for action in widget.actions():  # type: ignore[attr-defined]
        if any(
            seq.matches(wanted) == QKeySequence.SequenceMatch.ExactMatch
            for seq in action.shortcuts()
        ):
            action.trigger()
            return
    raise AssertionError(f"no action bound to {keys}")
