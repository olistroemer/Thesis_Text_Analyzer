"""Shared helpers for `tokens`-consuming modules (SDD Sec. 6.4: kind format).

A *word token* is a token containing at least one letter; pure
punctuation and number tokens are excluded from word-level metrics.

Process-local memo (#69)
------------------------
Three modules read the same `tokens` artefact for one thesis -
`mod_surface_counts`, `mod_vocabulary`, `mod_redundancy` - so without a
cache the JSON is parsed three times and the ``is_word`` filter is re-run
over every token three times. Measured on a 46k-token artefact that is
~100 ms per thesis, two thirds of it avoidable.

The cache is deliberately the smallest thing that removes all of it:

* **Process-local**, keyed by ``(path, st_mtime_ns, st_size)``. Nothing
  about the module contract changes - ``RunContext.artefacts`` stays
  ``dict[str, Path]`` (SDD Sec. 6.2, ADR-0004 "load-bearing public API"),
  and producers still write the artefact file, which SDD Sec. 9.2
  (double-click to open), the runner's reuse check and
  ``ArtefactStore.purge`` each independently require to exist.
* **Single-entry.** Within a worker all three consumers read one path, so
  one slot captures the entire win, and a cache that holds exactly one
  thesis cannot grow. (Workers are spawned one per thesis, but the GUI
  and the test suite do run many theses in one process; an unbounded dict
  would retain ~2.4 MB each.) A new key simply evicts the old one.

Callers must treat the returned lists as **read-only** - they are the
cached objects, not copies. All three consumers only read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tta.core import artefact_kinds
from tta.core.modules.base import NotApplicable, RunContext

#: Identity of the artefact currently memoised: (path, st_mtime_ns, st_size).
_memo_key: tuple[str, int, int] | None = None
#: Derived values for that artefact; keys are filled in on first demand.
_memo: dict[str, Any] = {}


def clear_memo() -> None:
    """Drop the memoised artefact (tests; anyone needing a cold read)."""
    global _memo_key, _memo
    _memo_key, _memo = None, {}


def _memo_for(path: Path) -> dict[str, Any]:
    """The memo slot for ``path``, reset if the file changed underneath us."""
    global _memo_key, _memo
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key != _memo_key:
        _memo_key, _memo = key, {}
    return _memo


def load_sentences(ctx: RunContext) -> list[list[str]]:
    path = ctx.artefacts[artefact_kinds.TOKENS]
    memo = _memo_for(path)
    if "sentences" not in memo:
        memo["sentences"] = json.loads(path.read_text(encoding="utf-8"))["sentences"]
    return memo["sentences"]


def is_word(token: str) -> bool:
    return any(ch.isalpha() for ch in token)


def word_sentences(ctx: RunContext) -> list[list[str]]:
    """Sentences reduced to their word tokens; NotApplicable when no words
    survive (nothing meaningful to measure)."""
    memo = _memo_for(ctx.artefacts[artefact_kinds.TOKENS])
    if "word_sentences" not in memo:
        sentences = [[t for t in sentence if is_word(t)] for sentence in load_sentences(ctx)]
        memo["word_sentences"] = [s for s in sentences if s]
    sentences = memo["word_sentences"]
    # raised on every call, cache hit or not: the outcome must not depend on
    # whether a sibling module happened to read the artefact first
    if not sentences:
        raise NotApplicable("no word tokens in tokenisation")
    return sentences
