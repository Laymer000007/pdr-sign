import threading

from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from pdr_sign.ui.worker import Runner


def test_callbacks_run_on_the_ui_thread_in_order(qtbot: QtBot, qapp: QApplication) -> None:
    runner = Runner()
    main = threading.get_ident()
    seen: list[tuple[str, object, bool]] = []

    def work() -> str:
        assert threading.get_ident() != main  # really off the UI thread
        for n in range(3):
            runner.post(lambda n: seen.append(("page", n, threading.get_ident() == main)), n)
        return "done"

    runner.submit(work, lambda r: seen.append(("final", r, threading.get_ident() == main)))
    assert runner.busy
    qtbot.waitUntil(lambda: not runner.busy, timeout=3000)
    assert seen == [
        ("page", 0, True),
        ("page", 1, True),
        ("page", 2, True),
        ("final", "done", True),
    ]
    assert not runner._timer.isActive()  # no polling while idle


def test_exceptions_reach_the_callback(qtbot: QtBot, qapp: QApplication) -> None:
    runner = Runner()
    results: list[object] = []

    def boom() -> None:
        raise ValueError("bad image")

    runner.submit(boom, results.append)
    assert runner.wait_idle()
    (error,) = results
    assert isinstance(error, ValueError) and str(error) == "bad image"
