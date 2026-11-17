"""Unit tests for mod_extract_pymupdf (SDD Sec. 7.1 #1 and 7.4, ADR-0024, QA-TEST)."""

import dataclasses
from collections import Counter

import pytest

pytest.importorskip("fitz")

from tta.core import artefact_kinds
from tta.core.modules.base import RunContext
from tta.core.modules.extract_pymupdf import (
    MATH,
    MONOSPACE,
    PAGE_SEPARATOR,
    ExtractPymupdf,
    filter_page,
    font_base_name,
    is_math_font,
    span_category,
)

METRICS = ("text_chars", "n_pages", "removed_monospace_chars", "removed_math_chars")


@pytest.fixture
def ctx(sample_thesis, tmp_path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    return RunContext(thesis=sample_thesis, artefacts={}, workdir=workdir)


@pytest.fixture
def code_pdf(tmp_path):
    """Prose in Helvetica and code in Courier, which PyMuPDF flags monospaced."""
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "code_thesis.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Prose line here.", fontname="helv")
    page.insert_text((72, 100), "x = foo(bar)", fontname="cour")
    page.insert_text((72, 128), "Mixed ", fontname="helv")
    page.insert_text((110, 128), "code()", fontname="cour")
    page = doc.new_page()
    page.insert_text((72, 72), "Second page.", fontname="helv")
    doc.save(path)
    doc.close()
    return path


def _run(thesis, tmp_path, name="w"):
    workdir = tmp_path / name
    workdir.mkdir()
    return ExtractPymupdf().run(RunContext(thesis=thesis, artefacts={}, workdir=workdir))


def _read(result, kind):
    return result.artefacts[kind].read_text(encoding="utf-8")


def test_spec_matches_catalogue():
    spec = ExtractPymupdf.spec
    assert spec.name == "mod_extract_pymupdf"
    assert spec.version == "0.2.0"
    assert spec.consumes == ()
    assert spec.produces_artefacts == (artefact_kinds.RAW_TEXT, artefact_kinds.PROSE_TEXT)
    assert spec.produces_metrics == METRICS
    artefact_kinds.validate_kinds(spec.consumes + spec.produces_artefacts, owner=spec.name)


def test_applicable_only_for_pdf_extension(sample_thesis):
    module = ExtractPymupdf()
    assert module.applicable(sample_thesis).ok

    not_pdf = dataclasses.replace(sample_thesis, pdf_path="/tmp/thesis.docx")
    result = module.applicable(not_pdf)
    assert not result.ok
    assert result.reason == "not a PDF"


def test_run_extracts_both_views_and_metrics(ctx, sample_pages):
    result = ExtractPymupdf().run(ctx)

    assert result.artefacts[artefact_kinds.RAW_TEXT] == ctx.workdir / "raw_text.txt"
    assert result.artefacts[artefact_kinds.PROSE_TEXT] == ctx.workdir / "prose_text.txt"
    raw = _read(result, artefact_kinds.RAW_TEXT)
    prose = _read(result, artefact_kinds.PROSE_TEXT)
    for page_text in sample_pages:
        assert page_text in raw
    # nothing to filter in plain Helvetica prose
    assert prose == raw
    assert raw.count(PAGE_SEPARATOR) == len(sample_pages) - 1

    assert set(result.metrics) == set(METRICS)
    assert result.metrics["n_pages"] == len(sample_pages)
    assert result.metrics["text_chars"] == len(prose)
    assert result.metrics["removed_monospace_chars"] == 0
    assert result.metrics["removed_math_chars"] == 0
    assert result.diagnostics["surrogates_replaced"] == {
        artefact_kinds.RAW_TEXT: 0,
        artefact_kinds.PROSE_TEXT: 0,
    }


def test_raw_text_is_exactly_get_text_text(sample_thesis, code_pdf, tmp_path):
    """ADR-0024 decision 1: the detection modules' input must not move."""
    import fitz

    with fitz.open(code_pdf) as doc:
        expected = PAGE_SEPARATOR.join(page.get_text("text") for page in doc)
    result = _run(dataclasses.replace(sample_thesis, pdf_path=str(code_pdf)), tmp_path)
    assert _read(result, artefact_kinds.RAW_TEXT) == expected


def test_monospaced_spans_leave_the_prose_view(sample_thesis, code_pdf, tmp_path):
    result = _run(dataclasses.replace(sample_thesis, pdf_path=str(code_pdf)), tmp_path)
    raw = _read(result, artefact_kinds.RAW_TEXT)
    prose = _read(result, artefact_kinds.PROSE_TEXT)

    assert "x = foo(bar)" in raw and "code()" in raw
    # the all-code line disappears, the mixed line keeps its prose span
    assert prose == "Prose line here.\nMixed \n" + PAGE_SEPARATOR + "Second page.\n"
    assert result.metrics["removed_monospace_chars"] == len("x=foo(bar)") + len("code()")
    assert result.metrics["removed_math_chars"] == 0
    assert result.metrics["text_chars"] == len(prose)
    assert result.metrics["n_pages"] == 2
    assert result.diagnostics["removed_fonts_top"][MONOSPACE] == {"Courier": 16}


def test_run_is_deterministic(ctx, tmp_path):
    first = ExtractPymupdf().run(ctx)
    second = _run(ctx.thesis, tmp_path, name="workdir2")

    assert first.metrics == second.metrics
    for kind in (artefact_kinds.RAW_TEXT, artefact_kinds.PROSE_TEXT):
        assert _read(first, kind) == _read(second, kind)


# -- font filter v1 (SDD Sec. 7.4) -------------------------------------------


@pytest.mark.parametrize(
    "font",
    [
        "CMMI10",
        "ABCDEF+CMSY7",
        "CMBSY10",
        "CMEX10",
        "MSAM10",
        "MSBM10",
        "EUFM10",
        "RSFS10",
        "stmary10",
        "Cambria Math",
        "STIXTwoMath-Regular",
        "LMMathItalic10-Regular",
        "XITSMath",
    ],
)
def test_math_fonts(font):
    assert is_math_font(font)


@pytest.mark.parametrize(
    "font",
    ["Symbol", "CMR10", "ABCDEF+CMBX12", "Times-Roman", "Calibri", "LMRoman10-Regular", ""],
)
def test_not_math_fonts(font):
    assert not is_math_font(font)


def test_font_base_name_strips_only_the_subset_tag():
    assert font_base_name("ABCDEF+CMMI10") == "CMMI10"
    assert font_base_name("Abcdef+CMMI10") == "Abcdef+CMMI10"
    assert font_base_name(None) == ""


def test_monospace_wins_over_math():
    assert span_category({"flags": 8, "font": "CMMI10"}) == MONOSPACE
    assert span_category({"flags": 8 | 2, "font": "CMTT10"}) == MONOSPACE
    assert span_category({"flags": 0, "font": "CMMI10"}) == MATH
    assert span_category({"flags": 2, "font": "CMR10"}) is None


def _span(text, font="CMR10", flags=0):
    return {"text": text, "font": font, "flags": flags}


def test_filter_page_rebuilds_lines_and_counts_visible_chars():
    page = {
        "blocks": [
            {"type": 1},  # an image block carries no text
            {
                "type": 0,
                "lines": [
                    {"spans": [_span("where "), _span("x y", "CMMI10"), _span(" holds")]},
                    {"spans": [_span("int main()", "CMTT10", 8)]},
                    {"spans": [_span("  ")]},
                ],
            },
        ]
    }
    removed = Counter({MONOSPACE: 0, MATH: 0})
    fonts = {MONOSPACE: Counter(), MATH: Counter()}

    text = filter_page(page, removed, fonts)

    # removed spans leave no gap filler; an emptied line vanishes; a kept
    # whitespace-only line stays (as in the plain-text output)
    assert text == "where  holds\n  \n"
    assert removed == {MONOSPACE: len("intmain()"), MATH: 2}
    assert fonts[MATH] == {"CMMI10": 2}
    assert fonts[MONOSPACE] == {"CMTT10": 9}
