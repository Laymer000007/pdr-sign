"""Fill every field of a PDF the way PDR saves, then check the copy (dev tool).

    .venv/bin/python tools/fill_check.py samples/private/*.pdf

For each input it writes ``build/verify/<name>-filled.pdf`` (git-ignored, never next
to the original), re-reads the copy to confirm every value stuck, and prints what to
look for. Open the copies in Firefox, or in the bundled pdf.js page:

    python3 -m http.server 8791 --bind 127.0.0.1 --directory build/verify
    → http://127.0.0.1:8791/viewer.html?file=<name>-filled.pdf
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdr_sign.services import forms  # noqa: E402
from pdr_sign.services.document import Document, PasswordRequired  # noqa: E402
from pdr_sign.services.forms import FieldInfo, FieldValue  # noqa: E402

OUT = ROOT / "build" / "verify"


def sample_value(field: FieldInfo, group: list[FieldInfo]) -> FieldValue | None:
    if field.kind == "text":
        if field.comb or field.max_len:
            return ("1234567890" * 10)[: field.max_len]
        return "First line\nSecond line" if field.multiline else f"Test {field.display_name}"[:60]
    if field.kind in ("checkbox", "radio"):
        return group[-1].on_state or None  # the last option, so it differs from defaults
    if field.kind == "combo":
        if field.editable:
            return "Typed value"
        return field.options[-1][0] if field.options else None
    if field.kind == "list" and field.options:
        picks = field.options[:2] if field.multi_select else field.options[-1:]
        return tuple(export for export, _ in picks)
    return None


def check(path: Path) -> bool:
    try:
        doc = Document.open(path)
    except PasswordRequired:
        print(f"  skipped {path.name}: password protected")
        return True
    fields = forms.list_fields(doc)
    if forms.has_xfa(doc):
        print("  note: XFA form; PDR fills its AcroForm fields only")
    groups: dict[str, list[FieldInfo]] = {}
    for f in fields:
        if f.fillable:
            groups.setdefault(f.name, []).append(f)
    values = {}
    for name, group in groups.items():
        value = sample_value(group[0], group)
        if value is not None:
            values[name] = value
    forms.apply_values(doc, values)
    out = OUT / f"{path.stem}-filled.pdf"
    with doc.locked() as pdf:
        pdf.save(out, garbage=0, deflate=True)
    doc.close()

    kinds = sorted({f.kind for f in fields})
    print(f"  {len(groups)} fillable fields ({', '.join(kinds)}) → {out.relative_to(ROOT)}")
    reread = forms.field_values(forms.list_fields(Document.open(out)))
    ok = True
    for name, value in values.items():
        got = reread.get(name)
        if got != value:
            ok = False
            print(f"  MISMATCH {name!r}: wrote {value!r}, read back {got!r}")
    print("  all values read back" if ok else "  some values did not survive")
    return ok


def main(paths: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "tools" / "pdfjs-check" / "viewer.html", OUT / "viewer.html")
    results = []
    for raw in paths:
        print(raw)
        results.append(check(Path(raw)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
