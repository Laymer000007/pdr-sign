from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from pdr_sign.services.instance import file_args, send_to_running, socket_path
from pdr_sign.ui.single_instance import InstanceServer


def test_no_server_means_no_instance(tmp_path: Path) -> None:
    assert not send_to_running(["x.pdf"], tmp_path / "none.sock")


def test_second_launch_hands_over_files(qtbot: QtBot, tmp_path: Path) -> None:
    sock = tmp_path / "pdr.sock"
    server = InstanceServer(sock)
    assert server.start()
    received: list[list[str]] = []
    server.files_received.connect(received.append)

    # The client blocks until the server acks, so run it after the event loop spins.
    result: list[bool] = []
    import threading

    thread = threading.Thread(target=lambda: result.append(send_to_running(["a.pdf"], sock)))
    thread.start()
    qtbot.waitUntil(lambda: bool(received), timeout=3000)
    thread.join(3)
    assert result == [True]
    assert received == [[str(Path("a.pdf").resolve())]]
    server.stop()
    assert not sock.exists()


def test_stale_socket_is_replaced(tmp_path: Path) -> None:
    sock = tmp_path / "pdr.sock"
    sock.write_text("stale")
    server = InstanceServer(sock)
    assert server.start()
    server.stop()


def test_file_args() -> None:
    argv = ["pdr-sign", "--verbose", "a.pdf", "file:///tmp/My%20File.pdf"]
    assert file_args(argv) == ["a.pdf", "/tmp/My File.pdf"]


def test_socket_lives_in_xdg_runtime_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = tmp_path / "run" / "snap.pdr-sign"  # what snapd sets under confinement
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    path = socket_path()
    assert path.parent == runtime
    server = InstanceServer(path)
    assert server.start(), "server should create a missing runtime dir"
    assert path.exists() and (path.stat().st_mode & 0o777) == 0o600
    server.stop()


def test_overlong_runtime_dir_gets_short_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / ("x" * 60)))
    assert len(str(socket_path())) <= 107 or socket_path().name.startswith("pdr-sign-")
