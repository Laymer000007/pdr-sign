from pathlib import Path

from pytestqt.qtbot import QtBot

from pdr_sign.services.instance import file_args, send_to_running
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
