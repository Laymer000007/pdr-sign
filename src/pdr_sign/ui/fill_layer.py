"""Keeps overlay graphics in step with the FillModel, and places new items with tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QDate, QLocale, QObject, QPointF, Signal

from pdr_sign.services.stamps import DEFAULT_FONT_SIZE, MARK_KINDS, TEXT_COLORS, OverlayItem
from pdr_sign.ui.fill_model import FillModel
from pdr_sign.ui.overlay.base import OverlayGraphic
from pdr_sign.ui.overlay.check_item import MARK_SIZE, MarkGraphic
from pdr_sign.ui.overlay.line_item import MIN_LENGTH, LineGraphic, default_end
from pdr_sign.ui.overlay.text_item import TextGraphic

if TYPE_CHECKING:
    from pdr_sign.ui.page_item import PageItem

TOOLS = ("text", "check", "cross", "dot", "line", "date")
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
        model.item_added.connect(self._on_added)
        model.item_removed.connect(self._on_removed)
        model.item_changed.connect(self._on_changed)
        for item in model.items.values():
            self._on_added(item)

    # --- tools ------------------------------------------------------------------

    def set_tool(self, tool: str) -> None:
        tool = tool if tool in TOOLS else ""
        if tool != self.tool:
            self.tool = tool
            self.tool_changed.emit(tool)

    def place(self, page: int, point: QPointF) -> OverlayGraphic | None:
        """Use the active tool at ``point`` (page points)."""
        tool = self.tool
        if not tool:
            return None
        info = self.pages[page].info
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
