"""Unit tests for mod_readability (SDD §7.1 #7) — Flesch en / Amstad de."""

import pytest

from tta.core.modules.base import NotApplicable
from tta.core.modules.readability import Readability

ENGLISH = "The cat sat on the mat. The dog ran to the park. We like short words."
GERMAN = "Die Katze sitzt auf der Matte. Der Hund läuft in den Park. Wir mögen kurze Wörter."


def test_english_flesch(build_ctx):
    metrics = Readability().run(
        build_ctx(raw_text=ENGLISH, language={"code": "en", "confidence": 1.0})
    ).metrics
    assert metrics["flesch_reading_ease"] > 80  # simple short-word prose


def test_german_uses_amstad(build_ctx):
    de = Readability().run(
        build_ctx(raw_text=GERMAN, language={"code": "de", "confidence": 1.0})
    ).metrics["flesch_reading_ease"]
    # Amstad differs from plain Flesch on the same text; the en formula on
    # this German text gives a different value than the de formula
    en_formula = Readability().run(
        build_ctx(raw_text=GERMAN, language={"code": "en", "confidence": 1.0})
    ).metrics["flesch_reading_ease"]
    assert de != pytest.approx(en_formula)


def test_unsupported_language_is_not_applicable(build_ctx):
    with pytest.raises(NotApplicable, match="no readability formula for language: it"):
        Readability().run(build_ctx(raw_text="Ciao.", language={"code": "it", "confidence": 1.0}))
