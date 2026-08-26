"""`mod_readability` - catalogue #7 (SDD Sec. 7.1).

Language-aware Flesch reading ease via textstat: Flesch's formula for
English [Flesch 1948], Amstad's German adaptation [Amstad 1978]; other
languages are N/A (SDD Sec. 7.2).

``textstat`` is imported **inside** ``run``, not at module scope (#74):
importing it costs ~1.13 s because it imports ``nltk`` itself, and building
the module catalogue instantiates every module - so that second was paid on
every GUI launch, by five CLI commands and in every spawned worker. The
import sits after the applicability check, so a thesis in an unsupported
language never pays it.
"""

from __future__ import annotations

import json

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
        import textstat  # lazy: see the module docstring (#74)

        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        # textstat's language is process-global state; set it on every run
        textstat.set_lang(language)
        return RunResult(metrics={"flesch_reading_ease": textstat.flesch_reading_ease(text)})
