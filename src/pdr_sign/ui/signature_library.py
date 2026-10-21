"""The signatures and initials on offer: saved ones (on disk) plus this session's
"don't remember" ones (memory only, gone when PDR closes)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from pdr_sign.services.signatures import SignatureKind, SignatureStore


@dataclass(frozen=True)
class LibraryItem:
    id: str
    kind: SignatureKind
    png: bytes
    saved: bool


class SignatureLibrary(QObject):
    changed = Signal()

    def __init__(self, store: SignatureStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._session: list[LibraryItem] = []

    def items(self, kind: SignatureKind) -> list[LibraryItem]:
        """Newest first: this session's unsaved ones, then the saved ones."""
        session = [i for i in reversed(self._session) if i.kind == kind]
        saved = [LibraryItem(s.id, kind, s.png(), True) for s in self.store.list(kind)]
        return session + saved

    def latest(self, kind: SignatureKind) -> LibraryItem | None:
        items = self.items(kind)
        return items[0] if items else None

    def add(self, kind: SignatureKind, png: bytes, remember: bool) -> LibraryItem:
        if remember:
            saved = self.store.add(kind, png)
            item = LibraryItem(saved.id, kind, png, True)
        else:
            item = LibraryItem(uuid.uuid4().hex[:12], kind, png, False)
            self._session.append(item)
        self.changed.emit()
        return item

    def remove(self, kind: SignatureKind, item_id: str) -> None:
        before = len(self._session)
        self._session = [i for i in self._session if i.id != item_id]
        if len(self._session) == before:
            self.store.remove(kind, item_id)
        self.changed.emit()
