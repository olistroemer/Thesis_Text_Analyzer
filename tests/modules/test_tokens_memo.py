"""Process-local memo in `_tokens` (#69).

Three modules read the same `tokens` artefact per thesis, so the parse and
the `is_word` filter are memoised. The contract must be unchanged:
`RunContext.artefacts` still carries Paths (ADR-0004), the artefact file is
still written, and a stale file is never served.
"""

import json
import os

import pytest

from tta.core import artefact_kinds
from tta.core.modules import _tokens
from tta.core.modules.base import NotApplicable
from tta.core.modules.redundancy import Redundancy
from tta.core.modules.surface_counts import SurfaceCounts
from tta.core.modules.vocabulary import Vocabulary

TOKENS = {"sentences": [["Der", "Hund", "schlief", "."], ["Die", "Katze", "sass", "."]],
          "language": "de"}


def test_repeated_reads_hit_the_memo(build_ctx):
    ctx = build_ctx(tokens=TOKENS)
    assert _tokens.load_sentences(ctx) is _tokens.load_sentences(ctx)
    assert _tokens.word_sentences(ctx) is _tokens.word_sentences(ctx)


def test_the_artefact_file_is_parsed_once_for_all_three_consumers(build_ctx, monkeypatch):
    """The point of #69: 3 reads + 3 is_word passes collapse to one."""
    ctx = build_ctx(tokens=TOKENS)
    reads = []
    real_read_text = type(ctx.artefacts[artefact_kinds.TOKENS]).read_text

    def counting(self, *args, **kwargs):
        reads.append(str(self))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(ctx.artefacts[artefact_kinds.TOKENS]), "read_text", counting)
    SurfaceCounts().run(ctx)
    Vocabulary().run(ctx)
    Redundancy().run(ctx)
    tokens_path = str(ctx.artefacts[artefact_kinds.TOKENS])
    assert reads.count(tokens_path) == 1


def test_changed_content_is_not_served_from_the_memo(build_ctx):
    ctx = build_ctx(tokens=TOKENS)
    assert len(_tokens.load_sentences(ctx)) == 2

    path = ctx.artefacts[artefact_kinds.TOKENS]
    path.write_text(
        json.dumps({"sentences": [["Nur", "ein", "Satz", "."]], "language": "de"}),
        encoding="utf-8",
    )
    assert len(_tokens.load_sentences(ctx)) == 1


def test_same_size_rewrite_is_caught_by_mtime(build_ctx):
    """Size alone is not enough: the key carries st_mtime_ns too."""
    ctx = build_ctx(tokens=TOKENS)
    path = ctx.artefacts[artefact_kinds.TOKENS]
    first = _tokens.load_sentences(ctx)
    original = path.read_text(encoding="utf-8")
    swapped = original.replace("Hund", "Wolf")
    assert len(swapped) == len(original)  # identical size on purpose
    path.write_text(swapped, encoding="utf-8")
    os.utime(path, (0, 0))  # a different mtime, same size
    assert _tokens.load_sentences(ctx) is not first
    assert _tokens.load_sentences(ctx)[0][1] == "Wolf"


def test_two_artefacts_do_not_bleed_into_each_other(build_ctx, tmp_path):
    ctx_a = build_ctx(tokens=TOKENS)
    other = tmp_path / "other_tokens.json"
    other.write_text(
        json.dumps({"sentences": [["Ein", "Satz", "."]], "language": "de"}), encoding="utf-8"
    )
    ctx_b = build_ctx(tokens=TOKENS)
    ctx_b.artefacts[artefact_kinds.TOKENS] = other

    assert len(_tokens.load_sentences(ctx_a)) == 2
    assert len(_tokens.load_sentences(ctx_b)) == 1
    assert len(_tokens.load_sentences(ctx_a)) == 2


def test_memo_holds_a_single_entry(build_ctx, tmp_path):
    """Workers are spawned per thesis, but the GUI and the test suite run many
    in one process - the cache must not accumulate them (#69)."""
    ctx_a = build_ctx(tokens=TOKENS)
    first = _tokens.load_sentences(ctx_a)

    other = tmp_path / "other_tokens.json"
    other.write_text(
        json.dumps({"sentences": [["Ein", "Satz", "."]], "language": "de"}), encoding="utf-8"
    )
    ctx_b = build_ctx(tokens=TOKENS)
    ctx_b.artefacts[artefact_kinds.TOKENS] = other
    _tokens.load_sentences(ctx_b)

    # reading B evicted A rather than keeping both alive
    assert _tokens.load_sentences(ctx_a) is not first


def test_not_applicable_is_raised_on_every_call_not_just_the_first(build_ctx):
    """The outcome must not depend on whether a sibling module read first."""
    ctx = build_ctx(tokens={"sentences": [[".", "..."], ["42"]], "language": "de"})
    for _ in range(3):
        with pytest.raises(NotApplicable, match="no word tokens in tokenisation"):
            _tokens.word_sentences(ctx)


def test_clear_memo_forces_a_cold_read(build_ctx):
    ctx = build_ctx(tokens=TOKENS)
    first = _tokens.load_sentences(ctx)
    _tokens.clear_memo()
    assert _tokens.load_sentences(ctx) is not first
    assert _tokens.load_sentences(ctx) == first


def test_run_context_still_carries_paths(build_ctx):
    """ADR-0004 is a load-bearing public API: the memo must not have turned
    artefacts into objects (#69 explicitly rules that out)."""
    from pathlib import Path

    ctx = build_ctx(tokens=TOKENS)
    _tokens.word_sentences(ctx)
    assert isinstance(ctx.artefacts[artefact_kinds.TOKENS], Path)
    assert ctx.artefacts[artefact_kinds.TOKENS].exists()
