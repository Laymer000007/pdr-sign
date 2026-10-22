"""The save pipeline. Qt-free.

Saving never touches the live document. It works on a fresh copy of the file:

1. copy the original next to itself (``.pdr-tmp``), open the copy (same password);
2. drop the copy's old PDR annotations (they're rewritten from the current items);
3. write form values (``widget.update()`` regenerates appearances), then text, mark
   and line items as tagged annotations, then signatures, initials and stamps
   into the page content;
4. optionally flatten (``Document.bake``);
5. save: incremental when the file allows it (keeps the original bytes and any
   signature revisions intact), otherwise a full rewrite; encryption is kept;
6. **verify** by reopening the result: page count, every written field value, every
   editable item (or, flattened: no widgets or annotations left), every image;
7. only then replace the target atomically (``os.replace``), keeping a
   ``.pdr-backup`` of the original until the replace has succeeded.

If anything fails, the original file is untouched and the temporary files are gone.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from pdr_sign.services import forms, stamps
from pdr_sign.services.document import MUPDF_LOCK, Document
from pdr_sign.services.forms import FieldValue
from pdr_sign.services.stamps import OverlayItem

# PyMuPDF defines its constants at import time; its type stubs don't list them.
_C: Any = pymupdf

TMP_SUFFIX = ".pdr-tmp"
BACKUP_SUFFIX = ".pdr-backup"


class SaveError(Exception):
    """Saving failed; the original file was left as it was."""


class VerificationError(SaveError):
    """The written file didn't read back as expected; nothing was replaced."""


class TargetExists(SaveError):  # noqa: N818 - reads better at call sites
    """``overwrite=False`` and a file with that name appeared: nothing was written."""


SIGNED_SUFFIX = " - signed with PDR-sign"
_NUMBERED = re.compile(r"^(?P<base>.*) \((?P<n>\d+)\)$")


def signed_copy_name(original: Path, number: int = 1) -> str:
    """``<name> - signed with PDR-sign.pdf``, or ``… (2).pdf`` and up. A signed copy
    of a signed copy counts up instead of adding the suffix twice."""
    stem = original.stem
    match = _NUMBERED.match(stem)
    if match and match["base"].endswith(SIGNED_SUFFIX):
        stem = match["base"]
    if not stem.endswith(SIGNED_SUFFIX):
        stem += SIGNED_SUFFIX
    return f"{stem}.pdf" if number == 1 else f"{stem} ({number}).pdf"


def free_name(folder: Path, name_for: Callable[[int], str], start: int = 1) -> Path:
    """The first ``folder / name_for(n)`` (n = start, start+1, …) that doesn't exist."""
    number = start
    while (folder / name_for(number)).exists():
        number += 1
    return folder / name_for(number)


def signed_copy_path(original: Path, folder: Path | None = None) -> Path:
    return free_name(folder or original.parent, lambda n: signed_copy_name(original, n))


def numbered(path: Path) -> Path:
    """``path`` if it's free, else ``name (2).pdf``, ``name (3).pdf``, … next to it."""
    if not path.exists():
        return path
    return free_name(path.parent, lambda n: f"{path.stem} ({n}){path.suffix}", start=2)


@dataclass
class SaveRequest:
    values: Mapping[str, FieldValue] = field(default_factory=dict)
    items: list[OverlayItem] = field(default_factory=list)
    flatten: bool = False


@dataclass(frozen=True)
class SaveResult:
    path: Path
    incremental: bool
    pages: int


def can_write_in_place(path: Path) -> bool:
    """Saving over ``path`` needs the file writable and its folder writable (for the
    temporary file and the atomic replace)."""
    return os.access(path, os.W_OK) and os.access(path.parent, os.W_OK)


def _open_copy(source: Path, password: str | None) -> pymupdf.Document:
    pdf = pymupdf.open(source)
    if pdf.needs_pass and not pdf.authenticate(password or ""):
        pdf.close()
        raise SaveError("The password no longer opens this file.")
    return pdf


def _apply(doc: Document, request: SaveRequest) -> None:
    stamps.read_overlays(doc, remove=True)  # current items replace the saved ones
    forms.apply_values(doc, request.values)
    stamps.write_overlays(doc, request.items)
    if request.flatten:
        with doc.locked() as pdf:
            pdf.bake(annots=True, widgets=True)


def _image_counts(pdf: pymupdf.Document) -> Counter[int]:
    return Counter({i: len(pdf[i].get_image_info()) for i in range(pdf.page_count)})


def verify(
    path: Path, password: str | None, request: SaveRequest, pages: int, images_before: Counter[int]
) -> None:
    """Reopen ``path`` and check that what we meant to write is really there."""
    try:
        written = Document.open(path, password)
    except Exception as exc:
        raise VerificationError(f"The saved file doesn't open: {exc}") from exc
    try:
        if written.page_count != pages:
            raise VerificationError(
                f"The saved file has {written.page_count} pages instead of {pages}."
            )
        with written.locked() as pdf:
            images_after = _image_counts(pdf)
            widgets = sum(1 for i in range(pdf.page_count) for _ in pdf[i].widgets())
            annots = sum(1 for i in range(pdf.page_count) for _ in pdf[i].annots())
            text = {i: pdf[i].get_text() for i in {it.page for it in request.items}}
        placed = Counter(it.page for it in request.items if it.is_image and it.image)
        for page, count in placed.items():
            if images_after[page] < images_before[page] + count:
                raise VerificationError(f"A signature or stamp is missing on page {page + 1}.")
        if request.flatten:
            if widgets or annots:
                raise VerificationError("The flattened copy still has form fields or notes.")
            for item in request.items:
                if item.kind in stamps.TEXT_KINDS and item.text:
                    first = item.text.split()[0]
                    if first not in text.get(item.page, ""):
                        raise VerificationError(f"Text “{first}” is missing after flattening.")
            return
        values = forms.field_values(forms.list_fields(written))
        for name, value in request.values.items():
            if name in values and values[name] != value:
                raise VerificationError(f"The field “{name}” didn't keep its new value.")
        expected = Counter(it.kind for it in request.items if not it.is_image)
        found = Counter(it.kind for it in stamps.read_overlays(written))
        if found != expected:
            raise VerificationError("Some text, marks or lines are missing from the saved file.")
    finally:
        written.close()


def _create_exclusively(work: Path, target: Path) -> None:
    """Put ``work`` at ``target`` only if nothing is there: never overwrites, even if
    a file appears between choosing the name and writing it."""
    try:
        os.link(work, target)  # atomic, and fails if target exists
    except FileExistsError as exc:
        raise TargetExists(target.name) from exc
    except OSError:  # file systems without hard links (FAT, some network shares)
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError as exc:
            raise TargetExists(target.name) from exc
        with os.fdopen(fd, "wb") as out, open(work, "rb") as src:
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
    work.unlink(missing_ok=True)


def save(
    source: Document, target: Path, request: SaveRequest, overwrite: bool = True
) -> SaveResult:
    """Write ``request`` on top of ``source``'s file to ``target`` (maybe the same path).

    The live ``source`` document is not modified. With ``overwrite=False`` an existing
    ``target`` is never replaced (``TargetExists``).
    """
    origin = source.path
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    work = target.with_name(target.name + TMP_SUFFIX)
    backup = target.with_name(target.name + BACKUP_SUFFIX)
    try:
        shutil.copyfile(origin, work)
        with MUPDF_LOCK:
            pdf = _open_copy(work, source.password)
        doc = Document(pdf, work, source.password)
        with doc.locked() as raw:
            pages = raw.page_count
            images_before = _image_counts(raw)
            incremental = bool(raw.can_save_incrementally()) and not request.flatten
        _apply(doc, request)
        with doc.locked() as raw:
            if incremental:
                raw.save(work, incremental=True, encryption=_C.PDF_ENCRYPT_KEEP)
            else:
                # A full rewrite (always for flattened copies, so the old form data and
                # annotations really are gone rather than hidden in earlier revisions).
                fresh = work.with_name(work.name + ".full")
                raw.save(fresh, garbage=3, deflate=True, encryption=_C.PDF_ENCRYPT_KEEP)
                os.replace(fresh, work)
        doc.close()
        verify(work, source.password, request, pages, images_before)
        with open(work, "rb") as fh:
            os.fsync(fh.fileno())
        if not overwrite:
            _create_exclusively(work, target)
            return SaveResult(target, incremental, pages)
        if target.exists():
            shutil.copy2(target, backup)
        os.replace(work, target)
        backup.unlink(missing_ok=True)
        return SaveResult(target, incremental, pages)
    except SaveError:
        raise
    except Exception as exc:
        raise SaveError(f"Couldn't save: {exc}") from exc
    finally:
        with contextlib.suppress(OSError):
            work.unlink(missing_ok=True)
            work.with_name(work.name + ".full").unlink(missing_ok=True)
