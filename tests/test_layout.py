import pytest

from pdr_sign.services import layout


def test_zoom_steps() -> None:
    assert layout.zoom_in(1.0) == 1.1
    assert layout.zoom_out(1.0) == 0.9
    assert layout.zoom_in(1.05) == 1.1
    assert layout.zoom_in(4.0) == layout.MAX_ZOOM
    assert layout.zoom_out(0.5) == 0.5
    assert layout.zoom_out(0.3) == 0.3
    assert layout.clamp_zoom(100) == layout.MAX_ZOOM


def test_fit_width_leaves_gap() -> None:
    zoom = layout.fit_width_zoom(500, 1034, 16)
    assert 500 * zoom + 2 * 16 <= 1034
    assert zoom == pytest.approx(2.0, abs=0.01)


def test_fit_page_uses_tighter_axis() -> None:
    zoom = layout.fit_page_zoom(600, 800, 2000, 434, 16)
    assert 800 * zoom <= 434 - 32


def test_layout_stacks_and_centres() -> None:
    lay = layout.PageLayout([(100, 200), (200, 100)], zoom=2.0, gap_px=16)
    gap = 8  # 16 px at 2x
    assert lay.gap == gap
    first, second = lay.slots
    assert (first.x, first.y) == (gap + 50, gap)
    assert (second.x, second.y) == (gap, gap + 200 + gap)
    assert lay.height == second.bottom + gap
    assert lay.width == 200 + 2 * gap


def test_page_at_and_visible_pages() -> None:
    lay = layout.PageLayout([(100, 100)] * 5, zoom=1.0, gap_px=10)
    assert lay.page_at(0) == 0
    assert lay.page_at(115) == 0  # gap below page 0
    assert lay.page_at(125) == 1
    assert lay.page_at(10_000) == 4
    assert list(lay.visible_pages(50, 250)) == [0, 1, 2]


def test_anchor_round_trip() -> None:
    a = layout.PageLayout([(100, 100)] * 3, zoom=1.0, gap_px=10)
    page, x, y = a.anchor(60, 150)
    b = layout.PageLayout([(100, 100)] * 3, zoom=3.0, gap_px=10)
    assert (page, x, y) == (1, 50, 30)
    assert b.scene_point(page, x, y) == pytest.approx((b.slots[1].x + 50, b.slots[1].y + 30))
