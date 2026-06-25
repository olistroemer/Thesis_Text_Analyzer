"""`mod_vocabulary` — catalogue #6 (SDD §7.1). stdlib only.

Vocabulary richness over lowercased word tokens:
- ``ttr`` — type-token ratio V/N (length-sensitive; kept for comparison)
- ``root_ttr`` — Guiraud's index V/√N
- ``hapax_token_ratio`` — hapax legomena per token, V1/N
- ``hapax_type_ratio`` — share of the vocabulary occurring exactly once,
  V1/V (both hapax variants ship so they can be compared on real cohorts)
- ``yules_k`` — Yule's characteristic K = 10⁴·(Σᵢ i²·Vᵢ − N)/N²,
  length-stable per the exploration findings [Yule 1944]
"""

from __future__ import annotations

import math
from collections import Counter

from tta.core import artefact_kinds
from tta.core.modules import _tokens
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult


class Vocabulary(Module):
    spec = ModuleSpec(
        name="mod_vocabulary",
        version="0.2.0",  # 0.2.0: hapax_ratio split into token- and type-variant
        consumes=(artefact_kinds.TOKENS,),
        produces_metrics=("ttr", "root_ttr", "hapax_token_ratio", "hapax_type_ratio", "yules_k"),
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
                "hapax_token_ratio": spectrum.get(1, 0) / n,
                "hapax_type_ratio": spectrum.get(1, 0) / v,
                "yules_k": yules_k,
            }
        )
