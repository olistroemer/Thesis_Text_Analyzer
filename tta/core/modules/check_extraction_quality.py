"""`mod_check_extraction_quality` — catalogue #2 (SDD §7.1).

Heuristic from `harvester/GARBLED_EXTRACTIONS.md`: PDFs with broken
/ToUnicode CMaps extract as deterministic gibberish in every library;
the ratio of common EN/DE function words separates clean (≥ 0.149) from
garbled (≤ 0.063) text, threshold 0.10. Texts with fewer than 200 word
tokens are too sparse to judge (poster-style documents).

Flags but does NOT block downstream modules (SDD §7.4): a `garbled`
thesis still gets all metrics computed; the grid shows a warning glyph.
"""

from __future__ import annotations

import re

from tta.core import artefact_kinds
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult

STOP_WORDS = frozenset(
    {
        # en
        "the", "of", "and", "to", "in", "is", "a", "for", "with", "on", "as", "are",
        # de
        "die", "der", "und", "das", "den", "von", "mit", "für", "ist", "auf", "des",
        "im", "ein", "eine", "zu", "wird",
    }
)
WORD_RE = re.compile(r"[a-zäöüß]+")
GARBLED_THRESHOLD = 0.10
MIN_TOKENS = 200
MAX_TOKENS = 5000  # judging the head is enough; keeps the budget ≤ 100 ms


class CheckExtractionQuality(Module):
    spec = ModuleSpec(
        name="mod_check_extraction_quality",
        version="0.1.0",
        consumes=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("extraction_quality",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        tokens = WORD_RE.findall(text.lower())[:MAX_TOKENS]
        if len(tokens) < MIN_TOKENS:
            quality, score = "sparse", None
        else:
            score = sum(token in STOP_WORDS for token in tokens) / len(tokens)
            quality = "garbled" if score < GARBLED_THRESHOLD else "ok"
        return RunResult(
            metrics={"extraction_quality": quality},
            notes={"stop_word_ratio": score, "tokens_checked": len(tokens)},
        )
