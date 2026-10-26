"""Small pure helpers for the main window: its title, zoom settings, dropped files."""

from __future__ import annotations

from PySide6.QtCore import QUrl

from pdr_sign import APP_NAME


def window_title(document_name: str | None = None, dirty: bool = False) -> str:
    """ "<name> – PDR Sign" (with "• " while unsaved), or "PDR Sign" alone. Ending in the
    application display name stops Qt from appending it a second time."""
    if document_name is None:
        return APP_NAME
    return f"{'• ' if dirty else ''}{document_name} – {APP_NAME}"


def zoom_setting(zoom: float, mode: str) -> str:
    return mode or f"{zoom:.4f}"


def is_pdf_url(url: QUrl) -> bool:
    return url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
