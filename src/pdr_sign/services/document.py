"""PDF document access on top of PyMuPDF. Qt-free.

MuPDF is not safe to call from several threads at once, and PyMuPDF releases the GIL
while rendering. Every PyMuPDF call therefore goes through ``MUPDF_LOCK``.
"""

from __future__ import annotations

import itertools
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from pdr_sign.services.text import Word

MUPDF_LOCK = threading.RLock()

# PyMuPDF prints MuPDF warnings to stderr by default. Collect them instead.
pymupdf.TOOLS.mupdf_display_errors(False)

_doc_ids = itertools.count(1)
WORD_CACHE_PAGES = 64

Rect = tuple[float, float, float, float]


class DocumentError(Exception):
    """The file could not be opened as a PDF."""


class PasswordRequired(DocumentError):  # noqa: N818 - reads better at call sites
    """The PDF is encrypted. Call ``Document.open`` again with ``password``."""


class WrongPassword(PasswordRequired):
    pass


@dataclass(frozen=True)
class PageInfo:
    index: int
    width: float  # points, after rotation (what the reader sees)
    height: float
    label: str


@dataclass(frozen=True)
class OutlineEntry:
    level: int  # 1 = top level
    title: str
    page: int  # 0-based; -1 when the entry points nowhere in this document
    y: float | None  # top of the target in page points, when known


@dataclass(frozen=True)
class LinkInfo:
    rect: Rect  # visible page coordinates (points)
    page: int | None = None  # internal target, 0-based
    y: float | None = None
    uri: str | None = None


@dataclass(frozen=True)
class Tile:
    """Rendered pixels, packed RGB888 rows of ``stride`` bytes."""

    width: int
    height: int
    stride: int
    data: bytes


class Document:
    """An open PDF. All methods are safe to call from any thread."""

    def __init__(self, doc: pymupdf.Document, path: Path, password: str | None) -> None:
        self._doc = doc
        self.path = path
        self.password = password
        self.id = next(_doc_ids)
        with MUPDF_LOCK:
            self.pages: list[PageInfo] = [self._page_info(i) for i in range(doc.page_count)]
            self.title = (doc.metadata or {}).get("title") or ""
            self.is_encrypted = bool(doc.is_encrypted or password)
        self._words: OrderedDict[int, list[Word]] = OrderedDict()

    # --- lifecycle -----------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path, password: str | None = None) -> Document:
        path = Path(path).expanduser().resolve()
        with MUPDF_LOCK:
            try:
                doc = pymupdf.open(path, filetype="pdf")
            except (pymupdf.FileDataError, pymupdf.FileNotFoundError, RuntimeError) as exc:
                raise DocumentError(f"Couldn't open {path.name}: {exc}") from exc
            if doc.needs_pass:
                if password is None:
                    doc.close()
                    raise PasswordRequired(path.name)
                if not doc.authenticate(password):
                    doc.close()
                    raise WrongPassword(path.name)
            if doc.page_count == 0:
                doc.close()
                raise DocumentError(f"{path.name} has no pages")
        return cls(doc, path, password)

    def close(self) -> None:
        with MUPDF_LOCK:
            self._doc.close()

    # --- metadata ------------------------------------------------------------

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def display_name(self) -> str:
        return self.title.strip() or self.path.name

    def _page_info(self, index: int) -> PageInfo:
        page = self._doc[index]
        rect = page.rect
        return PageInfo(index, rect.width, rect.height, page.get_label() or str(index + 1))

    def outline(self) -> list[OutlineEntry]:
        with MUPDF_LOCK:
            toc = self._doc.get_toc(simple=False)
        entries = []
        for level, title, page_no, *rest in toc:
            dest = rest[0] if rest else {}
            to = dest.get("to") if isinstance(dest, dict) else None
            page = page_no - 1 if 1 <= page_no <= self.page_count else -1
            y = self._visible_y(page, to) if page >= 0 and to is not None else None
            entries.append(OutlineEntry(level, title.strip() or "Untitled", page, y))
        return entries

    def links(self, index: int) -> list[LinkInfo]:
        with MUPDF_LOCK:
            # get_links() already reports rects and targets in visible (rotated)
            # coordinates, unlike search_for(), which needs page.rotation_matrix.
            raw = self._doc[index].get_links()
            result = []
            for link in raw:
                r = pymupdf.Rect(link["from"])
                rect = (r.x0, r.y0, r.x1, r.y1)
                kind = link.get("kind")
                if kind == pymupdf.LINK_URI and link.get("uri"):
                    result.append(LinkInfo(rect, uri=link["uri"]))
                elif kind in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED):
                    target = link.get("page", -1)
                    if kind == pymupdf.LINK_NAMED and target < 0:
                        target = self._resolve_named(link.get("name") or link.get("nameddest"))
                    if 0 <= target < self.page_count:
                        y = self._visible_y(target, link.get("to"))
                        result.append(LinkInfo(rect, page=target, y=y))
        return result

    def _resolve_named(self, name: str | None) -> int:
        if not name:
            return -1
        try:
            dest = self._doc.resolve_names().get(name, {})
        except (RuntimeError, AttributeError):
            return -1
        page = dest.get("page", -1) if isinstance(dest, dict) else -1
        return int(page)

    def _visible_y(self, index: int, to: object) -> float | None:
        if not isinstance(to, pymupdf.Point):
            return None
        return max(0.0, min(float(to.y), self.pages[index].height))

    # --- text ----------------------------------------------------------------

    def words(self, index: int) -> list[Word]:
        """Words on page ``index`` in reading order, in visible coordinates (cached)."""
        with MUPDF_LOCK:
            cached = self._words.get(index)
            if cached is not None:
                self._words.move_to_end(index)
                return cached
            page = self._doc[index]
            matrix = page.rotation_matrix
            words = []
            for x0, y0, x1, y1, text, block, line, _ in page.get_text("words", sort=False):
                r = pymupdf.Rect(x0, y0, x1, y1) * matrix  # words come unrotated
                words.append(Word((r.x0, r.y0, r.x1, r.y1), text, block, line))
            self._words[index] = words
            if len(self._words) > WORD_CACHE_PAGES:
                self._words.popitem(last=False)
            return words

    def find(self, index: int, query: str) -> list[Rect]:
        """Case-insensitive matches of ``query`` on a page, in visible coordinates.

        A match that wraps onto a second line yields one rect per line.
        """
        with MUPDF_LOCK:
            page = self._doc[index]
            matrix = page.rotation_matrix
            hits = page.search_for(query)
        return [(r.x0, r.y0, r.x1, r.y1) for r in (h * matrix for h in hits)]

    # --- rendering -----------------------------------------------------------

    def render_tile(self, index: int, zoom: float, dpr: float, clip: Rect | None = None) -> Tile:
        """Render page ``index`` at ``zoom * dpr`` device pixels per point.

        ``clip`` is in visible page coordinates (points); None renders the whole page.
        """
        scale = zoom * dpr
        with MUPDF_LOCK:
            page = self._doc[index]
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                clip=pymupdf.Rect(clip) if clip else None,
                alpha=False,
                annots=True,
            )
            return Tile(pix.width, pix.height, pix.stride, bytes(pix.samples))

    def thumbnail_png(self, index: int = 0, width: int = 160) -> bytes:
        info = self.pages[index]
        scale = width / info.width
        with MUPDF_LOCK:
            pix = self._doc[index].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            return bytes(pix.tobytes("png"))

    def warnings(self) -> str:
        """MuPDF warnings collected so far (useful when a file renders oddly)."""
        with MUPDF_LOCK:
            return str(pymupdf.TOOLS.mupdf_warnings())
