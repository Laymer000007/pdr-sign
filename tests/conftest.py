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


def _widget(
    page: pymupdf.Page, kind: int, name: str, rect: tuple[float, ...], **kw: object
) -> None:
    w = pymupdf.Widget()
    w.field_type = kind
    w.field_name = name
    w.rect = pymupdf.Rect(rect)
    for key, value in kw.items():
        setattr(w, key, value)
    page.add_widget(w)


def _radio_group(
    doc: pymupdf.Document, page: pymupdf.Page, name: str, states: list[str], top: float
) -> None:
    """A radio group as real forms build it: one parent field, one kid per option.

    (PyMuPDF's add_widget makes each radio its own field, which real forms don't.)
    """
    parent = doc.get_new_xref()
    kids = []
    for i, state in enumerate(states):
        kid = doc.get_new_xref()
        x0 = 72 + i * 40
        y0 = page.rect.height - top - 14  # PDF space is bottom-up
        doc.update_object(
            kid,
            f"<< /Type /Annot /Subtype /Widget /Parent {parent} 0 R "
            f"/Rect [{x0} {y0} {x0 + 14} {y0 + 14}] /F 4 /P {page.xref} 0 R /AS /Off "
            f"/MK << /BC [0 0 0] /BG [1 1 1] /CA (l) >> "
            f"/AP << /N << /{state} null /Off null >> >> >>",
        )
        kids.append(f"{kid} 0 R")
    doc.update_object(
        parent, f"<< /FT /Btn /Ff 49152 /T ({name}) /V /Off /Kids [{' '.join(kids)}] >>"
    )
    annots = doc.xref_get_key(page.xref, "Annots")[1]
    doc.xref_set_key(page.xref, "Annots", annots.replace("]", " " + " ".join(kids) + "]"))
    cat = doc.pdf_catalog()
    fields = doc.xref_get_key(cat, "AcroForm/Fields")[1]
    doc.xref_set_key(cat, "AcroForm/Fields", fields.replace("]", f" {parent} 0 R]"))


def make_form_pdf(path: Path) -> Path:
    """An AcroForm with every field type, over two pages."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 60), "Application form", fontsize=16)
    T = pymupdf  # noqa: N806 - short alias keeps the field table readable
    _widget(
        p1,
        T.PDF_WIDGET_TYPE_TEXT,
        "name",
        (72, 72, 300, 92),
        text_fontsize=11,
        field_label="Full name",
    )
    _widget(
        p1,
        T.PDF_WIDGET_TYPE_TEXT,
        "notes",
        (72, 100, 300, 160),
        field_flags=T.PDF_TX_FIELD_IS_MULTILINE,
        text_fontsize=0,
    )
    _widget(
        p1, T.PDF_WIDGET_TYPE_TEXT, "code", (320, 72, 440, 92), text_maxlen=6, field_flags=1 << 24
    )  # comb
    _widget(
        p1, T.PDF_WIDGET_TYPE_TEXT, "ref", (320, 100, 440, 120), field_value="R-1", field_flags=1
    )  # read-only
    _widget(p1, T.PDF_WIDGET_TYPE_CHECKBOX, "agree", (72, 170, 86, 184), field_value=False)
    _widget(
        p1,
        T.PDF_WIDGET_TYPE_COMBOBOX,
        "country",
        (72, 230, 250, 250),
        choice_values=["ZA", "NL", "DE"],
        field_value="ZA",
    )
    _widget(
        p1,
        T.PDF_WIDGET_TYPE_COMBOBOX,
        "city",
        (300, 230, 480, 250),
        choice_values=["Cape Town", "Durban"],
        field_value="",
        field_flags=1 << 18,
    )  # editable
    _widget(
        p1,
        T.PDF_WIDGET_TYPE_LISTBOX,
        "fruit",
        (72, 260, 250, 320),
        choice_values=["apple", "pear", "plum"],
        field_value="pear",
    )
    p2 = doc.new_page(width=595, height=842)
    _widget(p2, T.PDF_WIDGET_TYPE_TEXT, "city_again", (72, 72, 300, 92))
    _widget(p2, T.PDF_WIDGET_TYPE_SIGNATURE, "signature", (300, 700, 500, 750))
    _radio_group(doc, doc[0], "colour", ["red", "green", "blue"], top=200)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def form_pdf(tmp_path: Path) -> Path:
    return make_form_pdf(tmp_path / "form.pdf")


@pytest.fixture
def signed_pdf(tmp_path: Path) -> Path:
    """The form with its signature field signed (structurally: /V is a /Sig dict)."""
    path = make_form_pdf(tmp_path / "unsigned.pdf")
    doc = pymupdf.open(path)
    sig = doc.get_new_xref()
    doc.update_object(
        sig,
        "<< /Type /Sig /Filter /PDR.Test /SubFilter /adbe.pkcs7.detached "
        "/ByteRange [0 0 0 0] /Contents <00> /M (D:20261022000000Z) >>",
    )
    for widget in doc[1].widgets():
        if widget.field_name == "signature":
            doc.xref_set_key(widget.xref, "V", f"{sig} 0 R")
    doc.save(tmp_path / "signed.pdf")
    return tmp_path / "signed.pdf"


@pytest.fixture
def xfa_pdf(tmp_path: Path) -> Path:
    path = make_form_pdf(tmp_path / "plain-form.pdf")
    doc = pymupdf.open(path)
    packet = doc.get_new_xref()
    doc.update_object(packet, "<< /Length 0 >>")
    doc.update_stream(packet, b"<xdp/>")  # contents don't matter for detection
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm/XFA", f"[(template) {packet} 0 R]")
    doc.save(tmp_path / "xfa.pdf")
    return tmp_path / "xfa.pdf"


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


@pytest.fixture(autouse=True)
def no_save_dialogs(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[object]]:
    """Save-related modal dialogs would block the run. By default: discard unsaved
    changes on close, cancel the signed-document warning, cancel Save As.
    Tests override these with monkeypatch to drive other answers."""
    from pdr_sign.ui import dialogs

    asked: dict[str, list[object]] = {"unsaved": [], "signed": [], "path": []}

    def unsaved(_parent: object, name: str) -> str:
        asked["unsaved"].append(name)
        return "discard"

    def signed(_parent: object) -> str:
        asked["signed"].append(True)
        return "cancel"

    def save_path(_parent: object, title: str, suggested: object) -> None:
        asked["path"].append((title, suggested))
        return None

    monkeypatch.setattr(dialogs, "ask_unsaved", unsaved)
    monkeypatch.setattr(dialogs, "confirm_signed", signed)
    monkeypatch.setattr(dialogs, "ask_save_path", save_path)
    return asked
