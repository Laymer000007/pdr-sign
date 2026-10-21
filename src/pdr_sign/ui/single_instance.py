"""Single instance over a Unix socket: the listening side (client: services/instance.py).

QtNetwork's QLocalServer isn't in our allowed module list, so this uses Python's
``socket`` with a QSocketNotifier from QtCore.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
from pathlib import Path

from PySide6.QtCore import QObject, QSocketNotifier, Signal

from pdr_sign.services.instance import TIMEOUT_S, socket_path

MAX_MESSAGE = 1 << 20


class InstanceServer(QObject):
    """Listens for later launches. Emits the files they asked to open (maybe none)."""

    files_received = Signal(list)

    def __init__(self, path: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.path = path or socket_path()
        self._sock: socket.socket | None = None
        self._notifier: QSocketNotifier | None = None

    def start(self) -> bool:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()  # stale: send_to_running already found nobody listening
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(self.path))
            os.chmod(self.path, 0o600)
            sock.listen(4)
        except OSError:
            sock.close()
            return False
        sock.setblocking(False)
        self._sock = sock
        self._notifier = QSocketNotifier(sock.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._accept)
        return True

    def stop(self) -> None:
        if self._notifier is not None:
            self._notifier.setEnabled(False)
        if self._sock is not None:
            self._sock.close()
            self._sock = None
            with contextlib.suppress(FileNotFoundError):
                self.path.unlink()

    def _accept(self) -> None:
        if self._sock is None:
            return
        try:
            conn, _ = self._sock.accept()
        except BlockingIOError:
            return
        with conn:
            conn.settimeout(TIMEOUT_S)
            data = b""
            try:
                while len(data) < MAX_MESSAGE:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                conn.sendall(b"ok")
            except OSError:
                return
        try:
            paths = json.loads(data).get("open", [])
        except (ValueError, AttributeError):
            return
        self.files_received.emit([str(p) for p in paths if isinstance(p, str)])
