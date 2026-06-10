import hashlib

import pytest

from pds.core.types import Thesis

SAMPLE_PAGES = ("Hello thesis world.", "Second page text.")


@pytest.fixture
def sample_pages():
    return SAMPLE_PAGES


@pytest.fixture
def sample_pdf(tmp_path):
    """A tiny two-page PDF, generated on the fly (no binary fixture in the repo)."""
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "sample_thesis.pdf"
    doc = fitz.open()
    for content in SAMPLE_PAGES:
        page = doc.new_page()
        page.insert_text((72, 72), content)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_thesis(sample_pdf):
    return Thesis(
        id=1,
        pdf_sha256=hashlib.sha256(sample_pdf.read_bytes()).hexdigest(),
        pdf_path=str(sample_pdf),
        pdf_filename=sample_pdf.name,
    )
