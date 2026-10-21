from pathlib import Path

import pymupdf
import pytest

from pdr_sign.services.document import (
    Document,
    DocumentError,
    PasswordRequired,
    WrongPassword,
)
from tests.conftest import ENCRYPTED_PASSWORD


def test_open_reports_pages(text_pdf: Path) -> None:
    doc = Document.open(text_pdf)
    assert doc.page_count == 3
    assert (doc.pages[0].width, doc.pages[0].height) == (595, 842)
    assert [p.label for p in doc.pages] == ["1", "2", "3"]
    assert doc.display_name == "three-pages.pdf"
    doc.close()


def test_rotated_page_reports_visible_size(rich_pdf: Path) -> None:
    doc = Document.open(rich_pdf)
    assert (doc.pages[3].width, doc.pages[3].height) == (842, 595)  # landscape
    assert (doc.pages[4].width, doc.pages[4].height) == (842, 595)  # portrait rotated 90°
    assert doc.display_name == "Rich sample"
    doc.close()


def test_outline(rich_pdf: Path) -> None:
    doc = Document.open(rich_pdf)
    entries = doc.outline()
    assert [(e.level, e.title, e.page) for e in entries] == [
        (1, "Part one", 0),
        (2, "Chapter 2", 1),
        (1, "Part two", 3),
        (2, "Five", 4),
    ]
    doc.close()


def test_links(rich_pdf: Path) -> None:
    doc = Document.open(rich_pdf)
    links = doc.links(0)
    internal = next(link for link in links if link.page is not None)
    external = next(link for link in links if link.uri)
    assert internal.page == 2
    assert internal.y == pytest.approx(200)
    assert internal.rect == pytest.approx((72, 100, 172, 120))
    assert external.uri == "https://example.org"
    doc.close()


def test_link_rects_follow_rotation(rich_pdf: Path) -> None:
    doc = Document.open(rich_pdf)
    (link,) = doc.links(4)
    # Unrotated (0,0)-(50,20) on an 842-tall page rotated 90° clockwise.
    assert link.rect == pytest.approx((822, 0, 842, 50))
    doc.close()


def test_link_target_on_rotated_page(tmp_path: Path) -> None:
    src = pymupdf.open()
    src.new_page(width=595, height=842)
    src.new_page(width=595, height=842)
    src[0].insert_link(
        {
            "kind": pymupdf.LINK_GOTO,
            "from": pymupdf.Rect(0, 0, 50, 20),
            "page": 1,
            "to": pymupdf.Point(72, 280),
        }
    )
    src[1].set_rotation(90)
    src.save(tmp_path / "t.pdf")
    doc = Document.open(tmp_path / "t.pdf")
    (link,) = doc.links(0)
    # Unrotated y=280 lies at visible y=72 once the target is turned 90°.
    assert link.page == 1 and link.y == pytest.approx(72)
    doc.close()


@pytest.mark.parametrize(("zoom", "dpr"), [(1.0, 1.0), (1.5, 2.0), (0.5, 1.0)])
def test_render_tile_size(text_pdf: Path, zoom: float, dpr: float) -> None:
    doc = Document.open(text_pdf)
    tile = doc.render_tile(0, zoom, dpr, clip=(0, 0, 100, 50))
    assert (tile.width, tile.height) == (round(100 * zoom * dpr), round(50 * zoom * dpr))
    assert len(tile.data) == tile.stride * tile.height
    whole = doc.render_tile(0, zoom, dpr)
    assert whole.width == round(595 * zoom * dpr)
    doc.close()


def test_rendered_page_has_ink(text_pdf: Path) -> None:
    doc = Document.open(text_pdf)
    tile = doc.render_tile(0, 1.0, 1.0)
    assert min(tile.data) < 100  # some dark text pixels on white
    doc.close()


def test_thumbnail_png(text_pdf: Path) -> None:
    doc = Document.open(text_pdf)
    assert doc.thumbnail_png(width=80).startswith(b"\x89PNG")
    doc.close()


def test_password_flow(encrypted_pdf: Path) -> None:
    with pytest.raises(PasswordRequired) as info:
        Document.open(encrypted_pdf)
    assert not isinstance(info.value, WrongPassword)
    with pytest.raises(WrongPassword):
        Document.open(encrypted_pdf, "nope")
    doc = Document.open(encrypted_pdf, ENCRYPTED_PASSWORD)
    assert doc.is_encrypted and doc.page_count == 1
    doc.close()


def test_not_a_pdf(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.pdf"
    bogus.write_text("hello")
    with pytest.raises(DocumentError):
        Document.open(bogus)
    with pytest.raises(DocumentError):
        Document.open(tmp_path / "missing.pdf")


def test_render_after_close_raises(text_pdf: Path) -> None:
    doc = Document.open(text_pdf)
    doc.close()
    with pytest.raises((ValueError, RuntimeError)):
        doc.render_tile(0, 1.0, 1.0)


def test_ids_are_unique(text_pdf: Path) -> None:
    a, b = Document.open(text_pdf), Document.open(text_pdf)
    assert a.id != b.id
    a.close()
    b.close()
