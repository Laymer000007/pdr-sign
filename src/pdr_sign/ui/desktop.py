"""Hand-offs to the desktop: show a file in the file manager."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def show_in_folder(path: Path) -> None:
    """Open the file manager with ``path`` selected (freedesktop FileManager1), or
    just open its folder when that interface isn't there."""
    sender = shutil.which("dbus-send")
    if sender is not None:
        try:
            subprocess.run(
                [
                    sender,
                    "--session",
                    "--dest=org.freedesktop.FileManager1",
                    "--type=method_call",
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
