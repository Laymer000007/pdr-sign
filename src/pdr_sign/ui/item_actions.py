"""Copy, cut, paste, duplicate and delete placed items; their right-click menu; and the
rubber band that selects several at once. One canvas each.

Paste goes where the pointer is when it's over a page (the group's top-left at the
pointer), otherwise 10 pt below-right of where the items were copied from. Each paste,
duplicate, delete or group move is one undo step.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QPoint, QRect
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMenu, QRubberBand

from pdr_sign.services import item_codec
from pdr_sign.services.stamps import OverlayItem
from pdr_sign.ui.overlay.base import OverlayGraphic
from pdr_sign.ui.overlay.text_item import TextGraphic

if TYPE_CHECKING:
    from PySide6.QtGui import QClipboard

    from pdr_sign.ui.canvas import Canvas

OFFSET = 10.0  # points: duplicate, or paste with the pointer off the pages
MAX_PASTED_IMAGE = 200.0  # points: the longer side of an image pasted from another app
PX_TO_PT = 72 / 96


def _clipboard() -> QClipboard:
    from pdr_sign.ui import canvas  # late: canvas imports this module; tests replace it

    return canvas.clipboard()


class ItemActions:
    def __init__(self, canvas: Canvas) -> None:
        self.canvas = canvas
        self.band: QRubberBand | None = None
        self._band_origin: QPoint | None = None
        self._band_adds = False

    # --- what's selected -------------------------------------------------------------

    def selected(self) -> list[OverlayGraphic]:
        """Selected items that are settled (not being typed into or still pending)."""
        layer = self.canvas.fill_layer
        if layer is None:
            return []
        return [
            g
            for g in layer.selected()
            if not (isinstance(g, TextGraphic) and (g.editing or g.pending))
        ]

    def _items(self) -> list[OverlayItem]:
        return [g.item.moved_to(g.scene_rect_in_page()) for g in self.selected()]

    # --- clipboard ----------------------------------------------------------------------

    def copy(self) -> bool:
        items = self._items()
        if not items:
            return False
        data = QMimeData()
        data.setData(item_codec.MIME, QByteArray(item_codec.encode(items)))
        words = [i.text for i in items if i.text]
        if words:  # other apps get the text
            data.setText("\n".join(words))
        _clipboard().setMimeData(data)
        return True

    def cut(self) -> bool:
        return self.copy() and self.delete("Cut")

    def delete(self, text: str = "Delete") -> bool:
        layer = self.canvas.fill_layer
        if layer is None or not layer.selected():
            return False
        model = layer.model
        with model.one_step(text):
            return layer.delete_selected()

    def duplicate(self) -> bool:
        items = self._items()
        if not items:
            return False
        page = items[0].page
        return self._add([replace(i, page=page) for i in items], page, OFFSET, OFFSET, "Duplicate")

    def can_paste(self) -> bool:
        data = _clipboard().mimeData()
        return data is not None and (
            data.hasFormat(item_codec.MIME) or data.hasImage() or bool(data.text().strip())
        )

    def paste(self, at: QPoint | None = None) -> bool:
        """Paste at viewport position ``at`` (default: the pointer, if over a page)."""
        data = _clipboard().mimeData()
        if data is None:
            return False
        target = self._page_at(at if at is not None else self.canvas.pointer)
        if data.hasFormat(item_codec.MIME):
            items = item_codec.decode(bytes(data.data(item_codec.MIME).data()))
        elif data.hasImage():
            items = self._from_image(data.imageData())
        elif data.text().strip():
            items = [self._from_text(data.text().strip())]
        else:
            items = []
        if not items:
            return False
        if target is not None:  # the group's top-left at the pointer
            page, x, y = target
            x0, y0, _, _ = item_codec.bounds(items)
            return self._add(items, page, x - x0, y - y0, "Paste")
        page = items[0].page if items[0].page < len(self.canvas.page_items) else -1
        if page < 0 or not (data.hasFormat(item_codec.MIME)):
            page = self.canvas.current_page
            info = self.canvas.page_items[page].info
            x0, y0, x1, y1 = item_codec.bounds(items)  # centre of the current page
            dx = (info.width - (x1 - x0)) / 2 - x0
            dy = (info.height - (y1 - y0)) / 2 - y0
            return self._add(items, page, dx, dy, "Paste")
        return self._add(items, page, OFFSET, OFFSET, "Paste")

    def _page_at(self, pos: QPoint | None) -> tuple[int, float, float] | None:
        if pos is None:
            return None
        hit = self.canvas._page_point(pos)
        if hit is None:
            return None
        page, local = hit
        if not self.canvas.page_items[page].page_rect().contains(local):
            return None
        return page, local.x(), local.y()

    def _from_image(self, value: object) -> list[OverlayItem]:
        image = value if isinstance(value, QImage) else QImage()
        if image.isNull():
            return []
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")  # type: ignore[call-overload]  # str works at runtime
        png = bytes(buffer.data().data())
        w, h = image.width() * PX_TO_PT, image.height() * PX_TO_PT
        scale = min(1.0, MAX_PASTED_IMAGE / max(w, h))
        return [OverlayItem("stamp", 0, (0, 0, w * scale, h * scale), image=png)]

    def _from_text(self, text: str) -> OverlayItem:
        layer = self.canvas.fill_layer
        size = layer.text_size if layer is not None else 12.0
        color = layer.text_color if layer is not None else "#000000"
        lines = text.splitlines() or [""]
        width = max(len(line) for line in lines) * size * 0.55 + 4
        height = len(lines) * size * 1.2 + 2
        return OverlayItem(
            item_codec.kind_of("text"),
            0,
            (0, 0, width, height),
            text=text,
            font_size=size,
            color=color,
        )

    def _add(self, items: list[OverlayItem], page: int, dx: float, dy: float, text: str) -> bool:
        layer = self.canvas.fill_layer
        if layer is None:
            return False
        info = self.canvas.page_items[page].info
        new = item_codec.placed(items, page, dx, dy, (info.width, info.height))
        layer.model.add_items(new, text)
        scene = self.canvas.scene()
        scene.clearSelection()
        for item in new:
            graphic = layer.graphics.get(item.id)
            if graphic is not None:
                graphic.setSelected(True)
        return True

    # --- right-click menu ------------------------------------------------------------------

    def menu(self, pos: QPoint) -> QMenu:
        """The menu for a right-click at viewport ``pos`` on a placed item."""
        from pdr_sign.ui import canvas_fill

        under = canvas_fill.overlay_at(self.canvas, pos)
        if under is not None and not under.isSelected():
            self.canvas.scene().clearSelection()
            under.setSelected(True)
        menu = QMenu(self.canvas)
        some = bool(self.selected())
        for label, keys, slot, enabled in (
            ("Copy", "Ctrl+C", self.copy, some),
            ("Cut", "Ctrl+X", self.cut, some),
            ("Paste", "Ctrl+V", lambda: self.paste(pos), self.can_paste()),
            ("Duplicate", "Ctrl+D", self.duplicate, some),
            ("Delete", "Del", self.delete, some),
        ):
            action = menu.addAction(label)
            action.setShortcut(keys)
            action.setEnabled(enabled)
            action.triggered.connect(lambda _=False, s=slot: s())
        return menu

    # --- rubber band -------------------------------------------------------------------

    def band_press(self, pos: QPoint, adds: bool) -> None:
        self._band_origin = pos
        self._band_adds = adds

    def band_move(self, pos: QPoint) -> bool:
        """Grow the band; False if no band was started."""
        if self._band_origin is None:
            return False
        if self.band is None:
            self.band = QRubberBand(QRubberBand.Shape.Rectangle, self.canvas.viewport())
        self.band.setGeometry(QRect(self._band_origin, pos).normalized())
        self.band.show()
        return True

    def band_release(self) -> bool:
        """Select the items the band touched; False if there was no band drawn."""
        origin, self._band_origin = self._band_origin, None
        band = self.band
        if origin is None or band is None or not band.isVisible():
            return False
        area = self.canvas.mapToScene(band.geometry()).boundingRect()
        band.hide()
        layer = self.canvas.fill_layer
        if layer is None:
            return True
        if not self._band_adds:
            self.canvas.scene().clearSelection()
        for graphic in layer.graphics.values():
            if graphic.scene() is not None and graphic.sceneBoundingRect().intersects(area):
                graphic.setSelected(True)
        return True

    def band_cancel(self) -> None:
        self._band_origin = None
        if self.band is not None:
            self.band.hide()

    @property
    def banding(self) -> bool:
        return self._band_origin is not None and self.band is not None and self.band.isVisible()
