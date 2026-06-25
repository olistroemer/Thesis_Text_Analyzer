"""Unit tests for mod_redundancy (SDD §7.1 #8) — hand-computed values."""

import pytest

from tta.core.modules.base import NotApplicable
from tta.core.modules.redundancy import Redundancy


def test_hand_computed_repetition(build_ctx):
    # bigrams: (a,b) (b,a) (a,b) → 3 total, 2 distinct → rate 1/3
    # trigrams: (a,b,a) (b,a,b) → 2 total, 2 distinct → rate 0
    tokens = {"sentences": [["a", "b", "a", "b"]], "language": "en"}
    metrics = Redundancy().run(build_ctx(tokens=tokens)).metrics
    assert metrics["bigram_repetition_rate"] == pytest.approx(1 / 3)
    assert metrics["trigram_repetition_rate"] == pytest.approx(0.0)


def test_ngrams_do_not_cross_sentence_boundaries(build_ctx):
    tokens = {"sentences": [["a", "b"], ["b", "a"]], "language": "en"}
    metrics = Redundancy().run(build_ctx(tokens=tokens)).metrics
    assert metrics["bigram_repetition_rate"] == pytest.approx(0.0)  # (a,b) and (b,a) distinct


def test_case_folding(build_ctx):
    tokens = {"sentences": [["The", "cat"], ["the", "cat"]], "language": "en"}
    metrics = Redundancy().run(build_ctx(tokens=tokens)).metrics
    assert metrics["bigram_repetition_rate"] == pytest.approx(0.5)


def test_too_short_for_bigrams_is_not_applicable(build_ctx):
    tokens = {"sentences": [["one"], ["two"]], "language": "en"}
    with pytest.raises(NotApplicable, match="bigrams"):
        Redundancy().run(build_ctx(tokens=tokens))
