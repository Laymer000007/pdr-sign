"""All of the app's windows: one process, any number of main windows.

New windows come from Ctrl+N / the menu, a tab moved or dragged out, and the
launcher's "New Window" action (a second launch with ``--new-window``). Files from
the file manager open in the most recently focused window; one that's already open
somewhere is shown there instead of opening twice. Closing the last window quits.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint

from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.services.signatures import SignatureStore
from pdr_sign.ui.render_scheduler import RenderScheduler
from pdr_sign.ui.signature_library import SignatureLibrary

if TYPE_CHECKING:
    from pdr_sign.app import ThemeController
    from pdr_sign.ui.document_tab import DocumentTab
    from pdr_sign.ui.main_window import MainWindow

CASCADE = QPoint(32, 32)  # each new window a little down-right of the last


class WindowManager(QObject):
    def __init__(
        self, controller: ThemeController, settings: Settings, recent: RecentFiles
    ) -> None:
        super().__init__()
        self.controller = controller
        self.settings = settings
        self.recent = recent
        self.scheduler = RenderScheduler()  # one render thread for every window
        self.library = SignatureLibrary(SignatureStore(settings.signature_dir), self)
        self.windows: list[MainWindow] = []
        self.last_active: MainWindow | None = None

    def new_window(self, show: bool = True) -> MainWindow:
        from pdr_sign.ui.main_window import MainWindow

        window = MainWindow(
            self.controller.tokens,
            self.settings,
            self.recent,
            self.scheduler,
            library=self.library,
            manager=self,
        )
        window.theme_controller = self.controller
        previous = self.last_active if self.last_active in self.windows else None
        self.windows.append(window)
        self.last_active = window
        if show:
            if previous is not None:
                window.resize(previous.size())
                window.move(previous.pos() + CASCADE)
            window.show()
            window.raise_()
            window.activateWindow()
        return window

    def activated(self, window: MainWindow) -> None:
        if window in self.windows:
            self.last_active = window

    def closed(self, window: MainWindow) -> None:
        if window in self.windows:
            self.windows.remove(window)
        if self.last_active is window:
            self.last_active = self.windows[-1] if self.windows else None

    def find(self, path: Path) -> tuple[MainWindow, DocumentTab] | None:
        for window in self.windows:
            for tab in window.tabs:
                if tab.doc.path == path:
                    return window, tab
        return None

    def open_paths(self, paths: list[str], new_window: bool = False) -> MainWindow | None:
        """Open ``paths`` in the most recently focused window (or a new one). Files open
        elsewhere already are shown there. Returns the window that got new tabs."""
        if new_window or not self.windows:
            target = self.new_window()
        else:
            target = self.last_active if self.last_active in self.windows else self.windows[-1]
        fresh: list[str] = []
        for raw in paths:
            found = self.find(Path(raw).expanduser().resolve())
            if found is None:
                fresh.append(raw)
                continue
            window, tab = found
            window.show_tab(tab)
            if not fresh and target is not window and not new_window:
                self.last_active = window
        if fresh:
            target.open_paths(fresh)
        elif not paths:
            target.raise_()
            target.activateWindow()
        return target

    def set_tokens(self, tokens: object) -> None:
        for window in self.windows:
            window.set_tokens(tokens)  # type: ignore[arg-type]
