"""Welcome & support window, the Zcash address check, the coffee button and About links."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import segno
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel
from pytestqt.qtbot import QtBot

from pdr_sign.app import build_window, configure
from pdr_sign.services import settings as settings_service
from pdr_sign.services import support
from pdr_sign.services.recent import RecentFiles
from pdr_sign.services.settings import Settings
from pdr_sign.ui import desktop, dialogs, welcome_dialog, window_actions
from pdr_sign.ui.welcome_dialog import WelcomeDialog

ADDRESS = "t1J43HtBcvFmtYmJF7waapPcJtKHUwDY8mf"


# --- the address ------------------------------------------------------------------


def test_zcash_address_constant_has_a_valid_checksum() -> None:
    assert support.ZCASH_ADDRESS == ADDRESS
    payload = support.base58check_decode(support.ZCASH_ADDRESS)
    assert payload is not None and payload[:2] == bytes((0x1C, 0xB8))  # mainnet "t1"
    assert len(payload) == 22  # prefix + 20-byte public-key hash
    assert support.is_zcash_transparent_address(support.ZCASH_ADDRESS)


@pytest.mark.parametrize(
    "bad",
    [
        ADDRESS[:-1] + ("g" if ADDRESS[-1] != "g" else "h"),  # one character off
        ADDRESS[:10] + ADDRESS[11] + ADDRESS[10] + ADDRESS[12:],  # two swapped
        ADDRESS[:-1],  # truncated
        ADDRESS.replace("t", "0", 1),  # not Base58
        "1BoatSLRHtKNngkdXEeobR76b53LETtpyT",  # a valid Bitcoin address, wrong prefix
        "",
    ],
)
def test_bad_addresses_fail(bad: str) -> None:
    assert not support.is_zcash_transparent_address(bad)


def test_payment_uri() -> None:
    assert support.zcash_uri() == f"zcash:{ADDRESS}"


# --- the window ---------------------------------------------------------------------


@pytest.fixture
def welcome(qtbot: QtBot) -> WelcomeDialog:
    dialog = WelcomeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


def all_text(dialog: WelcomeDialog) -> str:
    return "\n".join(label.text() for label in dialog.findChildren(QLabel))


def test_content(welcome: WelcomeDialog) -> None:
    text = all_text(welcome)
    assert welcome.windowTitle() == "Welcome to PDR Sign"
    for line in (
        "Welcome to PDR Sign",
        "Thank you for trying PDR Sign, a fast, private PDF reader with Fill &amp; Sign"
        if "&amp;" in text
        else "Thank you for trying PDR Sign, a fast, private PDF reader with Fill & Sign",
        "Your documents never leave your computer.",
        "PDR Sign is free and open source, and always will be. No ads, no subscriptions, "
        "no paywalled features.",
        "If PDR Sign saves you time, please consider buying me a coffee. Your support "
        "funds what's next:",
        "Buy me a coffee with Zcash (ZEC)",
        "Ideas or feedback? I'd love to hear from you:",
        "micro_korn@hotmail.com",
        "Report a problem",
        "https://github.com/Laymer000007/pdr-sign/issues",
    ):
        assert line in text, line
    for milestone in support.MILESTONES:
        assert milestone in text
    assert welcome.address.text() == ADDRESS and welcome.address.isReadOnly()
    assert welcome.address.objectName() == "Mono"
    assert welcome.start.text() == "Start using PDR Sign"
    assert welcome.start.property("primary") is True
    assert not welcome.isModal()  # never blocks the app


def test_qr_encodes_the_payment_uri(monkeypatch: pytest.MonkeyPatch, qtbot: QtBot) -> None:
    seen: list[str] = []
    real = segno.make

    def spy(data: str, **kw: Any) -> Any:
        seen.append(data)
        return real(data, **kw)

    monkeypatch.setattr(welcome_dialog.segno, "make", spy)
    dialog = WelcomeDialog()
    qtbot.addWidget(dialog)
    assert seen == [f"zcash:{ADDRESS}"]
    image = dialog.qr.pixmap().toImage()
    colours = {image.pixelColor(x, y).name() for x in range(image.width()) for y in (0, 40, 80)}
    assert colours <= {"#000000", "#ffffff"}  # black on white in both themes


def test_copy_address(welcome: WelcomeDialog, fake_clipboard: Any, qtbot: QtBot) -> None:
    qtbot.mouseClick(welcome.copy_address, Qt.MouseButton.LeftButton)
    assert fake_clipboard.text() == ADDRESS
    assert welcome.toast.isVisible() and welcome.toast.label.text() == "Address copied"


def test_mailto_opens_mail_app(
    welcome: WelcomeDialog, monkeypatch: pytest.MonkeyPatch, fake_clipboard: Any
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(desktop, "open_url", lambda url: opened.append(url) or True)
    welcome.open_link(support.mailto_url())
    assert opened == ["mailto:micro_korn@hotmail.com?subject=PDR%20Sign%20feedback"]
    assert fake_clipboard.text() == ""


def test_mailto_without_mail_app_copies(
    welcome: WelcomeDialog, monkeypatch: pytest.MonkeyPatch, fake_clipboard: Any
) -> None:
    monkeypatch.setattr(desktop, "open_url", lambda _url: False)
    welcome.open_link(support.mailto_url())
    assert fake_clipboard.text() == "micro_korn@hotmail.com"
    assert "copied" in welcome.toast.label.text()


def test_start_closes(welcome: WelcomeDialog, qtbot: QtBot) -> None:
    qtbot.mouseClick(welcome.start, Qt.MouseButton.LeftButton)
    assert not welcome.isVisible()


# --- coffee button, first launch, About -----------------------------------------------


@pytest.fixture
def window(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> Any:
    s = Settings(theme="light")
    w = build_window(configure(qapp, s), s, RecentFiles(tmp_path / "recent.json"))
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    yield w
    welcome = getattr(w, "_welcome", None)
    if welcome is not None:
        welcome.close()


def test_coffee_button_next_to_search_opens_window(window: Any, qtbot: QtBot) -> None:
    header = window.header
    button = header.support_button
    assert button.toolTip().startswith("Support PDR Sign")
    assert button.accessibleName() == "Support PDR Sign"
    row = header.layout()
    assert row.indexOf(button) == row.indexOf(header.search_button) + 1
    assert button.isEnabled()  # also with no document open
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._welcome.isVisible(), timeout=2000)
    first = window._welcome
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert window._welcome is first  # one window, raised again


def test_first_launch_shows_once_ever(window: Any, qtbot: QtBot) -> None:
    assert not window.settings.welcome_shown
    assert window_actions.welcome_on_first_launch(window)
    qtbot.waitUntil(lambda: getattr(window, "_welcome", None) is not None, timeout=2000)
    assert settings_service.load().welcome_shown  # saved before it shows
    window._welcome.close()
    assert not window_actions.welcome_on_first_launch(window)
    window.settings = settings_service.load()  # e.g. after an update and restart
    assert not window_actions.welcome_on_first_launch(window)


def test_about_has_support_links(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, fake_clipboard: Any
) -> None:
    supported: list[bool] = []
    about = dialogs.AboutDialog(None, lambda: supported.append(True))
    qtbot.addWidget(about)
    text = about.support.text()
    assert "Support PDR Sign" in text and "Send feedback" in text
    assert "Report a problem" in text and support.ISSUES_URL in text
    about.show()
    about._support_link("support")
    qtbot.waitUntil(lambda: supported == [True], timeout=2000)
    assert not about.isVisible()
    monkeypatch.setattr(desktop, "open_url", lambda _url: False)
    about._support_link(support.mailto_url())
    assert fake_clipboard.text() == support.FEEDBACK_EMAIL
