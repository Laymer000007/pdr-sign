"""Keeps overlay graphics in step with the FillModel, and places new items with tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QDate, QLocale, QObject, QPointF, Signal
from PySide6.QtGui import QPixmap

from pdr_sign.services.forms import FieldInfo
from pdr_sign.services.stamps import DEFAULT_FONT_SIZE, MARK_KINDS, TEXT_COLORS, OverlayItem
from pdr_sign.ui.fill_model import FillModel
from pdr_sign.ui.overlay.base import OverlayGraphic
from pdr_sign.ui.overlay.check_item import MARK_SIZE, MarkGraphic
from pdr_sign.ui.overlay.line_item import MIN_LENGTH, LineGraphic, default_end
from pdr_sign.ui.overlay.signature_item import SignatureGraphic
from pdr_sign.ui.overlay.text_item import TextGraphic

if TYPE_CHECKING:
    from pdr_sign.ui.page_item import PageItem

TOOLS = ("text", "check", "cross", "dot", "line", "date", "initials", "signature")
IMAGE_TOOLS = ("signature", "initials")
DEFAULT_WIDTH = {"signature": 150.0, "initials": 56.0}  # points, before snapping
SNAP_DISTANCE = 12.0  # points: how near a signature field counts as "in" it
FIELD_INSET = 2.0
STICKY_TOOLS = (*MARK_KINDS, "line")  # stay active for repeated use


def today_text() -> str:
    """Today's date in the user's short locale format (editable afterwards)."""
    return QLocale.system().toString(QDate.currentDate(), QLocale.FormatType.ShortFormat)


class FillLayer(QObject):
    tool_changed = Signal(str)  # "" = no tool (select / read)

    def __init__(self, model: FillModel, pages: list[PageItem]) -> None:
        super().__init__()
        self.model = model
        self.pages = pages
        self.tool = ""
        self.text_size = DEFAULT_FONT_SIZE
        self.text_color = TEXT_COLORS["black"]
        self.graphics: dict[str, OverlayGraphic] = {}
        self.draft: LineGraphic | None = None  # a line being drawn by dragging
        self.armed_image: bytes | None = None  # what the signature/initials tool places
        self.sign_fields = [f for f in model.fields if f.kind == "signature" and not f.is_signed]
        model.item_added.connect(self._on_added)
        model.item_removed.connect(self._on_removed)
        model.item_changed.connect(self._on_changed)
        for item in model.items.values():
            self._on_added(item)

    # --- tools ------------------------------------------------------------------

    def arm_image(self, kind: str, png: bytes) -> None:
        """Make the signature or initials tool place ``png``."""
        self.armed_image = png
        self.tool = ""  # force tool_changed even if the same tool was active
        self.set_tool(kind)

    def set_tool(self, tool: str) -> None:
        tool = tool if tool in TOOLS else ""
        if tool in IMAGE_TOOLS and self.armed_image is None:
            tool = ""
        if tool != self.tool:
            self.tool = tool
            self.tool_changed.emit(tool)

    def place(self, page: int, point: QPointF) -> OverlayGraphic | None:
        """Use the active tool at ``point`` (page points)."""
        tool = self.tool
        if not tool:
            return None
        info = self.pages[page].info
        if tool in IMAGE_TOOLS:
            return self._place_image(tool, page, point)
        if tool in MARK_KINDS:
            half = MARK_SIZE / 2
            x = min(max(point.x() - half, 0), info.width - MARK_SIZE)
            y = min(max(point.y() - half, 0), info.height - MARK_SIZE)
            item = OverlayItem(
                tool,
                page,
                (x, y, x + MARK_SIZE, y + MARK_SIZE),
                font_size=MARK_SIZE,
                color=self.text_color,
            )
            self.model.add_item(item)
            graphic = self.graphics[item.id]
        else:
            size = self.text_size
            x = min(max(point.x(), 0), info.width - size * 2)
            y = min(max(point.y() - size * 0.7, 0), info.height - size * 1.4)
            text = today_text() if tool == "date" else ""
            item = OverlayItem(
                tool,  # type: ignore[arg-type]
                page,
                (x, y, x + size * 2, y + size * 1.4),
                text=text,
                font_size=size,
                color=self.text_color,
            )
            if tool == "date":
                self.model.add_item(item)
                graphic = self.graphics[item.id]
            else:
                text_graphic = TextGraphic(item, self.model, self.pages[page], pending=True)
                self.graphics[item.id] = text_graphic
                text_graphic.start_editing()
                graphic = text_graphic
            self.set_tool("")  # text and date are one-shot
        scene = graphic.scene()
        if scene is not None:
            scene.clearSelection()
        graphic.setSelected(True)
        return graphic

    # --- signatures -----------------------------------------------------------------

    def _place_image(self, kind: str, page: int, point: QPointF) -> OverlayGraphic | None:
        png = self.armed_image
        if png is None:
            return None
        pixmap = QPixmap()
        pixmap.loadFromData(png, "PNG")
        aspect = pixmap.height() / pixmap.width() if pixmap.width() else 0.3
        width = DEFAULT_WIDTH.get(kind, 150.0)
        height = width * aspect
        info = self.pages[page].info
        x = min(max(point.x() - width / 2, 0), info.width - width)
        y = min(max(point.y() - height / 2, 0), info.height - height)
        rect = (x, y, x + width, y + height)
        rect = self.snap_to_field(page, rect, point) or rect
        item = OverlayItem(kind, page, rect, image=png)  # type: ignore[arg-type]
        self.model.add_item(item)
        self.set_tool("")  # one-shot
        graphic = self.graphics[item.id]
        if graphic.scene() is not None:
            graphic.scene().clearSelection()
        graphic.setSelected(True)
        return graphic

    def sign_field(self, field: FieldInfo, png: bytes) -> OverlayGraphic | None:
        """Place ``png`` fitted into a signature field."""
        self.armed_image = png
        x0, y0, x1, y1 = field.rect
        return self._place_image("signature", field.page, QPointF((x0 + x1) / 2, (y0 + y1) / 2))

    def snap_to_field(
        self, page: int, rect: tuple[float, float, float, float], point: QPointF | None = None
    ) -> tuple[float, float, float, float] | None:
        """If the click (or the item's centre) is in or near an empty signature field,
        the image fitted inside that field (aspect kept, centred)."""
        cx = point.x() if point is not None else (rect[0] + rect[2]) / 2
        cy = point.y() if point is not None else (rect[1] + rect[3]) / 2
        for field in self.sign_fields:
            if field.page != page:
                continue
            x0, y0, x1, y1 = field.rect
            d = SNAP_DISTANCE
            if not (x0 - d <= cx <= x1 + d and y0 - d <= cy <= y1 + d):
                continue
            box_w, box_h = x1 - x0 - 2 * FIELD_INSET, y1 - y0 - 2 * FIELD_INSET
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            scale = min(box_w / w, box_h / h)
            w, h = w * scale, h * scale
            left, top = (x0 + x1 - w) / 2, (y0 + y1 - h) / 2
            return (left, top, left + w, top + h)
        return None

    # --- drawing lines ---------------------------------------------------------------

    def begin_line(self, page: int, point: QPointF) -> LineGraphic:
        """Start a line at ``point``; ``drag_line`` stretches it, ``end_line`` commits."""
        item = OverlayItem(
            "line",
            page,
            (point.x(), point.y(), point.x(), point.y()),
            font_size=self.text_size,
            color=self.text_color,
        )
        self.draft = LineGraphic(item, self.model, self.pages[page], pending=True)
        self.graphics[item.id] = self.draft
        return self.draft

    def drag_line(self, point: QPointF, any_angle: bool) -> None:
        if self.draft is None:
            return
        start, _ = self.draft.endpoints()
        self.draft.set_endpoints(start, self.draft.constrain(start, point, any_angle))

    def end_line(self) -> LineGraphic | None:
        draft, self.draft = self.draft, None
        if draft is None:
            return None
        start, end = draft.endpoints()
        if draft.length() < MIN_LENGTH:  # a click, not a drag
            end = default_end(start, self.pages[draft.item.page].info.width)
            draft.set_endpoints(start, end)
        draft.pending = False
        draft.item = draft.item.moved_to(draft.scene_rect_in_page())
        self.model.add_item(draft.item)
        scene = draft.scene()
        if scene is not None:
            scene.clearSelection()
        draft.setSelected(True)
        return draft

    # --- selection ------------------------------------------------------------------

    def selected(self) -> list[OverlayGraphic]:
        return [g for g in self.graphics.values() if g.isSelected()]

    def delete_selected(self) -> bool:
        doomed = [g for g in self.selected() if not (isinstance(g, TextGraphic) and g.editing)]
        for graphic in doomed:
            if isinstance(graphic, TextGraphic) and graphic.pending:
                graphic.scene_remove()
                self.graphics.pop(graphic.item.id, None)
            else:
                self.model.remove_item(graphic.item.id)
        return bool(doomed)

    def apply_style(self, font_size: float, color: str) -> None:
        """New defaults from the panel; also restyles selected text items."""
        self.text_size, self.text_color = font_size, color
        for graphic in self.selected():
            if isinstance(graphic, TextGraphic):
                graphic.set_style(font_size, color)
            elif isinstance(graphic, LineGraphic):
                graphic.restyle(font_size, color)

    # --- model → graphics ---------------------------------------------------------------

    def _on_added(self, item: OverlayItem) -> None:
        if item.id in self.graphics:
            return  # a pending text box that just got its first text
        page = self.pages[item.page]
        graphic: OverlayGraphic
        if item.kind == "line":
            graphic = LineGraphic(item, self.model, page)
        elif item.is_image:
            graphic = SignatureGraphic(item, self.model, page, snap=self.snap_to_field)
        elif item.is_mark:
            graphic = MarkGraphic(item, self.model, page)
        else:
            graphic = TextGraphic(item, self.model, page)
        self.graphics[item.id] = graphic

    def _on_removed(self, item_id: str) -> None:
        graphic = self.graphics.pop(item_id, None)
        if graphic is not None and graphic.scene() is not None:
            graphic.scene().removeItem(graphic)

    def _on_changed(self, item: OverlayItem) -> None:
        graphic = self.graphics.get(item.id)
        if graphic is not None and graphic.item != item:
            graphic.apply(item)
