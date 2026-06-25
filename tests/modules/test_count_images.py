"""Unit tests for mod_count_images (SDD §7.1 #9)."""

import dataclasses

import pytest

from tta.core.modules.count_images import CountImages
from tests.conftest import make_thesis


@pytest.fixture
def pdf_with_images(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "with_images.pdf"
    doc = fitz.open()
    page = doc.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8))
    pixmap.clear_with(200)
    page.insert_image(fitz.Rect(72, 72, 144, 144), pixmap=pixmap)
    page.insert_image(fitz.Rect(200, 72, 272, 144), pixmap=pixmap)
    doc.new_page()  # second page, no images
    doc.save(path)
    doc.close()
    return path


def test_counts_embedded_images(build_ctx, pdf_with_images):
    thesis = make_thesis(pdf_with_images)
    result = CountImages().run(build_ctx(thesis=thesis))
    assert result.metrics == {"n_images": 2}


def test_text_only_pdf_has_zero(build_ctx, sample_thesis):
    result = CountImages().run(build_ctx(thesis=sample_thesis))
    assert result.metrics == {"n_images": 0}


def test_applicable_only_for_pdf(sample_thesis):
    not_pdf = dataclasses.replace(sample_thesis, pdf_path="/tmp/x.docx")
    assert not CountImages().applicable(not_pdf).ok
