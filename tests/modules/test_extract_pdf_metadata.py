"""Unit tests for mod_extract_pdf_metadata (SDD §7.1 #10, §7.4)."""

import dataclasses
import json

import pytest

from pds.core import artefact_kinds
from pds.core.modules.extract_pdf_metadata import ExtractPdfMetadata, categorize_tool
from tests.conftest import make_thesis


@pytest.mark.parametrize(
    ("raw", "category"),
    [
        ("pdfTeX-1.40.25", "latex"),
        ("LaTeX with hyperref", "latex"),
        ("Microsoft® Word 2019", "word"),
        ("LibreOffice 7.4", "libreoffice"),
        ("OpenOffice.org 3.2", "openoffice"),
        ("Adobe InDesign 18.0", "indesign"),
        ("GPL Ghostscript 9.55", "ghostscript"),
        ("Scribus 1.5", "other"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_categorize_tool(raw, category):
    assert categorize_tool(raw) == category


def test_curated_metrics_only_no_raw_strings(build_ctx, english_pdf):
    """Raw Producer/Creator strings must never reach the DB (SDD §7.4)."""
    thesis = make_thesis(english_pdf)
    result = ExtractPdfMetadata().run(build_ctx(thesis=thesis))

    assert result.metrics == {
        "page_count_meta": 2,
        "producer_category": "latex",
        "creator_category": "latex",
        "creation_year": 2023,
        "modification_year": 2024,
        "has_outline": False,
    }
    for value in result.metrics.values():
        assert value is None or not (isinstance(value, str) and "pdfTeX" in value)


def test_full_metadata_lands_in_local_artefact(build_ctx, english_pdf):
    thesis = make_thesis(english_pdf)
    result = ExtractPdfMetadata().run(build_ctx(thesis=thesis))
    artefact = json.loads(
        result.artefacts[artefact_kinds.PDF_METADATA].read_text(encoding="utf-8")
    )
    assert artefact["info"]["/Producer"] == "pdfTeX-1.40.25"  # raw string, local only
    assert artefact["is_encrypted"] is False
    assert "pdf_version" in artefact


def test_pdf_without_metadata(build_ctx, sample_pdf):
    thesis = make_thesis(sample_pdf)
    metrics = ExtractPdfMetadata().run(build_ctx(thesis=thesis)).metrics
    assert metrics["creation_year"] is None
    assert metrics["producer_category"] in {"unknown", "other"}


def test_applicable_only_for_pdf(sample_thesis):
    not_pdf = dataclasses.replace(sample_thesis, pdf_path="/tmp/x.docx")
    assert not ExtractPdfMetadata().applicable(not_pdf).ok
