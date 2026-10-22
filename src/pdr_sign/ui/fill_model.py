"""In-memory Fill & Sign state for one document, with undo/redo.

Overlay items and form-field values live here until save; nothing touches the PDF
before then. Every user change goes through ``QUndoStack`` commands.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from pdr_sign.services.forms import FieldInfo, FieldValue, field_values
from pdr_sign.services.stamps import OverlayItem

MERGE_ITEM = 1
MERGE_FIELD = 2


class _Command(QUndoCommand):
    def __init__(
        self,
        text: str,
        do: Callable[[], None],
        undo: Callable[[], None],
        merge_id: int = -1,
        merge_key: object = None,
    ) -> None:
        super().__init__(text)
        self._do, self._undo = do, undo
        self._merge_id, self.merge_key = merge_id, merge_key

    def redo(self) -> None:
        self._do()

    def undo(self) -> None:
        self._undo()

    def id(self) -> int:
        return self._merge_id

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, _Command) or other.merge_key != self.merge_key:
            return False
        if self.merge_key is None:
            return False
        self._do = other._do  # keep our undo, take their redo
        return True


class FillModel(QObject):
    item_added = Signal(object)  # OverlayItem
    item_removed = Signal(str)  # id
    item_changed = Signal(object)  # OverlayItem
    field_changed = Signal(str, object)  # name, value
    dirty_changed = Signal(bool)

    def __init__(self, fields: list[FieldInfo], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.fields = fields
        self.items: dict[str, OverlayItem] = {}
        self.values: dict[str, FieldValue] = field_values(fields)
        self.initial_values = dict(self.values)
        self.undo_stack = QUndoStack(self)
        # A bound slot, not a lambda: Qt drops it when the model is destroyed, whereas a
        # lambda would fire on the dying stack and hit a deleted signal source.
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)

    def _on_clean_changed(self, clean: bool) -> None:
        self.dirty_changed.emit(not clean)

    @property
    def dirty(self) -> bool:
        return not self.undo_stack.isClean()

    def load(self, items: list[OverlayItem]) -> None:
        """Items reopened from the file: the starting state, not undoable changes."""
        for item in items:
            self._add(item)
        self.undo_stack.clear()
        self.undo_stack.setClean()

    def save_request(self) -> tuple[dict[str, FieldValue], list[OverlayItem]]:
        """What Save writes: changed field values and every current item."""
        return self.changed_values(), list(self.items.values())

    def changed_values(self) -> dict[str, FieldValue]:
        return {k: v for k, v in self.values.items() if self.initial_values.get(k) != v}

    # --- overlay items ----------------------------------------------------------

    def add_item(self, item: OverlayItem) -> None:
        self.undo_stack.push(
            _Command(f"Add {item.kind}", lambda: self._add(item), lambda: self._remove(item.id))
        )

    def remove_item(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is not None:
            self.undo_stack.push(
                _Command(
                    f"Delete {item.kind}", lambda: self._remove(item_id), lambda: self._add(item)
                )
            )

    def update_item(self, new: OverlayItem, merge: bool = False) -> None:
        """Replace an item (move, resize, edit). ``merge`` folds repeats into one step."""
        old = self.items.get(new.id)
        if old is None or old == new:
            return
        self.undo_stack.push(
            _Command(
                f"Edit {new.kind}",
                lambda: self._replace(new),
                lambda: self._replace(old),
                MERGE_ITEM if merge else -1,
                new.id if merge else None,
            )
        )

    def _add(self, item: OverlayItem) -> None:
        self.items[item.id] = item
        self.item_added.emit(item)

    def _remove(self, item_id: str) -> None:
        if self.items.pop(item_id, None) is not None:
            self.item_removed.emit(item_id)

    def _replace(self, item: OverlayItem) -> None:
        self.items[item.id] = item
        self.item_changed.emit(item)

    # --- form fields ----------------------------------------------------------------

    def set_field_value(self, name: str, value: FieldValue, merge: bool = False) -> None:
        old = self.values.get(name)
        if old == value:
            return
        self.undo_stack.push(
            _Command(
                f"Fill {name}",
                lambda: self._set_value(name, value),
                lambda: self._set_value(name, old if old is not None else ""),
                MERGE_FIELD if merge else -1,
                name if merge else None,
            )
        )

    def _set_value(self, name: str, value: FieldValue) -> None:
        self.values[name] = value
        self.field_changed.emit(name, value)
