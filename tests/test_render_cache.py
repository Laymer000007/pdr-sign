from pdr_sign.services.render_cache import RenderCache


def test_lru_evicts_oldest_by_size() -> None:
    cache: RenderCache[str] = RenderCache(budget=100)
    cache.put("a", "A", 40)
    cache.put("b", "B", 40)
    assert cache.get("a") == "A"  # "a" is now most recent
    cache.put("c", "C", 40)
    assert "b" not in cache
    assert "a" in cache and "c" in cache
    assert cache.size == 80


def test_replacing_key_updates_size() -> None:
    cache: RenderCache[str] = RenderCache(budget=100)
    cache.put("a", "A", 60)
    cache.put("a", "A2", 10)
    assert cache.size == 10 and cache.get("a") == "A2"


def test_oversized_item_is_kept_alone() -> None:
    cache: RenderCache[str] = RenderCache(budget=10)
    cache.put("a", "A", 5)
    cache.put("big", "B", 50)
    assert len(cache) == 1 and "big" in cache


def test_discard_where() -> None:
    cache: RenderCache[int] = RenderCache()
    for doc in (1, 2):
        for page in range(3):
            cache.put((doc, page), page, 1)
    cache.discard_where(lambda k: isinstance(k, tuple) and k[0] == 1)
    assert len(cache) == 3 and cache.size == 3
    cache.clear()
    assert len(cache) == 0 and cache.size == 0
