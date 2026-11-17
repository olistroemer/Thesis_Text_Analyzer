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

import contextlib
import json
import logging
import sys
from collections.abc import Iterator

from tta.core import artefact_kinds
from tta.core.modules.base import Module, ModuleSpec, NotApplicable, RunContext, RunResult

SUPPORTED = ("en", "de")

#: The NLTK corpus ``textstat`` uses for English syllable counting. Release
#: builds bundle it (ADR-0014); from source it may be absent.
CMUDICT = "corpora/cmudict"

logger = logging.getLogger(__name__)

#: textstat's cached loaders whose result is per-language, not per-text: the
#: loaded CMU dictionary and the ``Pyphen`` instance. Kept, so a reused worker
#: does not reload them for every thesis (#86).
_KEPT_TEXTSTAT_CACHES = frozenset({"get_cmudict", "get_pyphen"})


def flesch_reading_ease(text: str) -> float:
    """Flesch/Amstad for the language textstat is currently set to, offline.

    Shared with ``doctor``'s offline self-check (#42) so the diagnostic
    exercises the path the application actually takes rather than calling
    textstat raw - otherwise it reports "tried to reach the network" for a
    machine on which the application would not, in fact, reach out (#75).
    """
    import textstat

    with _no_downloads():
        try:
            return textstat.flesch_reading_ease(text)
        except LookupError as exc:
            raise RuntimeError(
                f"NLTK '{CMUDICT}' not found - the English Flesch formula needs it "
                "for syllable counting and this application never downloads it "
                "(QA-PRIV). Release builds bundle the corpus (ADR-0014); from "
                "source run 'python -m nltk.downloader cmudict'."
            ) from exc


@contextlib.contextmanager
def _no_downloads() -> Iterator[None]:
    """Make an outbound fetch impossible for the duration of the block (#75).

    ``textstat`` calls ``nltk.download('cmudict', quiet=True)`` itself when the
    English syllable corpus is missing - an outbound connection the application
    promises never to make (QA-PRIV, US-ALL-OFFLINE), with ``quiet=True``
    swallowing the failure so nothing is reported. Neutering ``nltk.download``
    enforces the promise at our own boundary instead of assuming the corpus is
    always present: German still computes without the corpus, and English then
    raises ``LookupError``, which :meth:`Readability.run` turns into an
    actionable error.
    """
    import nltk

    real = nltk.download
    nltk.download = lambda *args, **kwargs: False  # type: ignore[assignment]
    try:
        yield
    finally:
        nltk.download = real  # type: ignore[assignment]


class Readability(Module):
    spec = ModuleSpec(
        name="mod_readability",
        version="0.2.0",  # 0.2.0: reads prose_text (#22, ADR-0024)
        consumes=(artefact_kinds.PROSE_TEXT, artefact_kinds.LANGUAGE),
        produces_metrics=("flesch_reading_ease",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        language = json.loads(
            ctx.artefacts[artefact_kinds.LANGUAGE].read_text(encoding="utf-8")
        )["code"]
        if language not in SUPPORTED:
            raise NotApplicable(f"no readability formula for language: {language}")
        import textstat  # lazy: see the module docstring (#74)

        text = ctx.artefacts[artefact_kinds.PROSE_TEXT].read_text(encoding="utf-8")
        # textstat's language is process-global state; set it on every run
        textstat.set_lang(language)
        try:
            score = flesch_reading_ease(text)
        finally:
            drop_text_caches()
        return RunResult(metrics={"flesch_reading_ease": score})


def drop_text_caches() -> None:
    """Free the per-text state textstat and pyphen keep between calls (#86).

    Workers are long-lived (ADR-0013 rev. 3), so whatever a library caches
    survives into the next thesis. Two caches grow with the corpus: textstat
    wraps ~50 functions in ``lru_cache`` keyed by the full text (128 entries
    each, so up to 128 thesis texts per function), and pyphen memoises every
    word it ever hyphenated in an unbounded dict per dictionary. Together they
    grew a worker by ~2.4 MB per thesis. Both are pure caches, so clearing them
    changes no result; the per-language loaders in ``_KEPT_TEXTSTAT_CACHES``
    stay warm.

    This reaches into library internals, so it is defensive by construction:
    anything it does not find (a renamed attribute, a different cache type in a
    future version) is skipped, and nothing here can fail the module's run.
    Only modules that are already imported are visited - nothing is imported.
    """
    try:
        _clear_pyphen_word_caches()
        _clear_textstat_lru_caches()
    except Exception:  # noqa: BLE001 - a cache sweep must never fail a run
        logger.debug("could not clear textstat/pyphen caches", exc_info=True)


def _clear_pyphen_word_caches() -> None:
    pyphen = sys.modules.get("pyphen")
    hdcache = getattr(pyphen, "hdcache", None)
    values = getattr(hdcache, "values", None)
    if not callable(values):
        return
    for hyph_dict in list(values()):
        clear = getattr(getattr(hyph_dict, "cache", None), "clear", None)
        if callable(clear):
            with contextlib.suppress(Exception):
                clear()


def _clear_textstat_lru_caches() -> None:
    for name, module in list(sys.modules.items()):
        if module is None or not (name == "textstat" or name.startswith("textstat.")):
            continue
        try:
            members = list(vars(module).items())
        except TypeError:
            continue
        for attr, obj in members:
            if attr in _KEPT_TEXTSTAT_CACHES:
                continue
            with contextlib.suppress(Exception):
                clear = getattr(obj, "cache_clear", None)
                if callable(clear):
                    clear()
