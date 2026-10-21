from pathlib import Path

import pymupdf
import pytest

from tests.conftest import ENCRYPTED_PASSWORD


def test_text_pdf_has_three_pages(text_pdf: Path) -> None:
    with pymupdf.open(text_pdf) as doc:
        assert doc.page_count == 3
        assert "Page 2" in doc[1].get_text()


def test_encrypted_pdf_needs_password(encrypted_pdf: Path) -> None:
    with pymupdf.open(encrypted_pdf) as doc:
        assert doc.needs_pass
        assert doc.authenticate(ENCRYPTED_PASSWORD)
        assert doc.page_count == 1


@pytest.mark.slow
def test_long_pdf_has_500_pages(long_pdf: Path) -> None:
    with pymupdf.open(long_pdf) as doc:
        assert doc.page_count == 500
