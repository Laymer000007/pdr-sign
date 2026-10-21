from pathlib import Path

import pymupdf
import pytest

from pdr_sign.services.document import Document
from pdr_sign.services.text import (
    TextPos,
    Word,
    join_words,
    line_rects,
    nearest_word,
    selected_ranges,
    word_at,
)

WORDS = [
    Word((0, 0, 10, 10), "Hello", 0, 0),
    Word((12, 0, 30, 10), "brave", 0, 0),
    Word((0, 20, 20, 30), "new", 0, 1),
    Word((22, 20, 40, 30), "world", 0, 1),
]


def test_word_at_and_nearest() -> None:
    assert word_at(WORDS, 15, 5) == 1
    assert word_at(WORDS, 11, 5) is None
    assert nearest_word(WORDS, 11, 5) in (0, 1)
    assert nearest_word(WORDS, 100, 25) == 3  # far right of line two
    assert nearest_word([], 0, 0) is None


def test_join_and_line_rects() -> None:
    assert join_words(WORDS) == "Hello brave\nnew world"
    assert line_rects(WORDS) == [(0, 0, 30, 10), (0, 20, 40, 30)]


def test_selected_ranges_across_pages() -> None:
    counts = {1: 10, 2: 0, 3: 5}
    ranges = selected_ranges(TextPos(3, 2), TextPos(1, 4), counts)  # backwards drag
    assert ranges == {1: (4, 9), 3: (0, 2)}


def test_document_words_follow_rotation(tmp_path: Path) -> None:
    src = pymupdf.open()
    page = src.new_page(width=595, height=842)
    page.insert_text((72, 100), "Hello brave world", fontsize=12)
    page.set_rotation(90)
    src.save(tmp_path / "r.pdf")
    doc = Document.open(tmp_path / "r.pdf")
    words = doc.words(0)
    assert [w.text for w in words] == ["Hello", "brave", "world"]
    for w in words:  # inside the visible 842 x 595 page, and tall rather than wide
        x0, y0, x1, y1 = w.rect
        assert 0 <= x0 < x1 <= 842 and 0 <= y0 < y1 <= 595
        assert y1 - y0 > x1 - x0
    assert doc.words(0) is words  # cached
    doc.close()


def test_find_matches_words(text_pdf: Path) -> None:
    doc = Document.open(text_pdf)
    hits = doc.find(0, "LAZY dog")  # case-insensitive, spans two words
    assert hits
    words = doc.words(0)
    lazy = next(w for w in words if w.text == "lazy")
    assert hits[0][0] == pytest.approx(lazy.rect[0], abs=0.5)
    doc.close()
