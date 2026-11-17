"""Tests for the artefact-kind vocabulary (SDD Sec. 6.4)."""

import pytest

from tta.core import artefact_kinds


def test_mvp_vocabulary_is_exactly_four_kinds():
    assert artefact_kinds.ALL_KINDS == {"raw_text", "prose_text", "language", "tokens", "pdf_metadata"}


def test_validate_kinds_accepts_known_kinds():
    artefact_kinds.validate_kinds(["raw_text", "language"], owner="mod_x")
    artefact_kinds.validate_kinds([], owner="mod_x")


def test_validate_kinds_rejects_unknown_kind_naming_the_module():
    with pytest.raises(ValueError, match=r"mod_bad.*'embeddings'"):
        artefact_kinds.validate_kinds(["raw_text", "embeddings"], owner="mod_bad")
