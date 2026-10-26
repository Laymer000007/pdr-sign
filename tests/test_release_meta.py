"""Release metadata stays in step with the code: support links, address, QR, dates."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from dataclasses import fields
from pathlib import Path

import segno

from pdr_sign import __version__
from pdr_sign.services import settings, support

ROOT = Path(__file__).resolve().parents[1]
METAINFO = ROOT / "packaging" / "linux" / "io.github.Laymer000007.PdrSign.metainfo.xml"


def readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_qr_is_generated_from_the_address_constant() -> None:
    buffer = io.BytesIO()
    segno.make(support.zcash_uri(), error="m").save(
        buffer, kind="svg", scale=5, border=4, dark="#000000", light="#ffffff", xmldecl=False
    )
    assert (ROOT / "docs" / "support" / "zcash-qr.svg").read_bytes() == buffer.getvalue()


def test_readme_support_install_and_free_note() -> None:
    text = readme()
    assert support.ZCASH_ADDRESS in text and support.FEEDBACK_EMAIL in text
    assert "Free forever, supported by donations" in text
    assert "sudo snap install pdr-sign" in text
    assert "sudo snap connect pdr-sign:cups-control" in text
    assert "sudo apt install ./pdr-sign_" in text and ".AppImage" in text
    assert support.ISSUES_URL in text and "## Support" in text and "## Feedback" in text


def test_appstream_urls_and_release() -> None:
    root = ET.parse(METAINFO).getroot()
    urls = {u.get("type"): u.text for u in root.findall("url")}
    assert urls["bugtracker"] == support.ISSUES_URL
    assert urls["donation"] == f"{support.ISSUES_URL.removesuffix('/issues')}#support"
    assert urls["contact"].endswith("#feedback")
    release = root.find("releases/release")
    assert release is not None and release.get("version") == __version__


def test_snap_store_links() -> None:
    snap = (ROOT / "packaging" / "snap" / "snapcraft.yaml").read_text(encoding="utf-8")
    for line in (
        "website: https://github.com/Laymer000007/pdr-sign",
        "source-code: https://github.com/Laymer000007/pdr-sign",
        f"issues: {support.ISSUES_URL}",
        f"contact: mailto:{support.FEEDBACK_EMAIL}",
        "donation: https://github.com/Laymer000007/pdr-sign#support",
    ):
        assert f"\n{line}\n" in snap, line


def test_changelog_and_security() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog
    assert support.FEEDBACK_EMAIL in (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    templates = ROOT / ".github" / "ISSUE_TEMPLATE"
    assert {p.name for p in templates.glob("*.yml")} >= {"bug_report.yml", "feature_request.yml"}


def test_no_licence_key_anywhere() -> None:
    assert "license_key" not in {f.name for f in fields(settings.Settings)}
    assert "license_key" in settings.DROPPED_KEYS
