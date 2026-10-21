"""Size-bounded LRU cache for rendered tiles. Qt-free and generic over the value type."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable

DEFAULT_BUDGET = 300 * 1024 * 1024  # bytes


class RenderCache[V]:
    """LRU keyed by any hashable (the UI uses ``(doc, page, zoom, dpr, tile)``).

    Each entry carries its own byte size; the least recently used entries are evicted
    once the total exceeds ``budget``.
    """

    def __init__(self, budget: int = DEFAULT_BUDGET) -> None:
        self.budget = budget
        self._items: OrderedDict[Hashable, tuple[V, int]] = OrderedDict()
        self._size = 0

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: Hashable) -> bool:
        return key in self._items

    @property
    def size(self) -> int:
        return self._size

    def get(self, key: Hashable) -> V | None:
        item = self._items.get(key)
        if item is None:
            return None
        self._items.move_to_end(key)
        return item[0]

    def put(self, key: Hashable, value: V, size: int) -> None:
        old = self._items.pop(key, None)
        if old is not None:
            self._size -= old[1]
        self._items[key] = (value, size)
        self._size += size
        while self._size > self.budget and len(self._items) > 1:
            _, (_, evicted) = self._items.popitem(last=False)
            self._size -= evicted

    def discard_where(self, predicate: Callable[[Hashable], bool]) -> None:
        """Drop every entry whose key satisfies ``predicate(key)``."""
        for key in [k for k in self._items if predicate(k)]:
            _, size = self._items.pop(key)
            self._size -= size

    def clear(self) -> None:
        self._items.clear()
        self._size = 0
