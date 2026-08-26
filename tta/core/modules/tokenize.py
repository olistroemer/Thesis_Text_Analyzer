"""`mod_tokenize` - catalogue #4 (SDD Sec. 7.1).

NLTK punkt_tab sentence segmentation + word tokenisation. The punkt_tab
model data is bundled into release builds via PyInstaller ``--add-data``
(ADR-0014); at runtime there is never a download (QA-PRIV: fully offline).

Both failure modes are deliberately loud (#34, SDD Sec. 7.4): three
modules and thirteen of the twenty-nine metrics read `tokens`, so an
empty-but-successful artefact would zero out nearly half the catalogue
with no visible cause.
"""

from __future__ import annotations

import json

import nltk

from tta.core import artefact_kinds
from tta.core.modules.base import Module, ModuleSpec, NotApplicable, RunContext, RunResult

#: Supported language codes -> NLTK language names (SDD Sec. 7.2).
NLTK_LANGUAGES = {"en": "english", "de": "german"}


class TokenizerDataMissing(RuntimeError):
    """The bundled punkt_tab model could not be resolved.

    An environment/packaging defect, not a property of the thesis, so it
    surfaces as an `error` outcome and never as `na` (SDD Sec. 7.4).
    Raised in place of NLTK's own ``LookupError``, whose message opens
    with blank lines - which collapsed the runner's one-line reason to a
    bare ``LookupError:`` - and whose advice (``nltk.download``) is wrong
    here: the model ships with the build (ADR-0014) and the app is
    offline by design (QA-PRIV).
    """


def _segment(text: str, nltk_language: str) -> list[str]:
    """Sentence-segment `text`, translating a missing model into an
    actionable message that survives the runner's one-line reason."""
    try:
        return nltk.sent_tokenize(text, language=nltk_language)
    except LookupError as exc:
        searched = ", ".join(str(p) for p in nltk.data.path) or "<no nltk.data.path entries>"
        raise TokenizerDataMissing(
            f"NLTK punkt_tab model for '{nltk_language}' not found - "
            f"tokenisation cannot run. Expected 'tokenizers/punkt_tab/{nltk_language}/' "
            f"under one of: {searched}. Release builds bundle this model (ADR-0014) and "
            f"the app never downloads it (QA-PRIV); from source, install it once with "
            f"'python -m nltk.downloader punkt_tab'."
        ) from exc


class Tokenize(Module):
    spec = ModuleSpec(
        name="mod_tokenize",
        version="0.2.0",
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
            for sentence in _segment(text, nltk_language)
        ]
        sentences = [s for s in sentences if s]
        if not sentences:
            # Never write an empty artefact: an `na` with a reason cascades
            # honestly, an empty `tokens` file measures nothing (#34).
            raise NotApplicable("no sentences in text")
        out_path = ctx.workdir / "tokens.json"
        out_path.write_text(
            json.dumps({"sentences": sentences, "language": language}, ensure_ascii=False),
            encoding="utf-8",
        )
        return RunResult(artefacts={artefact_kinds.TOKENS: out_path})
