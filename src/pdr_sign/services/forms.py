"""AcroForm fields: list them, read values, apply values. Qt-free.

Values are keyed by the fully qualified field name, so several widgets of one field
(a radio group, or a name printed twice) stay in step:

- text and combo box: ``str``
- check box and radio group: the selected widget's "on" state, or ``""`` for off
- list box: ``tuple[str, ...]`` of selected export values
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import pymupdf

from pdr_sign.services.document import Document
from pdr_sign.services.text import Rect

# PyMuPDF defines its constants at import time; its type stubs don't list them.
_C: Any = pymupdf

FieldKind = Literal["text", "checkbox", "radio", "combo", "list", "signature", "button"]
FieldValue = str | tuple[str, ...]

OFF = "Off"

# Field flags (PDF 32000-1, tables 226, 228, 230; bit n is 1 << (n - 1)).
FF_READ_ONLY = 1 << 0
FF_REQUIRED = 1 << 1
FF_MULTILINE = 1 << 12
FF_PASSWORD = 1 << 13
FF_COMBO_EDIT = 1 << 18
FF_MULTI_SELECT = 1 << 21
FF_COMB = 1 << 24

_KINDS: dict[int, FieldKind] = {
    _C.PDF_WIDGET_TYPE_TEXT: "text",
    _C.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
    _C.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
    _C.PDF_WIDGET_TYPE_COMBOBOX: "combo",
    _C.PDF_WIDGET_TYPE_LISTBOX: "list",
    _C.PDF_WIDGET_TYPE_SIGNATURE: "signature",
    _C.PDF_WIDGET_TYPE_BUTTON: "button",
}


@dataclass(frozen=True)
class FieldInfo:
    id: int  # the widget annotation's xref; unique per widget
    name: str
    kind: FieldKind
    page: int
    rect: Rect  # visible page coordinates
    order: int  # tab order: page order, then annotation order on the page
    value: FieldValue
    label: str = ""  # the /TU tooltip, if the form provides one
    on_state: str = ""  # check box / radio: this widget's "on" value
    options: tuple[tuple[str, str], ...] = ()  # (export value, display text)
    flags: int = 0
    max_len: int = 0
    font_size: float = 0.0  # 0 = auto
    is_signed: bool = False

    @property
    def read_only(self) -> bool:
        return bool(self.flags & FF_READ_ONLY)

    @property
    def required(self) -> bool:
        return bool(self.flags & FF_REQUIRED)

    @property
    def multiline(self) -> bool:
        return self.kind == "text" and bool(self.flags & FF_MULTILINE)

    @property
    def password(self) -> bool:
        return self.kind == "text" and bool(self.flags & FF_PASSWORD)

    @property
    def comb(self) -> bool:
        return self.kind == "text" and bool(self.flags & FF_COMB) and self.max_len > 0

    @property
    def editable(self) -> bool:
        """Free text is allowed in a combo box."""
        return self.kind == "combo" and bool(self.flags & FF_COMBO_EDIT)

    @property
    def multi_select(self) -> bool:
        return self.kind == "list" and bool(self.flags & FF_MULTI_SELECT)

    @property
    def fillable(self) -> bool:
        return self.kind not in ("signature", "button") and not self.read_only

    @property
    def display_name(self) -> str:
        return self.label or self.name.rsplit(".", 1)[-1]


def _options(raw: object) -> tuple[tuple[str, str], ...]:
    result = []
    for item in raw if isinstance(raw, list | tuple) else []:
        if isinstance(item, list | tuple) and len(item) == 2:
            result.append((str(item[0]), str(item[1])))
        else:
            result.append((str(item), str(item)))
    return tuple(result)


def _read_value(widget: pymupdf.Widget, kind: FieldKind) -> FieldValue:
    value = widget.field_value
    if kind in ("checkbox", "radio"):
        on = widget.on_state() or ""
        checked = value is True or (isinstance(value, str) and value not in ("", OFF))
        return on if checked and on else ""
    if kind == "list":
        if isinstance(value, list | tuple):
            return tuple(str(v) for v in value)
        return (str(value),) if value else ()
    return "" if value is None else str(value)


_PDF_STRING = re.compile(r"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>")
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "(": "(", ")": ")", "\\": "\\"}


def _pdf_strings(array: str) -> tuple[str, ...]:
    """The string items of a PDF array such as ``[(a) (c\\)d) <4142>]``."""
    items = []
    for token in _PDF_STRING.findall(array):
        if token.startswith("<"):
            items.append(bytes.fromhex("".join(token[1:-1].split())).decode("latin-1"))
        else:
            body = token[1:-1]
            items.append(re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), body))
    return tuple(items)


def _list_selection(pdf: pymupdf.Document, widget: pymupdf.Widget) -> tuple[str, ...] | None:
    """A multi-selection stored as a /V array (PyMuPDF only reads single values)."""
    for xref in (widget.xref, _parent_xref(pdf, widget.xref)):
        if xref:
            kind, value = pdf.xref_get_key(xref, "V")
            if kind == "array":
                return _pdf_strings(value)
    return None


def _parent_xref(pdf: pymupdf.Document, xref: int) -> int:
    kind, value = pdf.xref_get_key(xref, "Parent")
    return int(value.split()[0]) if kind == "xref" else 0


def list_fields(doc: Document) -> list[FieldInfo]:
    """Every widget in tab order (page by page, annotation order within a page)."""
    fields: list[FieldInfo] = []
    with doc.locked() as pdf:
        if not pdf.is_form_pdf:
            return fields
        for index in range(pdf.page_count):
            page = pdf[index]
            matrix = page.rotation_matrix
            for widget in page.widgets():
                kind = _KINDS.get(widget.field_type)
                if kind is None or not widget.field_name:
                    continue
                r = pymupdf.Rect(widget.rect) * matrix
                value = _read_value(widget, kind)
                if kind == "list":
                    value = _list_selection(pdf, widget) or value
                fields.append(
                    FieldInfo(
                        id=widget.xref,
                        name=widget.field_name,
                        kind=kind,
                        page=index,
                        rect=(r.x0, r.y0, r.x1, r.y1),
                        order=len(fields),
                        value=value,
                        label=widget.field_label or "",
                        on_state=(widget.on_state() or "") if kind in ("checkbox", "radio") else "",
                        options=_options(widget.choice_values),
                        flags=int(widget.field_flags or 0),
                        max_len=int(widget.text_maxlen or 0),
                        font_size=float(widget.text_fontsize or 0),
                        is_signed=bool(kind == "signature" and getattr(widget, "is_signed", False)),
                    )
                )
    return fields


def field_values(fields: list[FieldInfo]) -> dict[str, FieldValue]:
    """The current value of each field (radio groups resolved to the checked widget)."""
    values: dict[str, FieldValue] = {}
    for f in fields:
        if f.kind in ("signature", "button"):
            continue
        if f.kind in ("checkbox", "radio"):
            if f.value or f.name not in values:
                values[f.name] = f.value
        else:
            values.setdefault(f.name, f.value)
    return values


def apply_values(doc: Document, values: Mapping[str, FieldValue]) -> set[int]:
    """Write ``values`` into the in-memory PDF and regenerate appearances.

    Returns the indices of the pages that changed. Nothing is saved to disk.
    """
    changed: set[int] = set()
    if not values:
        return changed
    with doc.locked() as pdf:
        for index in range(pdf.page_count):
            for widget in pdf[index].widgets():
                name = widget.field_name
                if name not in values:
                    continue
                kind = _KINDS.get(widget.field_type)
                value = values[name]
                if kind in ("checkbox", "radio"):
                    # PyMuPDF treats any string (even "Off") as "on"; booleans are safe.
                    # Selecting one radio kid turns its siblings off by itself.
                    on = widget.on_state() or ""
                    checked = bool(value) and value == on
                    if kind == "radio" and not checked and value:
                        continue  # another kid of this group is the one being selected
                    widget.field_value = checked
                elif kind == "list":
                    selected = list(value) if isinstance(value, tuple) else [value]
                    widget.field_value = selected[0] if selected else ""
                    widget.update()
                    if len(selected) > 1:
                        _set_multi_selection(pdf, widget, selected)
                    changed.add(index)
                    continue
                elif kind == "combo" and isinstance(value, str):
                    exports = [o[0] for o in _options(widget.choice_values)]
                    if value and value not in exports:
                        # Free text in an editable combo. Viewers that draw combos as a
                        # plain <select> (pdf.js, so Firefox) only show listed values.
                        _append_option(pdf, widget, value)
                    widget.field_value = value
                elif kind in ("text", "combo"):
                    widget.field_value = value if isinstance(value, str) else ", ".join(value)
                else:
                    continue
                widget.update()
                changed.add(index)
    doc.invalidate_render()
    return changed


def _set_multi_selection(
    pdf: pymupdf.Document, widget: pymupdf.Widget, selected: list[str]
) -> None:
    """PyMuPDF only sets one choice, so write /V and /I (the selected indices) directly."""
    exports = [o[0] for o in _options(widget.choice_values)]
    values = " ".join(pymupdf.get_pdf_str(v) for v in selected)
    indices = " ".join(str(exports.index(v)) for v in selected if v in exports)
    holder = _field_xref(pdf, widget)
    pdf.xref_set_key(holder, "V", f"[{values}]")
    pdf.xref_set_key(holder, "I", f"[{indices}]")


def _field_xref(pdf: pymupdf.Document, widget: pymupdf.Widget) -> int:
    """The object holding the field's data: the widget itself, or its parent field
    when the widget is only a kid (no /T of its own)."""
    if pdf.xref_get_key(widget.xref, "T")[0] != "null":
        return int(widget.xref)
    return _parent_xref(pdf, widget.xref) or int(widget.xref)


def _append_option(pdf: pymupdf.Document, widget: pymupdf.Widget, value: str) -> None:
    holder = _field_xref(pdf, widget)
    kind, opt = pdf.xref_get_key(holder, "Opt")
    items = opt.strip()[1:-1] if kind == "array" else ""
    pdf.xref_set_key(holder, "Opt", f"[{items} {pymupdf.get_pdf_str(value)}]")


def has_xfa(doc: Document) -> bool:
    with doc.locked() as pdf:
        kind, _ = pdf.xref_get_key(pdf.pdf_catalog(), "AcroForm/XFA")
    return kind not in ("null", "")


def is_signed(fields: list[FieldInfo]) -> bool:
    return any(f.is_signed for f in fields)
