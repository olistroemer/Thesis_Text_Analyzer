"""Unit tests for mod_surface_counts (SDD §7.1 #5) — hand-computed values."""

import pytest

from pds.core.modules.base import NotApplicable
from pds.core.modules.surface_counts import SurfaceCounts

TOKENS = {
    # word tokens after punctuation filtering: [The, cat, sat] and [A, dog]
    "sentences": [["The", "cat", "sat", "."], ["A", "dog", "!"]],
    "language": "en",
}


def test_hand_computed_counts(build_ctx):
    metrics = SurfaceCounts().run(build_ctx(tokens=TOKENS)).metrics
    assert metrics["word_count"] == 5
    assert metrics["char_count_alpha"] == 13  # The(3) cat(3) sat(3) A(1) dog(3)
    assert metrics["sentence_count"] == 2
    assert metrics["avg_word_len"] == pytest.approx(13 / 5)
    assert metrics["avg_sentence_len"] == pytest.approx(2.5)
    assert metrics["std_sentence_len"] == pytest.approx(0.5)  # pstdev([3, 2])


def test_punctuation_only_sentences_are_dropped(build_ctx):
    tokens = {"sentences": [["Hello"], ["...", "!"]], "language": "en"}
    metrics = SurfaceCounts().run(build_ctx(tokens=tokens)).metrics
    assert metrics["sentence_count"] == 1
    assert metrics["std_sentence_len"] == 0.0


def test_no_words_is_not_applicable(build_ctx):
    with pytest.raises(NotApplicable, match="no word tokens"):
        SurfaceCounts().run(build_ctx(tokens={"sentences": [["..."]], "language": "en"}))
