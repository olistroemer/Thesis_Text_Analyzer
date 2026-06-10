"""`mod_vocabulary` — catalogue #6 (SDD §7.1). stdlib only.

Vocabulary richness over lowercased word tokens:
- ``ttr`` — type-token ratio V/N (length-sensitive; kept for comparison)
- ``root_ttr`` — Guiraud's index V/√N
- ``hapax_ratio`` — hapax legomena per token, V1/N
- ``yules_k`` — Yule's characteristic K = 10⁴·(Σᵢ i²·Vᵢ − N)/N²,
  length-stable per the exploration findings [Yule 1944]
"""

from __future__ import annotations

import math
from collections import Counter

from pds.core import artefact_kinds
from pds.core.modules import _tokens
from pds.core.modules.base import Module, ModuleSpec, RunContext, RunResult


class Vocabulary(Module):
    spec = ModuleSpec(
        name="mod_vocabulary",
        version="0.1.0",
        consumes=(artefact_kinds.TOKENS,),
        produces_metrics=("ttr", "root_ttr", "hapax_ratio", "yules_k"),
    )

    def run(self, ctx: RunContext) -> RunResult:
        frequencies = Counter(
            token.lower()
            for sentence in _tokens.word_sentences(ctx)
            for token in sentence
        )
        n = sum(frequencies.values())
        v = len(frequencies)
        spectrum = Counter(frequencies.values())  # occurrence count i -> V_i
        yules_k = 1e4 * (sum(i * i * v_i for i, v_i in spectrum.items()) - n) / (n * n)
        return RunResult(
            metrics={
                "ttr": v / n,
                "root_ttr": v / math.sqrt(n),
                "hapax_ratio": spectrum.get(1, 0) / n,
                "yules_k": yules_k,
            }
        )
