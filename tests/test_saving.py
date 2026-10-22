"""The save pipeline: round trip, incremental, encryption, flatten, verify, atomicity."""

from __future__ import annotations

import io
import os
import stat
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from pdr_sign.services import forms, saving, stamps
from pdr_sign.services.document import Document
from pdr_sign.services.saving import SaveRequest
from pdr_sign.services.stamps import OverlayItem
from tests.conftest import ENCRYPTED_PASSWORD


def png(width: int = 200, height: int = 60) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((0, 0, 0, 255), (0, height // 2 - 3, width, height // 2 + 3))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def everything() -> SaveRequest:
    return SaveRequest(
        values={"name": "Jane Ndlovu", "agree": "Yes", "colour": "blue", "fruit": ("plum",)},
        items=[
            OverlayItem("text", 0, (320, 330, 480, 346), text="Signed at Cape Town"),
            OverlayItem("check", 0, (400, 173, 414, 187), font_size=14),
            OverlayItem("line", 0, (100, 400, 250, 400), font_size=12),
            OverlayItem("signature", 1, (300, 700, 500, 750), image=png()),
            OverlayItem("initials", 0, (500, 780, 550, 800), image=png(100, 40)),
            OverlayItem("stamp", 0, (300, 450, 420, 510), image=png(), rotation=20, opacity=0.7),
        ],
    )


def test_save_in_place_round_trips_and_appends(form_pdf: Path) -> None:
    before = form_pdf.read_bytes()
    doc = Document.open(form_pdf)
    result = saving.save(doc, form_pdf, everything())
    assert result.incremental
    after = form_pdf.read_bytes()
    assert after.startswith(before)  # incremental: the original bytes are untouched
    assert not list(form_pdf.parent.glob("*.pdr-*"))  # no temp or backup left behind
    # The live document wasn't changed by saving.
    assert (
        stamps.read_overlays(doc) == [] and forms.field_values(forms.list_fields(doc))["name"] == ""
    )
    doc.close()

    again = Document.open(form_pdf)
    values = forms.field_values(forms.list_fields(again))
    assert values["name"] == "Jane Ndlovu" and values["colour"] == "blue"
    assert sorted(i.kind for i in stamps.read_overlays(again)) == ["check", "line", "text"]
    with again.locked() as pdf:
        assert len(pdf[0].get_image_info()) == 2 and len(pdf[1].get_image_info()) == 1
    again.close()


def test_saving_again_replaces_editable_items(form_pdf: Path) -> None:
    doc = Document.open(form_pdf)
    saving.save(
        doc, form_pdf, SaveRequest(items=[OverlayItem("text", 0, (50, 50, 150, 66), text="one")])
    )
    doc.close()
    doc = Document.open(form_pdf)
    (item,) = stamps.read_overlays(doc, remove=True)  # as the UI does on open
    moved = item.moved_to((60, 60, 160, 76))
    saving.save(doc, form_pdf, SaveRequest(items=[moved]))
    doc.close()
    (back,) = stamps.read_overlays(Document.open(form_pdf))
    assert back.rect == pytest.approx(moved.rect, abs=0.5)  # moved, not duplicated


def test_save_as_leaves_the_original_alone(form_pdf: Path, tmp_path: Path) -> None:
    original = form_pdf.read_bytes()
    doc = Document.open(form_pdf)
    target = tmp_path / "copy" / "filled.pdf"
    saving.save(doc, target, everything())
    assert form_pdf.read_bytes() == original
    assert forms.field_values(forms.list_fields(Document.open(target)))["name"] == "Jane Ndlovu"


def test_encryption_is_kept(encrypted_pdf: Path) -> None:
    doc = Document.open(encrypted_pdf, ENCRYPTED_PASSWORD)
    saving.save(
        doc,
        encrypted_pdf,
        SaveRequest(items=[OverlayItem("text", 0, (50, 50, 150, 66), text="hi")]),
    )
    doc.close()
    raw = pymupdf.open(encrypted_pdf)
    assert raw.needs_pass
    assert raw.authenticate(ENCRYPTED_PASSWORD)
    assert [
        i.text for i in stamps.read_overlays(Document.open(encrypted_pdf, ENCRYPTED_PASSWORD))
    ] == ["hi"]


def test_flattened_copy(form_pdf: Path, tmp_path: Path) -> None:
    doc = Document.open(form_pdf)
    request = everything()
    request.flatten = True
    result = saving.save(doc, tmp_path / "flat.pdf", request)
    assert not result.incremental
    flat = pymupdf.open(tmp_path / "flat.pdf")
    assert sum(1 for p in flat for _ in p.widgets()) == 0
    assert sum(1 for p in flat for _ in p.annots()) == 0
    text = flat[0].get_text()
    assert "Jane Ndlovu" in text and "Signed at Cape Town" in text
    assert b"/AcroForm" not in (tmp_path / "flat.pdf").read_bytes() or flat.is_form_pdf == 0
    assert stamps.read_overlays(Document.open(tmp_path / "flat.pdf")) == []  # nothing editable


def test_failed_verification_keeps_the_original(
    form_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = form_pdf.read_bytes()
    doc = Document.open(form_pdf)

    def broken(*_: object) -> None:
        raise saving.VerificationError("The field “name” didn't keep its new value.")

    monkeypatch.setattr(saving, "verify", broken)
    with pytest.raises(saving.VerificationError):
        saving.save(doc, form_pdf, everything())
    assert form_pdf.read_bytes() == original
    assert not list(form_pdf.parent.glob("*.pdr-*"))


def test_verification_really_reads_the_file(
    form_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If writing silently lost a value, verify must catch it."""
    original = form_pdf.read_bytes()
    real_apply = forms.apply_values
    monkeypatch.setattr(forms, "apply_values", lambda doc, values: real_apply(doc, {}))
    doc = Document.open(form_pdf)
    with pytest.raises(saving.VerificationError, match="name"):
        saving.save(doc, form_pdf, SaveRequest(values={"name": "Lost"}))
    assert form_pdf.read_bytes() == original


def test_crash_before_replace_keeps_the_original(
    form_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = form_pdf.read_bytes()
    doc = Document.open(form_pdf)
    real_replace = os.replace

    def crash(src: object, dst: object) -> None:
        if str(dst) == str(form_pdf):
            raise OSError("power cut")
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(saving.SaveError, match="power cut"):
        saving.save(doc, form_pdf, everything())
    assert form_pdf.read_bytes() == original
    backup = form_pdf.with_name(form_pdf.name + saving.BACKUP_SUFFIX)
    assert backup.read_bytes() == original  # the backup survives a failed replace
    assert not form_pdf.with_name(form_pdf.name + saving.TMP_SUFFIX).exists()


def test_can_write_in_place(form_pdf: Path) -> None:
    assert saving.can_write_in_place(form_pdf)
    form_pdf.chmod(stat.S_IRUSR)
    try:
        assert not saving.can_write_in_place(form_pdf)
    finally:
        form_pdf.chmod(stat.S_IRUSR | stat.S_IWUSR)
