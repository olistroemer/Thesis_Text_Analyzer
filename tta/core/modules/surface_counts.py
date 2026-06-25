"""`mod_surface_counts` — catalogue #5 (SDD §7.1). stdlib only.

Definitions: a word is a token with at least one letter; word length
counts alphabetic characters only; sentence length is in words.
"""

from __future__ import annotations

from statistics import pstdev

from tta.core import artefact_kinds
from tta.core.modules import _tokens
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult


class SurfaceCounts(Module):
    spec = ModuleSpec(
        name="mod_surface_counts",
        version="0.1.0",
        consumes=(artefact_kinds.TOKENS,),
        produces_metrics=(
            "word_count",
            "char_count_alpha",
            "sentence_count",
            "avg_word_len",
            "avg_sentence_len",
            "std_sentence_len",
        ),
    )

    def run(self, ctx: RunContext) -> RunResult:
        sentences = _tokens.word_sentences(ctx)
        sentence_lengths = [len(s) for s in sentences]
        word_count = sum(sentence_lengths)
        char_count_alpha = sum(
            sum(ch.isalpha() for ch in token) for sentence in sentences for token in sentence
        )
        return RunResult(
            metrics={
                "word_count": word_count,
                "char_count_alpha": char_count_alpha,
                "sentence_count": len(sentences),
                "avg_word_len": char_count_alpha / word_count,
                "avg_sentence_len": word_count / len(sentences),
                "std_sentence_len": pstdev(sentence_lengths) if len(sentences) > 1 else 0.0,
            }
        )
