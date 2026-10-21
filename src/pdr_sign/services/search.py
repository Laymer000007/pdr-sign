"""Full-text search with result snippets. Qt-free.

The UI searches page by page on a worker thread (see ``ui/search_controller.py``) so
results stream in while the user keeps reading.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from pdr_sign.services.document import Document
from pdr_sign.services.text import Rect, Word, join_words

MAX_HITS = 5000
SNIPPET_CHARS = 72


@dataclass(frozen=True)
class SearchHit:
    page: int
    rect: Rect  # visible page coordinates
    snippet: str


def _overlap(a: Rect, b: Rect) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(w, 0.0) * max(h, 0.0)


def snippet(words: list[Word], rect: Rect, query: str, width: int = SNIPPET_CHARS) -> str:
    """The line containing the hit, trimmed to about ``width`` characters around it."""
    if not words:
        return query
    best = max(words, key=lambda w: _overlap(w.rect, rect))
    if _overlap(best.rect, rect) == 0:
        return query
    line = join_words([w for w in words if w.line_key == best.line_key])
    if len(line) <= width:
        return line
    at = max(line.lower().find(query.lower()), 0)
    start = max(0, min(at - (width - len(query)) // 2, len(line) - width))
    text = line[start : start + width]
    return ("…" if start > 0 else "") + text + ("…" if start + width < len(line) else "")


def search_page(doc: Document, index: int, query: str) -> list[SearchHit]:
    rects = doc.find(index, query)
    if not rects:
        return []
    words = doc.words(index)
    return [SearchHit(index, r, snippet(words, r, query)) for r in rects]


def page_order(page_count: int, start: int) -> Iterator[int]:
    """Pages from ``start`` to the end, then wrapping round to ``start - 1``."""
    for offset in range(page_count):
        yield (start + offset) % page_count
