"""Saved signatures, initials and company stamps: transparent PNGs on disk. Qt-free.

Default folder: ``~/.local/share/pdr-sign/signatures/`` (inside a snap,
``$SNAP_USER_DATA/signatures``), or ``Settings.signature_dir``. Signatures are
personal, so the folder is 0700 and each file 0600. At most ``MAX_PER_KIND`` of each
kind are kept; saving another drops the oldest.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pdr_sign.services.settings import data_dir

SignatureKind = Literal["signature", "initials", "stamp"]
KINDS: tuple[SignatureKind, ...] = ("signature", "initials", "stamp")
MAX_PER_KIND = 5


def as_kind(value: str) -> SignatureKind:
    if value not in KINDS:
        raise ValueError(f"not a signature kind: {value!r}")
    return value  # narrowed to SignatureKind by the membership test


@dataclass(frozen=True)
class SavedSignature:
    id: str
    kind: SignatureKind
    path: Path
    created: float

    def png(self) -> bytes:
        return self.path.read_bytes()


def default_dir() -> Path:
    return data_dir() / "signatures"


class SignatureStore:
    def __init__(self, folder: str | Path | None = None) -> None:
        self.folder = Path(folder).expanduser() if folder else default_dir()

    def _ensure_folder(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        os.chmod(self.folder, 0o700)

    def list(self, kind: SignatureKind) -> list[SavedSignature]:
        """Newest first."""
        if not self.folder.is_dir():
            return []
        items = []
        for path in self.folder.glob(f"{kind}-*.png"):
            parts = path.stem.split("-")
            if len(parts) != 3:
                continue
            try:
                created = int(parts[1]) / 1_000_000
            except ValueError:
                continue
            items.append(SavedSignature(parts[2], kind, path, created))
        return sorted(items, key=lambda s: s.created, reverse=True)

    def get(self, kind: SignatureKind, sig_id: str) -> SavedSignature | None:
        return next((s for s in self.list(kind) if s.id == sig_id), None)

    def add(self, kind: SignatureKind, png: bytes) -> SavedSignature:
        if not png.startswith(b"\x89PNG"):
            raise ValueError("signatures are stored as PNG")
        self._ensure_folder()
        micros = time.time_ns() // 1000  # microseconds keep quick successive saves ordered
        created = micros / 1_000_000
        sig_id = uuid.uuid4().hex[:12]
        path = self.folder / f"{kind}-{micros}-{sig_id}.png"
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(png)
        os.replace(tmp, path)
        for old in self.list(kind)[MAX_PER_KIND:]:
            old.path.unlink(missing_ok=True)
        return SavedSignature(sig_id, kind, path, created)

    def remove(self, kind: SignatureKind, sig_id: str) -> bool:
        saved = self.get(kind, sig_id)
        if saved is None:
            return False
        saved.path.unlink(missing_ok=True)
        return True
