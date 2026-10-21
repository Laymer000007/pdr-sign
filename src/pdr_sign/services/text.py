"""Words on a page and word-based text selection. Qt-free.

Selection works on words in MuPDF's reading order: a selection runs from an anchor
word to a head word (possibly on another page), inclusive.
"""

from __future__ import annotations

from dataclasses import dataclass

Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class Word:
    rect: Rect  # visible page coordinates (points)
    text: str
    block: int
    line: int

    @property
    def line_key(self) -> tuple[int, int]:
        return self.block, self.line


@dataclass(frozen=True, order=True)
class TextPos:
    page: int
    word: int


def _distance(rect: Rect, x: float, y: float) -> float:
    dx = max(rect[0] - x, 0.0, x - rect[2])
    dy = max(rect[1] - y, 0.0, y - rect[3])
    # Vertical distance counts double so the pointer prefers words on its own line.
    return dx * dx + 4 * dy * dy


def word_at(words: list[Word], x: float, y: float) -> int | None:
    """Index of the word containing (x, y), if any."""
    for i, word in enumerate(words):
        x0, y0, x1, y1 = word.rect
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None


def nearest_word(words: list[Word], x: float, y: float) -> int | None:
    if not words:
        return None
    hit = word_at(words, x, y)
    if hit is not None:
        return hit
    return min(range(len(words)), key=lambda i: _distance(words[i].rect, x, y))


def join_words(words: list[Word]) -> str:
    """Words joined with spaces, and newlines where the line changes."""
    parts: list[str] = []
    previous: Word | None = None
    for word in words:
        if previous is not None:
            parts.append(" " if word.line_key == previous.line_key else "\n")
        parts.append(word.text)
        previous = word
    return "".join(parts)


def line_rects(words: list[Word]) -> list[Rect]:
    """One highlight rect per line, so selections read as bands, not word boxes."""
    rects: list[Rect] = []
    current: list[float] | None = None
    key: tuple[int, int] | None = None
    for word in words:
        x0, y0, x1, y1 = word.rect
        if current is not None and word.line_key == key:
            current[0], current[1] = min(current[0], x0), min(current[1], y0)
            current[2], current[3] = max(current[2], x1), max(current[3], y1)
            continue
        if current is not None:
            rects.append((current[0], current[1], current[2], current[3]))
        current, key = [x0, y0, x1, y1], word.line_key
    if current is not None:
        rects.append((current[0], current[1], current[2], current[3]))
    return rects


def selected_ranges(
    a: TextPos, b: TextPos, word_counts: dict[int, int]
) -> dict[int, tuple[int, int]]:
    """Per page, the inclusive ``(first, last)`` word indices between ``a`` and ``b``.

    ``word_counts`` gives the number of words on every page in the span.
    """
    start, end = min(a, b), max(a, b)
    ranges: dict[int, tuple[int, int]] = {}
    for page in range(start.page, end.page + 1):
        count = word_counts.get(page, 0)
        if count == 0:
            continue
        first = start.word if page == start.page else 0
        last = end.word if page == end.page else count - 1
        if first <= last:
            ranges[page] = (first, min(last, count - 1))
    return ranges
