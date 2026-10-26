"""Hand-offs to the desktop: show a file in the file manager."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def show_in_folder(path: Path) -> None:
    """Open the file manager with ``path`` selected (freedesktop FileManager1), or
    just open its folder when that interface isn't there. A strict snap may not call
    FileManager1, so there the folder opens through the desktop portal."""
    sender = None if "SNAP_NAME" in os.environ else shutil.which("dbus-send")
    if sender is not None:
        try:
            subprocess.run(
                [
                    sender,
                    "--session",
                    "--dest=org.freedesktop.FileManager1",
                    "--type=method_call",
                    "--print-reply",  # wait, so a refused or missing service falls back
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowItems",
                    f"array:string:{path.resolve().as_uri()}",
                    "string:",
                ],
                check=True,
                timeout=3,
                capture_output=True,
            )
            return
        except (OSError, subprocess.SubprocessError):
            pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


def open_url(url: str) -> bool:
    """Hand a web or mailto: link to the desktop (the OpenURI portal inside a snap).
    False when nothing could take it, so callers can offer a Copy fallback."""
    return QDesktopServices.openUrl(QUrl(url))
