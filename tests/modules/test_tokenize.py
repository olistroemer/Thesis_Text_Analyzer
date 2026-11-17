"""Unit tests for mod_tokenize (SDD Sec. 7.1 #4)."""

import json

import pytest

from tta.core import artefact_kinds
from tta.core.modules.base import NotApplicable
from tta.core.modules.tokenize import Tokenize


def test_tokenizes_english_sentences(build_ctx):
    ctx = build_ctx(
        prose_text="The cat sat on the mat. A dog barked loudly!",
        language={"code": "en", "confidence": 0.99},
    )
    result = Tokenize().run(ctx)
    payload = json.loads(result.artefacts[artefact_kinds.TOKENS].read_text(encoding="utf-8"))
    assert payload["language"] == "en"
    assert len(payload["sentences"]) == 2
    assert payload["sentences"][0][:3] == ["The", "cat", "sat"]


def test_german_uses_german_punkt(build_ctx):
    ctx = build_ctx(
        prose_text="Die Katze sa\u00df z.B. auf der Matte. Der Hund schlief im Garten.",
        language={"code": "de", "confidence": 0.99},
    )
    payload = json.loads(
        Tokenize().run(ctx).artefacts[artefact_kinds.TOKENS].read_text(encoding="utf-8")
    )
    # "z.B." is not a sentence boundary
    assert len(payload["sentences"]) == 2
    assert payload["language"] == "de"


def test_unsupported_language_is_not_applicable(build_ctx):
    ctx = build_ctx(prose_text="Ciao mondo.", language={"code": "it", "confidence": 0.99})
    with pytest.raises(NotApplicable, match="unsupported language: it"):
        Tokenize().run(ctx)


def test_no_sentences_is_not_applicable_not_an_empty_artefact(build_ctx):
    """#34: an empty/word-less text used to be written out as a
    perfectly successful but EMPTY tokens artefact, silently zeroing the
    three tokens-consuming modules (13 of the 31 metrics)."""
    ctx = build_ctx(prose_text="   \n\f  \n ", language={"code": "de", "confidence": 0.99})
    with pytest.raises(NotApplicable, match="no sentences in text"):
        Tokenize().run(ctx)
    assert not (ctx.workdir / "tokens.json").exists()


def test_missing_punkt_tab_fails_loud_with_actionable_first_line(build_ctx, monkeypatch):
    """#34: NLTK's own LookupError message opens with blank lines, so the
    runner's one-line reason (`f"{type}: {exc}".splitlines()[0]`) collapsed
    to a bare "LookupError: " with no diagnostic content at all."""
    import nltk

    from tta.core.modules.tokenize import TokenizerDataMissing

    nltk.tokenize._get_punkt_tokenizer.cache_clear()
    monkeypatch.setattr(nltk.data, "path", ["/nonexistent-nltk-data"])
    ctx = build_ctx(
        prose_text="The cat sat on the mat.", language={"code": "en", "confidence": 0.99}
    )
    try:
        with pytest.raises(TokenizerDataMissing) as excinfo:
            Tokenize().run(ctx)
    finally:
        nltk.tokenize._get_punkt_tokenizer.cache_clear()

    # An environment defect, not a property of the thesis: `error`, never `na`.
    assert not isinstance(excinfo.value, NotApplicable)
    reason = f"{type(excinfo.value).__name__}: {excinfo.value}".splitlines()[0]
    assert "punkt_tab" in reason
    assert "english" in reason
    assert "/nonexistent-nltk-data" in str(excinfo.value)
    assert not (ctx.workdir / "tokens.json").exists()
