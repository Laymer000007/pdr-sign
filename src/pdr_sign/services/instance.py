"""Single-instance client side, Qt-free so a second launch can exit before importing Qt."""

from __future__ import annotations

import json
import os
import socket
import tempfile
from pathlib import Path

from pdr_sign import APP_ID

TIMEOUT_S = 1.0


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(runtime) / f"{APP_ID}-{os.getuid()}.sock"


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
