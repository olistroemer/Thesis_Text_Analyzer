"""Unit tests for mod_classify_language (SDD Sec. 7.1 #3, US-RES-LANG)."""

import json

import pytest

from tta.core import artefact_kinds
from tta.core.modules.base import NotApplicable
from tta.core.modules.classify_language import ClassifyLanguage

ENGLISH = (
    "This thesis investigates the evolution of text characteristics in student "
    "theses over the last two decades. The first chapter introduces the research "
    "question and summarises the relevant literature on the topic."
)
GERMAN = (
    "Diese Arbeit untersucht die Entwicklung von Textmerkmalen in studentischen "
    "Abschlussarbeiten \u00fcber die letzten zwei Jahrzehnte. Das erste Kapitel f\u00fchrt "
    "in die Fragestellung ein und fasst die relevante Literatur zusammen."
)


def test_detects_english(build_ctx):
    result = ClassifyLanguage().run(build_ctx(raw_text=ENGLISH))
    assert result.metrics["language_code"] == "en"
    assert result.metrics["language_confidence"] > 0.9
    payload = json.loads(result.artefacts[artefact_kinds.LANGUAGE].read_text(encoding="utf-8"))
    assert payload == {
        "code": "en",
        "confidence": result.metrics["language_confidence"],
    }


def test_detects_german(build_ctx):
    result = ClassifyLanguage().run(build_ctx(raw_text=GERMAN))
    assert result.metrics["language_code"] == "de"


def test_short_text_is_not_applicable(build_ctx):
    with pytest.raises(NotApplicable, match="too short"):
        ClassifyLanguage().run(build_ctx(raw_text="Hello world."))


def test_deterministic(build_ctx):
    first = ClassifyLanguage().run(build_ctx(raw_text=ENGLISH)).metrics
    second = ClassifyLanguage().run(build_ctx(raw_text=ENGLISH)).metrics
    assert first == second  # langdetect seeded (QA-REPRO)
