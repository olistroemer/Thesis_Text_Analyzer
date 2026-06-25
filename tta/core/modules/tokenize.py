"""`mod_tokenize` - catalogue #4 (SDD Sec. 7.1).

NLTK punkt_tab sentence segmentation + word tokenisation. The punkt_tab
model data is bundled into release builds via PyInstaller ``--add-data``
(ADR-0014); at runtime there is never a download (QA-PRIV: fully offline).
"""

from __future__ import annotations

import json

import nltk

from tta.core import artefact_kinds
from tta.core.modules.base import Module, ModuleSpec, NotApplicable, RunContext, RunResult

#: Supported language codes -> NLTK language names (SDD Sec. 7.2).
NLTK_LANGUAGES = {"en": "english", "de": "german"}


class Tokenize(Module):
    spec = ModuleSpec(
        name="mod_tokenize",
        version="0.1.0",
        consumes=(artefact_kinds.RAW_TEXT, artefact_kinds.LANGUAGE),
        produces_artefacts=(artefact_kinds.TOKENS,),
    )

    def run(self, ctx: RunContext) -> RunResult:
        language = json.loads(
            ctx.artefacts[artefact_kinds.LANGUAGE].read_text(encoding="utf-8")
        )["code"]
        if language not in NLTK_LANGUAGES:
            raise NotApplicable(f"unsupported language: {language}")
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        nltk_language = NLTK_LANGUAGES[language]
        sentences = [
            nltk.word_tokenize(sentence, language=nltk_language)
            for sentence in nltk.sent_tokenize(text, language=nltk_language)
        ]
        out_path = ctx.workdir / "tokens.json"
        out_path.write_text(
            json.dumps({"sentences": sentences, "language": language}, ensure_ascii=False),
            encoding="utf-8",
        )
        return RunResult(artefacts={artefact_kinds.TOKENS: out_path})
