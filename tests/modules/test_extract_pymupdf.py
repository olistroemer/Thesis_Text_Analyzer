"""Unit tests for mod_extract_pymupdf (SDD Sec. 7.1 #1 and 7.4, ADR-0024, QA-TEST)."""

import dataclasses

import pytest

pytest.importorskip("fitz")

from tta.core import artefact_kinds
from tta.core.modules.base import RunContext
from tta.core.modules.extract_pymupdf import (
    GUARD_SHARE,
    MATH,
    MONOSPACE,
    PAGE_SEPARATOR,
    ExtractPymupdf,
    FilterTally,
    classify_page,
    font_base_name,
    guarded_categories,
    is_math_font,
    render_page,
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


def _page(*lines):
    """A ``extractDICT()``-shaped page: an image block, then one text block."""
    return {"blocks": [{"type": 1}, {"type": 0, "lines": [{"spans": list(s)} for s in lines]}]}


def test_classify_and_render_rebuild_lines_and_count_visible_chars():
    page = _page(
        [_span("where "), _span("x y", "CMMI10"), _span(" holds")],
        [_span("int main()", "CMTT10", 8)],
        [_span("  ")],
    )
    tally = FilterTally()

    lines = classify_page(page, tally)

    # removed spans leave no gap filler; an emptied line vanishes; a kept
    # whitespace-only line stays (as in the plain-text output)
    assert render_page(lines) == "where  holds\n  \n"
    # a category in `keep` stays in
    assert render_page(lines, frozenset({MONOSPACE})) == "where  holds\nint main()\n  \n"
    assert tally.candidates == {MONOSPACE: len("intmain()"), MATH: 2}
    assert tally.visible == len("whereholds") + 2 + len("intmain()")
    assert tally.fonts[MATH] == {"CMMI10": 2}
    assert tally.fonts[MONOSPACE] == {"CMTT10": 9}


# -- whole-document guard (ADR-0024 decision 2a) ------------------------------


def _tally(visible, mono=0, math=0):
    tally = FilterTally(visible=visible)
    tally.candidates.update({MONOSPACE: mono, MATH: math})
    return tally


def test_guard_threshold_is_strictly_above_the_share():
    assert GUARD_SHARE == 0.80
    assert guarded_categories(_tally(100, mono=80)) == {}
    assert guarded_categories(_tally(100, mono=81)) == {MONOSPACE: 0.81}
    assert guarded_categories(_tally(100, math=95, mono=3)) == {MATH: 0.95}
    assert guarded_categories(_tally(0)) == {}


def test_guard_spares_a_listing_appendix():
    """The largest genuine monospace share in Exp #22 (0.627, prose plus a
    long listing appendix) is still filtered."""
    assert guarded_categories(_tally(1000, mono=627, math=10)) == {}


@pytest.fixture
def courier_pdf(tmp_path):
    """A document set entirely in Courier, except one Helvetica title line."""
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "courier_thesis.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Title", fontname="helv")
    for i in range(10):
        page.insert_text((72, 100 + 20 * i), f"The body line {i} is typed.", fontname="cour")
    doc.save(path)
    doc.close()
    return path


def test_a_document_set_in_a_monospace_font_keeps_its_text(sample_thesis, courier_pdf, tmp_path):
    result = _run(dataclasses.replace(sample_thesis, pdf_path=str(courier_pdf)), tmp_path)
    raw = _read(result, artefact_kinds.RAW_TEXT)
    prose = _read(result, artefact_kinds.PROSE_TEXT)

    assert prose == raw
    assert "The body line 9 is typed." in prose
    assert result.metrics["removed_monospace_chars"] == 0
    assert result.metrics["text_chars"] == len(prose)
    skipped = result.diagnostics["filter_skipped"]
    assert set(skipped) == {MONOSPACE}
    assert skipped[MONOSPACE]["share"] > GUARD_SHARE
    assert skipped[MONOSPACE]["chars"] == 10 * len("Thebodyline0istyped.")
    assert skipped[MONOSPACE]["fonts_top"] == {"Courier": skipped[MONOSPACE]["chars"]}
    assert MONOSPACE not in result.diagnostics["removed_fonts_top"]


def test_a_normal_code_thesis_is_still_filtered(sample_thesis, code_pdf, tmp_path):
    result = _run(dataclasses.replace(sample_thesis, pdf_path=str(code_pdf)), tmp_path)
    assert result.diagnostics["filter_skipped"] == {}
    assert result.metrics["removed_monospace_chars"] > 0
    assert "x = foo(bar)" not in _read(result, artefact_kinds.PROSE_TEXT)


def test_a_document_set_in_a_math_font_keeps_its_text(sample_thesis, tmp_path, monkeypatch):
    """A Word body in Cambria Math (ETH 153428 in Exp #22). The math category
    is guarded; inline code in the same document is still removed, because
    each category is decided on its own share."""
    import fitz

    body = [[_span(f"Der Text {i} steht in Cambria Math.", "Cambria Math")] for i in range(20)]
    code = [_span("ls -la", "Courier", 8)]
    pages = [_page(*body, code)]

    class FakeTextPage:
        def __init__(self, page_dict):
            self.page_dict = page_dict

        def extractText(self):
            return "unused by the guard\n"

        def extractDICT(self, cb=None):
            return self.page_dict

    class FakePage:
        cropbox = None

        def __init__(self, page_dict):
            self.page_dict = page_dict

        def get_textpage(self, flags=None):
            return FakeTextPage(self.page_dict)

    class FakeDoc:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            return iter(FakePage(p) for p in pages)

    monkeypatch.setattr(fitz, "open", lambda *a, **k: FakeDoc())
    result = _run(sample_thesis, tmp_path)
    prose = _read(result, artefact_kinds.PROSE_TEXT)

    assert "Der Text 19 steht in Cambria Math." in prose
    assert "ls -la" not in prose
    assert result.metrics["removed_math_chars"] == 0
    assert result.metrics["removed_monospace_chars"] == len("ls-la")
    assert set(result.diagnostics["filter_skipped"]) == {MATH}
