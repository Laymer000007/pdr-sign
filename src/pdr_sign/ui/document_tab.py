"""One open document: sidebar, find bar and canvas, wired together."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from pdr_sign.services import forms, stamps
from pdr_sign.services.document import Document
from pdr_sign.services.forms import FieldInfo
from pdr_sign.services.search import SearchHit
from pdr_sign.services.signatures import SignatureStore, as_kind
from pdr_sign.ui import signature_dialog, stamp_dialog
from pdr_sign.ui.banner import Banner
from pdr_sign.ui.canvas import Canvas
from pdr_sign.ui.fill_model import FillModel
from pdr_sign.ui.fill_sign_panel import FillSignPanel
from pdr_sign.ui.overlay.line_item import LineGraphic
from pdr_sign.ui.overlay.text_item import TextGraphic
from pdr_sign.ui.render_scheduler import RenderScheduler
from pdr_sign.ui.search_bar import SearchBar
from pdr_sign.ui.search_controller import SearchController
from pdr_sign.ui.sidebar import Sidebar
from pdr_sign.ui.signature_library import SignatureLibrary
from pdr_sign.ui.theme import (
    ANIMATION_MS,
    LIGHT,
    PANEL_WIDTH,
    SIDEBAR_WIDTH,
    Tokens,
    animations_enabled,
)

RESULTS_REFRESH_MS = 120  # coalesce streaming results before rebuilding the list


class DocumentTab(QWidget):
    external_link = Signal(str)
    dirty_changed = Signal(bool)
    fill_done = Signal()
    flatten_requested = Signal()

    def __init__(
        self,
        doc: Document,
        scheduler: RenderScheduler,
        parent: QWidget | None = None,
        library: SignatureLibrary | None = None,
    ) -> None:
        super().__init__(parent)
        self.doc = doc
        self.library = library or SignatureLibrary(SignatureStore())
        self._tokens: Tokens = LIGHT
        # Items PDR saved earlier come back as editable overlays. Take them off the
        # in-memory pages *before* the canvas exists: it starts rendering tiles at once,
        # and a tile rendered with them still on the page would draw each item twice.
        reopened = stamps.read_overlays(doc, remove=True)
        self.view = Canvas(doc, scheduler, self)
        self.search_bar = SearchBar(self)
        self.search = SearchController(doc, self)
        self.model = FillModel(forms.list_fields(doc), self)
        self.view.attach_fill(self.model)
        self.model.load(reopened)
        self.signed = forms.is_signed(self.model.fields)
        self.xfa_banner = Banner(
            "This form uses XFA and can't be filled here. You can still read, sign and print it.",
            self,
        )
        self.xfa_banner.setVisible(forms.has_xfa(doc))
        self.panel = FillSignPanel(self.model.fields, self)
        self.panel.setMaximumWidth(0)
        self.panel.hide()
        self.panel_visible = False
        self.panel_divider = QFrame()
        self.panel_divider.setObjectName("Divider")
        self.panel_divider.setFixedWidth(1)
        self.panel_divider.hide()
        self.sidebar = Sidebar(doc, scheduler)
        self.sidebar.setMaximumWidth(0)
        self.sidebar.setMinimumWidth(0)
        self.sidebar_visible = False

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedWidth(1)
        self.divider = divider
        divider.hide()

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.sidebar)
        row.addWidget(divider)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.xfa_banner)
        column.addWidget(self.search_bar)
        column.addWidget(self.view, 1)
        row.addLayout(column, 1)
        row.addWidget(self.panel_divider)
        row.addWidget(self.panel)

        self._slide = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        self._slide.setDuration(ANIMATION_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.finished.connect(self._on_slide_finished)

        self.sidebar.thumbnails.page_activated.connect(self.view.go_to_page)
        self.sidebar.outline.destination_activated.connect(self.view.go_to_page)
        self.view.current_page_changed.connect(self.sidebar.thumbnails.set_current)
        self.view.external_link.connect(self.external_link)

        self._results_timer = QTimer(self, singleShot=True, interval=RESULTS_REFRESH_MS)
        self._results_timer.timeout.connect(self._refresh_results)
        self.search_bar.query_changed.connect(self._start_search)
        self.search_bar.next_requested.connect(lambda: self.search.step(1))
        self.search_bar.previous_requested.connect(lambda: self.search.step(-1))
        self.search_bar.closed.connect(self._on_search_closed)
        self.search.results_changed.connect(lambda: self._results_timer.start())
        self.search.finished.connect(self._refresh_results)
        self.search.current_changed.connect(self._on_current_hit)
        self.sidebar.search.hit_activated.connect(self.search.set_current)

        self._panel_slide = QPropertyAnimation(self.panel, b"maximumWidth", self)
        self._panel_slide.setDuration(ANIMATION_MS)
        self._panel_slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._panel_slide.finished.connect(self._on_panel_slide_finished)
        layer = self.view.fill_layer
        assert layer is not None
        self.panel.tool_selected.connect(layer.set_tool)
        layer.tool_changed.connect(self.panel.set_tool)
        self.panel.style_changed.connect(layer.apply_style)
        self.panel.field_activated.connect(self.focus_field)
        self.panel.done.connect(self.fill_done)
        self.panel.flatten_requested.connect(self.flatten_requested)
        self.panel.sign_requested.connect(self.sign)
        for strip in self.panel.saved.values():
            strip.chosen.connect(self._arm_saved)
            strip.new_requested.connect(self.create_signature)
            strip.delete_requested.connect(lambda k, i: self.library.remove(as_kind(k), i))
        self.library.changed.connect(self._refresh_saved)
        controls = self.panel.stamp_controls
        controls.rotate_requested.connect(layer.rotate_stamps)
        controls.opacity_changed.connect(layer.set_stamp_opacity)
        self.model.item_changed.connect(self._sync_stamp_controls)
        if self.view.field_layer is not None:
            self.view.field_layer.on_sign_field = self.sign_field
        self._refresh_saved()
        self.panel.set_values(self.model.values)
        self.model.field_changed.connect(lambda *_: self.panel.set_values(self.model.values))
        self.model.dirty_changed.connect(self.dirty_changed)
        self.view.scene().selectionChanged.connect(self._sync_style_from_selection)

    # --- Fill & Sign -------------------------------------------------------------

    def set_panel_visible(self, visible: bool, animate: bool = True) -> None:
        """Slide the Fill & Sign panel in or out. Only MainWindow.set_fill_mode calls
        this, so the app-wide fill mode is the single source of truth."""
        self.panel_visible = visible
        target = PANEL_WIDTH if visible else 0
        layer = self.view.fill_layer
        if not visible and layer is not None:
            layer.set_tool("")
        self._panel_slide.stop()
        if visible:
            self.panel.show()
            self.panel_divider.show()
        if animate and animations_enabled() and self.isVisible():
            self._panel_slide.setStartValue(self.panel.maximumWidth())
            self._panel_slide.setEndValue(target)
            self._panel_slide.start()
        else:
            self.panel.setMaximumWidth(target)
            self._on_panel_slide_finished()

    def _on_panel_slide_finished(self) -> None:
        # Hidden, not just zero-width: keyboard focus can't wander into it.
        self.panel.setVisible(self.panel_visible)
        self.panel_divider.setVisible(self.panel_visible)

    # --- signatures -------------------------------------------------------------------

    def sign(self, kind: str) -> None:
        """The Signature/Initials tool: place the latest one, or create the first."""
        latest = self.library.latest(as_kind(kind))
        if latest is None:
            self.create_signature(kind)
        else:
            self._arm(kind, latest.png)

    def sign_field(self, field: FieldInfo) -> None:
        """Clicked an empty signature field: sign into it (creating a signature if needed)."""
        latest = self.library.latest("signature")
        png = latest.png if latest else self._ask("signature")
        if png is not None and self.view.fill_layer is not None:
            self.view.fill_layer.sign_field(field, png)

    def _ask(self, kind: str) -> bytes | None:
        if kind == "stamp":
            answer = stamp_dialog.ask_stamp(self._tokens, self)
        else:
            answer = signature_dialog.ask_signature(as_kind(kind), self._tokens, self)
        if answer is None:
            return None
        png, remember = answer
        self.library.add(as_kind(kind), png, remember)
        return png

    def create_signature(self, kind: str) -> None:
        png = self._ask(kind)
        if png is not None:
            self._arm(kind, png)

    def _arm_saved(self, kind: str, item_id: str) -> None:
        item = next((i for i in self.library.items(as_kind(kind)) if i.id == item_id), None)
        if item is not None:
            self._arm(kind, item.png)

    def _arm(self, kind: str, png: bytes) -> None:
        layer = self.view.fill_layer
        if layer is not None:
            layer.arm_image(kind, png)

    def _refresh_saved(self) -> None:
        for kind, strip in self.panel.saved.items():
            strip.set_items(self.library.items(as_kind(kind)))

    def set_default_ink(self, color: str) -> None:
        layer = self.view.fill_layer
        if layer is not None:
            layer.text_color = color
            self.panel.set_style(layer.text_size, color)

    def focus_field(self, name: str) -> None:
        if self.view.field_layer is not None:
            self.view.field_layer.focus(name)

    def _sync_style_from_selection(self) -> None:
        layer = self.view.fill_layer
        if layer is None:
            return
        self._sync_stamp_controls()
        for graphic in layer.selected():
            if isinstance(graphic, TextGraphic | LineGraphic):
                self.panel.set_style(graphic.item.font_size, graphic.item.color)
                return

    def _sync_stamp_controls(self, *_: object) -> None:
        """Show the Stamp controls while a stamp is selected, with its current state."""
        layer = self.view.fill_layer
        stamps = layer.selected_stamps() if layer is not None else []
        self.panel.stamp_controls.setVisible(bool(stamps))
        if stamps:
            item = stamps[0].item
            self.panel.stamp_controls.show_stamp(item.rotation, item.opacity)

    # --- search ------------------------------------------------------------------

    def open_search(self) -> None:
        self.search_bar.open_bar()
        if self.sidebar_visible:
            self.sidebar.tabs.setCurrentWidget(self.sidebar.search)

    def _start_search(self, query: str) -> None:
        self.search.start(query, self.view.current_page)
        if query.strip() and self.sidebar_visible:
            self.sidebar.tabs.setCurrentWidget(self.sidebar.search)

    def _refresh_results(self) -> None:
        self._results_timer.stop()
        hits = self.search.hits
        self.view.set_search_hits(hits)
        self.sidebar.search.set_hits(hits, self.search.query, self.search.running)
        self.sidebar.search.set_current(self.search.current_index)
        self._update_search_status()

    def _on_current_hit(self, hit: SearchHit | None) -> None:
        self.view.set_current_hit(hit)
        self.sidebar.search.set_current(self.search.current_index)
        self._update_search_status()

    def _update_search_status(self) -> None:
        s = self.search
        self.search_bar.set_status(s.current_index, len(s.hits), s.running, s.capped)

    def _on_search_closed(self) -> None:
        self.search.clear()
        self.view.setFocus()

    def set_tokens(self, t: Tokens) -> None:
        self._tokens = t
        self.search_bar.set_tokens(t)
        self.panel.set_tokens(t)
        self.panel.set_values(self.model.values)
        self.view.viewport().update()

    def set_sidebar_visible(self, visible: bool, animate: bool = True) -> None:
        self.sidebar_visible = visible
        target = SIDEBAR_WIDTH if visible else 0
        self._slide.stop()
        self.sidebar.setMinimumWidth(0)
        if visible:
            self.divider.show()
        if animate and animations_enabled() and self.isVisible():
            self._slide.setStartValue(self.sidebar.maximumWidth())
            self._slide.setEndValue(target)
            self._slide.start()
        else:
            self.sidebar.setMaximumWidth(target)
            self._slide.setEndValue(target)
            self._on_slide_finished()

    def _on_slide_finished(self) -> None:
        open_ = self.sidebar.maximumWidth() > 0
        self.divider.setVisible(open_)
        if open_:
            self.sidebar.setMinimumWidth(SIDEBAR_WIDTH)
            self.sidebar.thumbnails.request_visible()

    def close_document(self) -> None:
        self.search.cancel()
        self.view.release()
        self.sidebar.thumbnails.release()
        self.view.scheduler.drop_document(self.doc)
        self.doc.close()
