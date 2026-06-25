"""Unit tests for mod_extract_pymupdf (SDD §7.1 #1, QA-TEST)."""

import dataclasses

import pytest

pytest.importorskip("fitz")

from tta.core import artefact_kinds
from tta.core.modules.base import RunContext
from tta.core.modules.extract_pymupdf import PAGE_SEPARATOR, ExtractPymupdf


@pytest.fixture
def ctx(sample_thesis, tmp_path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    return RunContext(thesis=sample_thesis, artefacts={}, workdir=workdir)


def test_spec_matches_catalogue():
    spec = ExtractPymupdf.spec
    assert spec.name == "mod_extract_pymupdf"
    assert spec.consumes == ()
    assert spec.produces_artefacts == (artefact_kinds.RAW_TEXT,)
    assert spec.produces_metrics == ("text_chars", "n_pages")
    artefact_kinds.validate_kinds(spec.consumes + spec.produces_artefacts, owner=spec.name)


def test_applicable_only_for_pdf_extension(sample_thesis):
    module = ExtractPymupdf()
    assert module.applicable(sample_thesis).ok

    not_pdf = dataclasses.replace(sample_thesis, pdf_path="/tmp/thesis.docx")
    result = module.applicable(not_pdf)
    assert not result.ok
    assert result.reason == "not a PDF"


def test_run_extracts_text_and_metrics(ctx, sample_pages):
    result = ExtractPymupdf().run(ctx)

    out = result.artefacts[artefact_kinds.RAW_TEXT]
    assert out == ctx.workdir / "raw_text.txt"
    text = out.read_text(encoding="utf-8")
    for page_text in sample_pages:
        assert page_text in text

    assert result.metrics["n_pages"] == len(sample_pages)
    assert result.metrics["text_chars"] == len(text)
    assert text.count(PAGE_SEPARATOR) == len(sample_pages) - 1
    assert result.notes == {}


def test_run_is_deterministic(ctx, tmp_path):
    first = ExtractPymupdf().run(ctx)
    other_workdir = tmp_path / "workdir2"
    other_workdir.mkdir()
    second_ctx = dataclasses.replace(ctx, workdir=other_workdir)
    second = ExtractPymupdf().run(second_ctx)

    assert first.metrics == second.metrics
    assert (
        first.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        == second.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
    )
