"""Recently opened files, with last page/zoom and a page-1 thumbnail. Qt-free."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pdr_sign.services.settings import data_dir

MAX_RECENT = 12


@dataclass
class RecentEntry:
    path: str
    page: int = 0
    zoom: str = ""  # "" = default zoom; otherwise "fit-width", "fit-page" or e.g. "1.25"
    opened_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return Path(self.path).name


def recent_path() -> Path:
    return data_dir() / "recent.json"


def thumbnails_dir() -> Path:
    return data_dir() / "thumbnails"


def thumbnail_path(path: str | Path) -> Path:
    digest = hashlib.sha1(str(Path(path).resolve()).encode(), usedforsecurity=False).hexdigest()
    return thumbnails_dir() / f"{digest}.png"


class RecentFiles:
    def __init__(self, store: Path | None = None) -> None:
        self.store = store or recent_path()
        self.entries: list[RecentEntry] = self._load()

    def _load(self) -> list[RecentEntry]:
        try:
            raw = json.loads(self.store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        entries = []
        for item in raw if isinstance(raw, list) else []:
            try:
                entries.append(
                    RecentEntry(
                        path=str(item["path"]),
                        page=int(item.get("page", 0)),
                        zoom=str(item.get("zoom", "")),
                        opened_at=float(item.get("opened_at", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return entries[:MAX_RECENT]

    def get(self, path: str | Path) -> RecentEntry | None:
        key = str(Path(path).resolve())
        return next((e for e in self.entries if e.path == key), None)

    def existing(self) -> list[RecentEntry]:
        """Entries whose file still exists, most recent first."""
        return [e for e in self.entries if Path(e.path).is_file()]

    def touch(self, path: str | Path, page: int | None = None, zoom: str | None = None) -> None:
        """Move ``path`` to the front, updating its position if given."""
        key = str(Path(path).resolve())
        entry = self.get(key) or RecentEntry(key)
        self.entries = [e for e in self.entries if e.path != key]
        if page is not None:
            entry.page = page
        if zoom is not None:
            entry.zoom = zoom
        entry.opened_at = time.time()
        self.entries.insert(0, entry)
        for dropped in self.entries[MAX_RECENT:]:
            thumbnail_path(dropped.path).unlink(missing_ok=True)
        del self.entries[MAX_RECENT:]
        self.save()

    def remove(self, path: str | Path) -> None:
        key = str(Path(path).resolve())
        self.entries = [e for e in self.entries if e.path != key]
        thumbnail_path(key).unlink(missing_ok=True)
        self.save()

    def save(self) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.store.parent, prefix=".recent-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump([asdict(e) for e in self.entries], fh, indent=2)
            os.replace(tmp, self.store)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def save_thumbnail(path: str | Path, png: bytes) -> Path:
    target = thumbnail_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return target
