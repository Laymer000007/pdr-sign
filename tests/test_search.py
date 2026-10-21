from pathlib import Path

from pdr_sign.services.document import Document
from pdr_sign.services.search import page_order, search_page, snippet
from pdr_sign.services.text import Word


def test_page_order_wraps() -> None:
    assert list(page_order(5, 3)) == [3, 4, 0, 1, 2]


def test_search_page_hits_and_snippets(text_pdf: Path) -> None:
    doc = Document.open(text_pdf)
    hits = search_page(doc, 1, "Page 2")
    assert len(hits) == 1
    assert hits[0].page == 1
    assert "Page 2" in hits[0].snippet
    assert search_page(doc, 1, "Page 3") == []
    doc.close()


def test_snippet_trims_long_lines_around_match() -> None:
    words = [Word((i * 10, 0, i * 10 + 8, 10), f"w{i}", 0, 0) for i in range(60)]
    words[40] = Word((400, 0, 408, 10), "needle", 0, 0)
    text = snippet(words, (400, 0, 408, 10), "needle", width=30)
    assert "needle" in text
    assert text.startswith("…") and text.endswith("…")
    assert len(text) <= 32
