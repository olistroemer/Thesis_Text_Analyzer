"""Unit tests for mod_vocabulary (SDD §7.1 #6) — hand-computed values."""

import math

import pytest

from pds.core.modules.vocabulary import Vocabulary

# lowercased words: the:2, cat:1, and:1, dog:1 → N=5, V=4, V1=3
TOKENS = {"sentences": [["The", "cat", "and", "the", "dog", "."]], "language": "en"}


def test_hand_computed_richness(build_ctx):
    metrics = Vocabulary().run(build_ctx(tokens=TOKENS)).metrics
    assert metrics["ttr"] == pytest.approx(4 / 5)
    assert metrics["root_ttr"] == pytest.approx(4 / math.sqrt(5))
    assert metrics["hapax_token_ratio"] == pytest.approx(3 / 5)  # V1/N
    assert metrics["hapax_type_ratio"] == pytest.approx(3 / 4)  # V1/V
    # K = 1e4 * (Σ i²·V_i − N) / N² with spectrum {1: 3, 2: 1} → (7 − 5) / 25
    assert metrics["yules_k"] == pytest.approx(1e4 * 2 / 25)


def test_case_folding(build_ctx):
    tokens = {"sentences": [["Word", "word", "WORD"]], "language": "en"}
    metrics = Vocabulary().run(build_ctx(tokens=tokens)).metrics
    assert metrics["ttr"] == pytest.approx(1 / 3)
