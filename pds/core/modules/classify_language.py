"""`mod_classify_language` — catalogue #3 (SDD §7.1, US-RES-LANG)."""

from __future__ import annotations

import json

from langdetect import DetectorFactory, detect_langs

from pds.core import artefact_kinds
from pds.core.modules.base import Module, ModuleSpec, NotApplicable, RunContext, RunResult

# langdetect is randomised by default; a fixed seed makes identical
# inputs produce identical outputs (QA-TEST determinism, QA-REPRO).
DetectorFactory.seed = 0

MIN_CHARS = 200  # applicability threshold per SDD §7.2
MAX_CHARS = 20_000  # the head is plenty for confident detection (≤ 500 ms budget)


class ClassifyLanguage(Module):
    spec = ModuleSpec(
        name="mod_classify_language",
        version="0.1.0",
        consumes=(artefact_kinds.RAW_TEXT,),
        produces_artefacts=(artefact_kinds.LANGUAGE,),
        produces_metrics=("language_code", "language_confidence"),
    )

    def run(self, ctx: RunContext) -> RunResult:
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8").strip()
        if len(text) < MIN_CHARS:
            raise NotApplicable("text too short for confident detection")
        best = detect_langs(text[:MAX_CHARS])[0]
        payload = {"code": best.lang, "confidence": round(best.prob, 4)}
        out_path = ctx.workdir / "language.json"
        out_path.write_text(json.dumps(payload), encoding="utf-8")
        return RunResult(
            metrics={"language_code": payload["code"], "language_confidence": payload["confidence"]},
            artefacts={artefact_kinds.LANGUAGE: out_path},
        )
