"""`mod_redundancy` - catalogue #8 (SDD Sec. 7.1). stdlib only.

Repetition rate of word n-grams: 1 - distinct/total, over lowercased
word tokens. N-grams do not cross sentence boundaries.
"""

from __future__ import annotations

from tta.core import artefact_kinds
from tta.core.modules import _tokens
from tta.core.i18n import N_
from tta.core.modules.base import Module, ModuleSpec, NotApplicable, RunContext, RunResult


def _repetition_rate(sentences: list[list[str]], n: int) -> float | None:
    total = 0
    distinct = set()
    for sentence in sentences:
        words = [t.lower() for t in sentence]
        for i in range(len(words) - n + 1):
            total += 1
            distinct.add(tuple(words[i : i + n]))
    if total == 0:
        return None
    return 1.0 - len(distinct) / total


class Redundancy(Module):
    spec = ModuleSpec(
        name="mod_redundancy",
        version="0.2.0",  # 0.2.0: tokens come from prose_text (#22, ADR-0024)
        consumes=(artefact_kinds.TOKENS,),
        produces_metrics=("bigram_repetition_rate", "trigram_repetition_rate"),
    )

    def run(self, ctx: RunContext) -> RunResult:
        sentences = _tokens.word_sentences(ctx)
        bigram = _repetition_rate(sentences, 2)
        trigram = _repetition_rate(sentences, 3)
        if bigram is None:
            raise NotApplicable(N_("no sentence long enough for bigrams"))
        return RunResult(
            metrics={
                "bigram_repetition_rate": bigram,
                # a text can have bigrams but no trigrams; trigram rate is 0 then
                "trigram_repetition_rate": trigram if trigram is not None else 0.0,
            }
        )
