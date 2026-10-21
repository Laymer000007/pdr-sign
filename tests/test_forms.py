from pathlib import Path

import pymupdf
import pytest

from pdr_sign.services import forms
from pdr_sign.services.document import Document


def save_copy(doc: Document, path: Path) -> Path:
    with doc.locked() as pdf:
        pdf.save(path)
    return path


def test_lists_every_kind_in_tab_order(form_pdf: Path) -> None:
    doc = Document.open(form_pdf)
    fields = forms.list_fields(doc)
    kinds = {f.kind for f in fields}
    assert kinds == {"text", "checkbox", "radio", "combo", "list", "signature"}
    assert [f.order for f in fields] == list(range(len(fields)))
    by_name = {f.name: f for f in fields}
    assert by_name["name"].display_name == "Full name"
    assert by_name["notes"].multiline
    assert by_name["code"].comb and by_name["code"].max_len == 6
    assert by_name["ref"].read_only and not by_name["ref"].fillable
    assert by_name["city"].editable and not by_name["country"].editable
    assert by_name["signature"].kind == "signature" and not by_name["signature"].fillable
    radios = [f for f in fields if f.kind == "radio"]
    assert [r.on_state for r in radios] == ["red", "green", "blue"]
    assert by_name["name"].rect == pytest.approx((72, 72, 300, 92))
    doc.close()


def test_initial_values(form_pdf: Path) -> None:
    doc = Document.open(form_pdf)
    values = forms.field_values(forms.list_fields(doc))
    assert values["ref"] == "R-1"
    assert values["country"] == "ZA"
    assert values["fruit"] == ("pear",)
    assert values["agree"] == "" and values["colour"] == ""
    assert "signature" not in values
    doc.close()


def test_fill_save_reopen(form_pdf: Path, tmp_path: Path) -> None:
    doc = Document.open(form_pdf)
    new = {
        "name": "Jane Ndlovu",
        "notes": "Line one\nLine two",
        "code": "ABC123",
        "agree": "Yes",
        "colour": "green",
        "country": "NL",
        "city": "Pretoria",  # free text in an editable combo
        "fruit": ("plum",),
        "city_again": "Durban",
    }
    assert forms.apply_values(doc, new) == {0, 1}
    out = save_copy(doc, tmp_path / "filled.pdf")
    doc.close()

    again = Document.open(out)
    values = forms.field_values(forms.list_fields(again))
    for name, value in new.items():
        assert values[name] == value, name
    with again.locked() as pdf:
        text = pdf[0].get_text()
        # The appearance streams were regenerated, so every viewer shows the values.
        assert "Jane Ndlovu" in text and "Line two" in text and "NL" in text
        radio_states = [
            pdf.xref_get_key(w.xref, "AS")[1] for w in pdf[0].widgets() if w.field_name == "colour"
        ]
    assert radio_states == ["/Off", "/green", "/Off"]
    city = next(f for f in forms.list_fields(again) if f.name == "city")
    assert ("Pretoria", "Pretoria") in city.options  # so <select>-style viewers show it
    again.close()


def test_unchecking_and_clearing(form_pdf: Path, tmp_path: Path) -> None:
    doc = Document.open(form_pdf)
    forms.apply_values(doc, {"agree": "Yes", "colour": "blue"})
    forms.apply_values(doc, {"agree": "", "colour": ""})
    out = save_copy(doc, tmp_path / "off.pdf")
    doc.close()
    values = forms.field_values(forms.list_fields(Document.open(out)))
    assert values["agree"] == "" and values["colour"] == ""


def test_multi_select_list(tmp_path: Path) -> None:
    src = pymupdf.open()
    page = src.new_page()
    w = pymupdf.Widget()
    w.field_type, w.field_name = pymupdf.PDF_WIDGET_TYPE_LISTBOX, "tags"
    w.rect = pymupdf.Rect(72, 72, 200, 140)
    w.choice_values = ["a", "b", "c"]
    w.field_flags = forms.FF_MULTI_SELECT
    page.add_widget(w)
    src.save(tmp_path / "multi.pdf")
    doc = Document.open(tmp_path / "multi.pdf")
    (field,) = forms.list_fields(doc)
    assert field.multi_select
    forms.apply_values(doc, {"tags": ("a", "c")})
    out = save_copy(doc, tmp_path / "multi2.pdf")
    doc.close()
    assert forms.field_values(forms.list_fields(Document.open(out)))["tags"] == ("a", "c")


def test_plain_pdf_has_no_fields(text_pdf: Path) -> None:
    doc = Document.open(text_pdf)
    assert forms.list_fields(doc) == []
    assert not forms.has_xfa(doc)
    doc.close()
