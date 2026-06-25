"""`mod_readability` — catalogue #7 (SDD §7.1).

Language-aware Flesch reading ease via textstat: Flesch's formula for
English [Flesch 1948], Amstad's German adaptation [Amstad 1978]; other
languages are N/A (SDD §7.2).
"""

from __future__ import annotations

import json

import textstat

from tta.core import artefact_kinds
from tta.core.modules.base import Module, ModuleSpec, NotApplicable, RunContext, RunResult

SUPPORTED = ("en", "de")


class Readability(Module):
    spec = ModuleSpec(
        name="mod_readability",
        version="0.1.0",
        consumes=(artefact_kinds.RAW_TEXT, artefact_kinds.LANGUAGE),
        produces_metrics=("flesch_reading_ease",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        language = json.loads(
            ctx.artefacts[artefact_kinds.LANGUAGE].read_text(encoding="utf-8")
        )["code"]
        if language not in SUPPORTED:
            raise NotApplicable(f"no readability formula for language: {language}")
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        # textstat's language is process-global state; set it on every run
        textstat.set_lang(language)
        return RunResult(metrics={"flesch_reading_ease": textstat.flesch_reading_ease(text)})
