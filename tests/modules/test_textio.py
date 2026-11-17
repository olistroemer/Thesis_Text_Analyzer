"""Lone surrogates in text artefacts (#95, SDD Sec. 6.4 "Encoding rule").

A PDF text layer can yield a lone surrogate such as ``\\udc5b``; strict UTF-8
cannot encode it, so every artefact writer used to crash with
``UnicodeEncodeError``. Each writer is fed a fake extraction carrying one.
"""

import json

import pytest

from tta.core import artefact_kinds
from tta.core.modules import _textio
from tta.core.modules.base import RunContext

LONE = "\udc5b"


def test_replace_lone_surrogates_counts_and_replaces():
    text, n = _textio.replace_lone_surrogates("a" + LONE + "b\ud800")
    assert text == "a\ufffdb\ufffd"
    assert n == 2


def test_text_without_surrogates_is_unchanged():
    text = "Gr\u00f6\u00dfe \U0001d465 \u2211"  # incl. a non-BMP character (one code point)
    assert _textio.replace_lone_surrogates(text) == (text, 0)


def test_write_text_artefact_writes_valid_utf8(tmp_path):
    path = tmp_path / "out.txt"
    assert _textio.write_text_artefact(path, "x" + LONE) == 1
    assert path.read_bytes().decode("utf-8") == "x\ufffd"


def test_extract_pymupdf_survives_a_lone_surrogate(sample_thesis, tmp_path, monkeypatch):
    pytest.importorskip("fitz")
    import fitz

    from tta.core.modules.extract_pymupdf import ExtractPymupdf

    text = "Text " + LONE + " layer"

    class FakeTextPage:
        def extractText(self):
            return text + "\n"

        def extractDICT(self, cb=None):
            span = {"text": text, "font": "Times-Roman", "flags": 0}
            return {"blocks": [{"type": 0, "lines": [{"spans": [span]}]}]}

    class FakePage:
        cropbox = None

        def get_textpage(self, flags=None):
            return FakeTextPage()

    class FakeDoc:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            return iter([FakePage(), FakePage()])

    monkeypatch.setattr(fitz, "open", lambda *a, **k: FakeDoc())
    workdir = tmp_path / "w"
    workdir.mkdir()
    result = ExtractPymupdf().run(RunContext(thesis=sample_thesis, artefacts={}, workdir=workdir))

    for kind in (artefact_kinds.RAW_TEXT, artefact_kinds.PROSE_TEXT):
        written = result.artefacts[kind].read_text(encoding="utf-8")
        assert LONE not in written
        assert written.count("\ufffd") == 2
    assert result.diagnostics["surrogates_replaced"] == {
        artefact_kinds.RAW_TEXT: 2,
        artefact_kinds.PROSE_TEXT: 2,
    }


def test_extract_pdf_metadata_survives_a_lone_surrogate(build_ctx, sample_thesis, monkeypatch):
    from tta.core.modules import extract_pdf_metadata

    class FakeReader:
        metadata = {"/Title": "Titel " + LONE, "/Producer": "pdfTeX"}
        xmp_metadata = None
        outline = []
        trailer = {"/Root": {}}
        pdf_header = "%PDF-1.5"
        is_encrypted = False
        pages = [object()]

    monkeypatch.setattr(extract_pdf_metadata, "PdfReader", lambda path: FakeReader())
    result = extract_pdf_metadata.ExtractPdfMetadata().run(build_ctx(thesis=sample_thesis))

    payload = json.loads(
        result.artefacts[artefact_kinds.PDF_METADATA].read_text(encoding="utf-8")
    )
    assert payload["info"]["/Title"] == "Titel \ufffd"
    assert result.diagnostics["surrogates_replaced"] == 1
    assert result.metrics["producer_category"] == "latex"


def test_tokenize_survives_a_lone_surrogate(build_ctx, monkeypatch):
    pytest.importorskip("nltk")
    from tta.core.modules import tokenize

    # a text artefact on disk cannot hold a lone surrogate any more, so the fake
    # sits behind the read: segmentation hands one to the word tokeniser
    monkeypatch.setattr(
        tokenize, "_segment", lambda text, language: ["Ein Wort" + LONE + " hier."]
    )
    ctx = build_ctx(prose_text="Ein Wort hier.", language={"code": "de", "confidence": 0.99})
    result = tokenize.Tokenize().run(ctx)

    payload = json.loads(result.artefacts[artefact_kinds.TOKENS].read_text(encoding="utf-8"))
    assert "Wort\ufffd" in payload["sentences"][0]
    assert result.diagnostics["surrogates_replaced"] == 1
