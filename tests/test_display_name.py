"""Users see "PDR Sign" with the tagline "Portable Document Read and Sign"; package,
command and app ID stay ``pdr-sign`` / ``io.github.Laymer000007.PdrSign``."""

from __future__ import annotations

import configparser
import xml.etree.ElementTree as ET
from pathlib import Path

from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from pdr_sign import APP_COMMAND, APP_ID, APP_NAME, TAGLINE
from pdr_sign.ui.dialogs import AboutDialog

ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "packaging" / "linux"


def test_names() -> None:
    assert APP_NAME == "PDR Sign"
    assert TAGLINE == "Portable Document Read and Sign"
    assert (APP_COMMAND, APP_ID) == ("pdr-sign", "io.github.Laymer000007.PdrSign")


def test_desktop_file() -> None:
    entry = configparser.ConfigParser(interpolation=None)
    entry.optionxform = str  # type: ignore[assignment,method-assign]
    entry.read(LINUX / f"{APP_ID}.desktop", encoding="utf-8")
    main = entry["Desktop Entry"]
    assert (main["Name"], main["Comment"]) == (APP_NAME, TAGLINE)
    assert main["Exec"].startswith(f"{APP_COMMAND} ")


def test_appstream() -> None:
    root = ET.parse(LINUX / f"{APP_ID}.metainfo.xml").getroot()
    assert root.findtext("id") == APP_ID
    assert root.findtext("name") == APP_NAME
    assert root.findtext("summary") == TAGLINE


def test_snap_deb_readme() -> None:
    snap = (ROOT / "packaging" / "snap" / "snapcraft.yaml").read_text(encoding="utf-8")
    assert "\nname: pdr-sign\n" in snap
    assert f"\ntitle: {APP_NAME}\n" in snap and f"\nsummary: {TAGLINE}\n" in snap
    control = (ROOT / "packaging" / "deb" / "control.in").read_text(encoding="utf-8")
    assert "Package: pdr-sign\n" in control and f"Description: {TAGLINE}\n" in control
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith(f"# {APP_NAME}\n")


def test_about_dialog(qtbot: QtBot) -> None:
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == f"About {APP_NAME}"
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert APP_NAME in texts
    assert any(TAGLINE in t for t in texts)


def test_saved_marks_are_authored_by_pdr_sign(tmp_path: Path) -> None:
    import pymupdf

    from pdr_sign.services import saving
    from pdr_sign.services.document import Document
    from pdr_sign.services.saving import SaveRequest
    from pdr_sign.services.stamps import OverlayItem

    path = tmp_path / "a.pdf"
    blank = pymupdf.open()
    blank.new_page()
    blank.save(path)
    doc = Document.open(path)
    items = [
        OverlayItem("text", 0, (72, 72, 200, 90), text="Hi"),
        OverlayItem("line", 0, (72, 120, 200, 120)),
    ]
    saving.save(doc, path, SaveRequest({}, items))
    doc.close()
    with pymupdf.open(path) as pdf:
        assert [a.info["title"] for a in pdf[0].annots()] == [APP_NAME, APP_NAME]
