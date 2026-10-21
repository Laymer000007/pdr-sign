from pathlib import Path

from pdr_sign.services import recent as r


def test_touch_orders_and_persists(tmp_path: Path) -> None:
    store = tmp_path / "recent.json"
    files = r.RecentFiles(store)
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    files.touch(a)
    files.touch(b, page=4, zoom="fit-page")
    files.touch(a, page=2)
    reloaded = r.RecentFiles(store)
    assert [Path(e.path).name for e in reloaded.entries] == ["a.pdf", "b.pdf"]
    entry_b = reloaded.get(b)
    assert entry_b is not None and (entry_b.page, entry_b.zoom) == (4, "fit-page")
    entry_a = reloaded.get(a)
    assert entry_a is not None and entry_a.page == 2


def test_capped_at_twelve_and_thumbnails_pruned(tmp_path: Path) -> None:
    files = r.RecentFiles(tmp_path / "recent.json")
    paths = [tmp_path / f"{n}.pdf" for n in range(14)]
    for p in paths:
        r.save_thumbnail(p, b"png")
        files.touch(p)
    assert len(files.entries) == r.MAX_RECENT
    assert not r.thumbnail_path(paths[0]).exists()
    assert r.thumbnail_path(paths[-1]).exists()


def test_existing_skips_missing_files(tmp_path: Path) -> None:
    files = r.RecentFiles(tmp_path / "recent.json")
    real = tmp_path / "real.pdf"
    real.write_bytes(b"%PDF")
    files.touch(real)
    files.touch(tmp_path / "gone.pdf")
    assert [e.name for e in files.existing()] == ["real.pdf"]


def test_corrupt_store(tmp_path: Path) -> None:
    store = tmp_path / "recent.json"
    store.write_text('[{"path": 1}, {"nope": 2}, "x"]')
    assert r.RecentFiles(store).entries[0].path == "1"
    store.write_text("{{{")
    assert r.RecentFiles(store).entries == []
