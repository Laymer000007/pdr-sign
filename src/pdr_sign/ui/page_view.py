"""Continuous-scroll page view: layout, zoom, navigation and tile requests.

Pointer interaction (links, selection, highlights) lives in ``ui/canvas.py``.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QKeyEvent,
    QNativeGestureEvent,
    QPainter,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QScroller, QWidget

from pdr_sign.services import layout
from pdr_sign.services.document import Document
from pdr_sign.ui.page_item import PageItem, tile_key, tiles, zoom_key
from pdr_sign.ui.render_scheduler import RenderRequest, RenderScheduler
from pdr_sign.ui.theme import ANIMATION_MS, PAGE_GAP, animations_enabled
from pdr_sign.ui.zoom_indicator import ZoomIndicator

ZoomMode = str  # "fit-width" | "fit-page" | "" (free zoom)
SETTLE_MS = 150
PREFETCH_PAGES = 2
READING_LINE = 1 / 3  # fraction of the viewport height that decides the current page


class PageView(QGraphicsView):
    current_page_changed = Signal(int)
    zoom_changed = Signal(float, str)  # zoom, mode

    def __init__(
        self, doc: Document, scheduler: RenderScheduler, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.doc = doc
        self.scheduler = scheduler
        self.owner = f"view-{id(self)}"
        self.setObjectName("Canvas")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.TouchGesture)

        self.page_items: list[PageItem] = []
        for info in doc.pages:
            item = PageItem(doc, info, scheduler)
            self.scene().addItem(item)
            self.page_items.append(item)

        self.zoom = 1.0
        self.zoom_mode: ZoomMode = "fit-width"
        self.render_zoom = 0.0
        self.page_layout: layout.PageLayout | None = None
        self._current = 0
        self._settle = QTimer(self, singleShot=True, interval=SETTLE_MS)
        self._settle.timeout.connect(self._settle_zoom)
        self._request_timer = QTimer(self, singleShot=True, interval=0)
        self._request_timer.timeout.connect(self._request_tiles)
        self._scroll_anim = QVariantAnimation(self, duration=ANIMATION_MS)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_anim.valueChanged.connect(lambda v: self.verticalScrollBar().setValue(int(v)))
        self.indicator = ZoomIndicator(self.viewport())
        scheduler.tile_ready.connect(self._on_tile_ready)
        self._relayout()

    # --- public API ------------------------------------------------------------

    @property
    def current_page(self) -> int:
        return self._current

    def set_zoom(
        self, zoom: float, mode: ZoomMode = "", anchor: QPointF | None = None, osd: bool = True
    ) -> None:
        """Change zoom, keeping the document point under ``anchor`` (viewport px) fixed."""
        zoom = layout.clamp_zoom(zoom)
        self.zoom_mode = mode
        if abs(zoom - self.zoom) < 1e-4 and self.page_layout is not None:
            self.zoom_changed.emit(self.zoom, mode)
            return
        if anchor is None:
            anchor = QPointF(self.viewport().width() / 2, self.viewport().height() / 2)
        page, ax, ay = self._anchor(anchor)
        self.zoom = zoom
        self._relayout()
        sx, sy = self.page_layout.scene_point(page, ax, ay) if self.page_layout else (0.0, 0.0)
        self._scroll_scene_to(sx, sy, anchor)
        self._settle.start()
        if osd:
            self.indicator.show_zoom(zoom)
        self.zoom_changed.emit(zoom, mode)

    def apply_zoom_mode(self, mode: ZoomMode, osd: bool = True) -> None:
        """Fit width/page: keep the top edge in place and centre horizontally."""
        at_top = self.verticalScrollBar().value() == 0
        self.set_zoom(self._fit_zoom(mode), mode, anchor=QPointF(0, 0), osd=osd)
        if at_top:
            self.verticalScrollBar().setValue(0)
        bar = self.horizontalScrollBar()
        bar.setValue((bar.minimum() + bar.maximum()) // 2)

    def zoom_in(self) -> None:
        self.set_zoom(layout.zoom_in(self.zoom))

    def zoom_out(self) -> None:
        self.set_zoom(layout.zoom_out(self.zoom))

    def go_to_page(self, index: int, y: float | None = None) -> None:
        if self.page_layout is None:
            return
        index = max(0, min(index, self.doc.page_count - 1))
        slot = self.page_layout.slots[index]
        top = slot.y + y if y is not None else slot.y - self.page_layout.gap
        self._scroll_anim.stop()
        self._scroll_scene_to(None, top, QPointF(0, 0))
        self._update_current(force_page=index)

    def reveal(self, page: int, rect: tuple[float, float, float, float]) -> None:
        """Scroll so ``rect`` (page points) is visible, centring it if it isn't."""
        item = self.page_items[page]
        target = item.mapRectToScene(QRectF(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]))
        margin = 24 / self.zoom
        if (
            not self.visible_scene_rect()
            .adjusted(margin, margin, -margin, -margin)
            .contains(target)
        ):
            self._scroll_anim.stop()
            self.centerOn(target.center())
            # Settle it a third of the way down, where the current-page probe looks,
            # so the page field agrees with the page the target is on.
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() + round(self.viewport().height() * (0.5 - READING_LINE)))
        self._update_current()

    # --- layout ----------------------------------------------------------------

    def _fit_zoom(self, mode: ZoomMode) -> float:
        vp = self.viewport()
        if mode == "fit-page":
            info = self.doc.pages[self._current]
            return layout.fit_page_zoom(info.width, info.height, vp.width(), vp.height(), PAGE_GAP)
        # Median, not widest: one landscape page shouldn't shrink every portrait page.
        widths = sorted(p.width for p in self.doc.pages)
        return layout.fit_width_zoom(widths[len(widths) // 2], vp.width(), PAGE_GAP)

    def _relayout(self) -> None:
        sizes = [(p.width, p.height) for p in self.doc.pages]
        self.page_layout = layout.PageLayout(sizes, self.zoom, PAGE_GAP)
        for item, slot in zip(self.page_items, self.page_layout.slots, strict=True):
            item.setPos(slot.x, slot.y)
            item.set_view_zoom(self.zoom)
        self.setSceneRect(QRectF(0, 0, self.page_layout.width, self.page_layout.height))
        self.setTransform(QTransform.fromScale(self.zoom, self.zoom))
        if self.render_zoom == 0.0:
            self._settle_zoom()

    def _anchor(self, viewport_pos: QPointF) -> tuple[int, float, float]:
        if self.page_layout is None:
            return 0, 0.0, 0.0
        scene = self.mapToScene(viewport_pos.toPoint())
        return self.page_layout.anchor(scene.x(), scene.y())

    def _scroll_scene_to(self, sx: float | None, sy: float, viewport_pos: QPointF) -> None:
        """Scroll so scene point (sx, sy) lands at ``viewport_pos``. sx=None keeps x."""
        if sx is not None:
            h = self.horizontalScrollBar()
            h.setValue(round(sx * self.zoom - viewport_pos.x() - self._x_offset()))
        self.verticalScrollBar().setValue(round(sy * self.zoom - viewport_pos.y()))

    def _x_offset(self) -> float:
        """Horizontal centring margin Qt adds when the scene is narrower than the viewport."""
        if self.page_layout is None:
            return 0.0
        return max(0.0, (self.viewport().width() - self.page_layout.width * self.zoom) / 2)

    def _settle_zoom(self) -> None:
        previous = self.render_zoom
        self.render_zoom = self.zoom
        changed = previous and zoom_key(previous) != zoom_key(self.zoom)
        zooms = (previous, self.zoom) if changed else (self.zoom,)
        dpr = self.devicePixelRatioF()
        for item in self.page_items:
            item.render_zooms = zooms
            item.dpr = dpr
        self._request_tiles()
        self.viewport().update()

    # --- rendering requests ---------------------------------------------------------

    def visible_scene_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def _request_tiles(self) -> None:
        if self.page_layout is None or not self.render_zoom:
            return
        area = self.visible_scene_rect()
        visible = self.page_layout.visible_pages(area.top(), area.bottom())
        first, last = visible.start, visible.stop - 1
        n = self.doc.page_count
        prefetch = [
            *range(last + 1, min(n, last + 1 + PREFETCH_PAGES)),
            *reversed(range(max(0, first - PREFETCH_PAGES), first)),
        ]
        zoom, dpr = self.render_zoom, self.devicePixelRatioF()
        requests: list[RenderRequest] = []
        for index in [*visible, *prefetch]:
            item = self.page_items[index]
            local = item.mapFromScene(area).boundingRect()
            if index not in visible:  # prefetch the same horizontal band, full height
                local = QRectF(local.left(), 0, local.width(), item.info.height)
            for tx, ty, clip in tiles(item.info.width, item.info.height, zoom, dpr, local):
                key = tile_key(self.doc, index, zoom, dpr, tx, ty)
                requests.append(RenderRequest(key, self.doc, index, zoom, dpr, clip))
        self.scheduler.set_wanted(self.owner, requests, priority=0)

    def _on_tile_ready(self, key: object) -> None:
        if not (isinstance(key, tuple) and key[0] == self.doc.id and len(key) == 6):
            return
        page = key[1]
        if 0 <= page < len(self.page_items):
            self.page_items[page].update()

    def release(self) -> None:
        self.scheduler.forget(self.owner)
        self.scheduler.tile_ready.disconnect(self._on_tile_ready)

    # --- scrolling and current page -------------------------------------------------

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._update_current()
        self._request_timer.start()

    def _update_current(self, force_page: int | None = None) -> None:
        if self.page_layout is None:
            return
        if force_page is None:
            area = self.visible_scene_rect()
            force_page = self.page_layout.page_at(area.top() + area.height() * READING_LINE)
        if force_page != self._current:
            self._current = force_page
            self.current_page_changed.emit(force_page)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.zoom_mode:
            self.apply_zoom_mode(self.zoom_mode, osd=False)
        self.indicator.reposition()
        self._request_timer.start()

    # --- input -----------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = event.angleDelta().y() / 120
            if steps:
                self.set_zoom(self.zoom * 1.1**steps, anchor=event.position())
            event.accept()
            return
        if not event.pixelDelta().isNull() or not animations_enabled():
            super().wheelEvent(event)  # touchpads already scroll smoothly
            return
        delta = event.angleDelta()
        if delta.x() and not delta.y():
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        start = bar.value()
        running = self._scroll_anim.state() == QVariantAnimation.State.Running
        end = self._scroll_anim.endValue() if running else start
        target = int(end) - round(delta.y() / 120 * bar.singleStep() * 3)
        target = max(bar.minimum(), min(bar.maximum(), target))
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(start)
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()
        event.accept()

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.NativeGesture:
            assert isinstance(event, QNativeGestureEvent)
            if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self.set_zoom(self.zoom * (1 + event.value()), anchor=event.position())
                return True
        if event.type() == QEvent.Type.Gesture:
            gesture = event.gesture(Qt.GestureType.PinchGesture)  # type: ignore[attr-defined]
            if gesture is not None:
                center = self.viewport().mapFromGlobal(gesture.centerPoint().toPoint())
                self.set_zoom(self.zoom * gesture.scaleFactor(), anchor=QPointF(center))
                return True
        return super().viewportEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Home:
            self.go_to_page(0)
        elif key == Qt.Key.Key_End:
            self.go_to_page(self.doc.page_count - 1)
        else:
            super().keyPressEvent(event)
