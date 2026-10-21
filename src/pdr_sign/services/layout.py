"""Continuous-scroll page layout and zoom maths. Qt-free.

Scene units are PDF points. The vertical gap between pages is a fixed number of screen
pixels, so in scene units it shrinks as the zoom grows.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

MIN_ZOOM = 0.1
MAX_ZOOM = 4.0
ZOOM_STEPS = (0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)
MENU_ZOOMS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)


def clamp_zoom(zoom: float) -> float:
    return max(MIN_ZOOM, min(MAX_ZOOM, zoom))


def zoom_in(zoom: float) -> float:
    for step in ZOOM_STEPS:
        if step > zoom + 1e-3:
            return step
    return MAX_ZOOM


def zoom_out(zoom: float) -> float:
    for step in reversed(ZOOM_STEPS):
        if step < zoom - 1e-3:
            return step
    return clamp_zoom(min(zoom, ZOOM_STEPS[0]))


# Pixels of slack so rounding never makes a fitted page trigger a horizontal scrollbar.
FIT_SLACK_PX = 2


def fit_width_zoom(page_width: float, viewport_width: float, gap_px: float) -> float:
    return clamp_zoom((viewport_width - 2 * gap_px - FIT_SLACK_PX) / page_width)


def fit_page_zoom(
    page_width: float, page_height: float, viewport_w: float, viewport_h: float, gap_px: float
) -> float:
    return clamp_zoom(
        min(
            (viewport_w - 2 * gap_px - FIT_SLACK_PX) / page_width,
            (viewport_h - 2 * gap_px - FIT_SLACK_PX) / page_height,
        )
    )


@dataclass(frozen=True)
class PageSlot:
    x: float
    y: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height


class PageLayout:
    """Vertical stack of pages, each centred horizontally."""

    def __init__(self, sizes: list[tuple[float, float]], zoom: float, gap_px: float) -> None:
        self.zoom = zoom
        self.gap = gap_px / zoom
        self.content_width = max(w for w, _ in sizes)
        self.width = self.content_width + 2 * self.gap
        self.slots: list[PageSlot] = []
        y = self.gap
        for w, h in sizes:
            self.slots.append(PageSlot(self.gap + (self.content_width - w) / 2, y, w, h))
            y += h + self.gap
        self.height = y
        self._tops = [s.y for s in self.slots]

    def page_at(self, y: float) -> int:
        """Index of the page at scene ``y`` (gaps count toward the page above)."""
        return max(0, min(len(self.slots) - 1, bisect.bisect_right(self._tops, y) - 1))

    def visible_pages(self, top: float, bottom: float) -> range:
        first = self.page_at(top)
        last = self.page_at(bottom)
        return range(first, last + 1)

    def anchor(self, x: float, y: float) -> tuple[int, float, float]:
        """Express a scene point as ``(page, x, y)`` relative to that page's origin."""
        index = self.page_at(y)
        slot = self.slots[index]
        return index, x - slot.x, y - slot.y

    def scene_point(self, page: int, x: float, y: float) -> tuple[float, float]:
        slot = self.slots[page]
        return slot.x + x, slot.y + y
