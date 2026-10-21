"""Single-instance client side, Qt-free so a second launch can exit before importing Qt."""

from __future__ import annotations

import json
import os
import socket
import tempfile
from pathlib import Path

from pdr_sign import APP_ID

TIMEOUT_S = 1.0
MAX_SOCKET_PATH = 107  # sun_path is 108 bytes including the terminating NUL


def socket_path() -> Path:
    """Per-user socket under $XDG_RUNTIME_DIR.

    Under strict snap confinement $XDG_RUNTIME_DIR is ``/run/user/<uid>/snap.pdr-sign``,
    which the default AppArmor template lets the snap write to (abstract sockets and
    the host /run/user/<uid> are not allowed). /tmp is only a fallback for sessions
    without a runtime dir.
    """
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    path = runtime / f"{APP_ID}-{os.getuid()}.sock"
    if len(os.fsencode(path)) > MAX_SOCKET_PATH:
        path = runtime / f"pdr-sign-{os.getuid()}.sock"
    return path


def send_to_running(paths: list[str], path: Path | None = None) -> bool:
    """Hand ``paths`` to a running instance. False when there isn't one."""
    message = json.dumps({"open": [str(Path(p).resolve()) for p in paths]}).encode()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(TIMEOUT_S)
            sock.connect(str(path or socket_path()))
            sock.sendall(message)
            sock.shutdown(socket.SHUT_WR)
            return sock.recv(16) == b"ok"
    except OSError:
        return False


def file_args(argv: list[str]) -> list[str]:
    """PDF paths from the command line (``file://`` URIs from file managers included)."""
    from urllib.parse import unquote, urlparse

    paths = []
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        paths.append(unquote(urlparse(arg).path) if arg.startswith("file://") else arg)
    return paths
