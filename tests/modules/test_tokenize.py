"""Unit tests for mod_tokenize (SDD §7.1 #4)."""

import json

import pytest

from tta.core import artefact_kinds
from tta.core.modules.base import NotApplicable
from tta.core.modules.tokenize import Tokenize


def test_tokenizes_english_sentences(build_ctx):
    ctx = build_ctx(
        raw_text="The cat sat on the mat. A dog barked loudly!",
        language={"code": "en", "confidence": 0.99},
    )
    result = Tokenize().run(ctx)
    payload = json.loads(result.artefacts[artefact_kinds.TOKENS].read_text(encoding="utf-8"))
    assert payload["language"] == "en"
    assert len(payload["sentences"]) == 2
    assert payload["sentences"][0][:3] == ["The", "cat", "sat"]


def test_german_uses_german_punkt(build_ctx):
    ctx = build_ctx(
        raw_text="Die Katze saß z.B. auf der Matte. Der Hund schlief im Garten.",
        language={"code": "de", "confidence": 0.99},
    )
    payload = json.loads(
        Tokenize().run(ctx).artefacts[artefact_kinds.TOKENS].read_text(encoding="utf-8")
    )
    # "z.B." is not a sentence boundary
    assert len(payload["sentences"]) == 2
    assert payload["language"] == "de"


def test_unsupported_language_is_not_applicable(build_ctx):
    ctx = build_ctx(raw_text="Ciao mondo.", language={"code": "it", "confidence": 0.99})
    with pytest.raises(NotApplicable, match="unsupported language: it"):
        Tokenize().run(ctx)
