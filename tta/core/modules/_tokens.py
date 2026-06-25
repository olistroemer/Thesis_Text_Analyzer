"""Shared helpers for `tokens`-consuming modules (SDD Sec. 6.4: kind format).

A *word token* is a token containing at least one letter; pure
punctuation and number tokens are excluded from word-level metrics.
"""

from __future__ import annotations

import json

from tta.core import artefact_kinds
from tta.core.modules.base import NotApplicable, RunContext


def load_sentences(ctx: RunContext) -> list[list[str]]:
    payload = json.loads(ctx.artefacts[artefact_kinds.TOKENS].read_text(encoding="utf-8"))
    return payload["sentences"]


def is_word(token: str) -> bool:
    return any(ch.isalpha() for ch in token)


def word_sentences(ctx: RunContext) -> list[list[str]]:
    """Sentences reduced to their word tokens; NotApplicable when no words
    survive (nothing meaningful to measure)."""
    sentences = [[t for t in sentence if is_word(t)] for sentence in load_sentences(ctx)]
    sentences = [s for s in sentences if s]
    if not sentences:
        raise NotApplicable("no word tokens in tokenisation")
    return sentences
