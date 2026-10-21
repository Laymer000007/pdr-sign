"""Text selection state for one document (drag on the canvas, double-click a word)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from pdr_sign.services.document import Document
from pdr_sign.services.text import (
    Rect,
    TextPos,
    join_words,
    line_rects,
    nearest_word,
    selected_ranges,
    word_at,
)


class TextSelection(QObject):
    changed = Signal(object)  # set[int] of pages whose highlight changed

    def __init__(self, doc: Document, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.anchor: TextPos | None = None
        self.head: TextPos | None = None
        self._rects: dict[int, list[Rect]] = {}

    @property
    def is_empty(self) -> bool:
        return self.anchor is None or self.head is None

    def begin(self, page: int, x: float, y: float) -> bool:
        index = nearest_word(self.doc.words(page), x, y)
        if index is None:
            return False
        self.anchor = self.head = TextPos(page, index)
        self._update()
        return True

    def extend(self, page: int, x: float, y: float) -> None:
        if self.anchor is None:
            self.begin(page, x, y)
            return
        index = nearest_word(self.doc.words(page), x, y)
        if index is not None:
            self.head = TextPos(page, index)
            self._update()

    def select_word(self, page: int, x: float, y: float) -> bool:
        index = word_at(self.doc.words(page), x, y)
        if index is None:
            return False
        self.anchor = self.head = TextPos(page, index)
        self._update()
        return True

    def select_page(self, page: int) -> None:
        count = len(self.doc.words(page))
        if count:
            self.anchor, self.head = TextPos(page, 0), TextPos(page, count - 1)
            self._update()

    def clear(self) -> None:
        if self.is_empty:
            return
        self.anchor = self.head = None
        self._update()

    def ranges(self) -> dict[int, tuple[int, int]]:
        if self.anchor is None or self.head is None:
            return {}
        low, high = sorted((self.anchor.page, self.head.page))
        counts = {p: len(self.doc.words(p)) for p in range(low, high + 1)}
        return selected_ranges(self.anchor, self.head, counts)

    def rects(self, page: int) -> list[Rect]:
        return self._rects.get(page, [])

    def text(self) -> str:
        chunks = []
        for page, (first, last) in sorted(self.ranges().items()):
            chunks.append(join_words(self.doc.words(page)[first : last + 1]))
        return "\n".join(chunks)

    def _update(self) -> None:
        before = set(self._rects)
        self._rects = {
            page: line_rects(self.doc.words(page)[first : last + 1])
            for page, (first, last) in self.ranges().items()
        }
        self.changed.emit(before | set(self._rects))
