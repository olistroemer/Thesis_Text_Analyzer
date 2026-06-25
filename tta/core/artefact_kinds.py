"""Vocabulary of artefact kinds - the documented source of truth (SDD Sec. 6.4).

Module declarations are checked against this vocabulary at registration.
Privacy classes per kind are registered in ``privacy_metadata.py`` (ADR-0009);
the short notes here are informative only.
"""

from __future__ import annotations

from collections.abc import Iterable

#: UTF-8 plain text file extracted from the PDF. Content - PII risk; never exported.
RAW_TEXT = "raw_text"

#: JSON ``{"code": "en", "confidence": 0.99}``. Metric - no PII.
LANGUAGE = "language"

#: JSON ``{"sentences": [["w", "w"], ...], "language": "en"}``. Content - PII in aggregate; never exported.
TOKENS = "tokens"

#: JSON: full PDF Info dict + XMP. Identifying (may include author/title); never exported.
PDF_METADATA = "pdf_metadata"

ALL_KINDS: frozenset[str] = frozenset({RAW_TEXT, LANGUAGE, TOKENS, PDF_METADATA})


def validate_kinds(kinds: Iterable[str], *, owner: str = "<unknown>") -> None:
    """Raise ``ValueError`` if any kind is not in the documented vocabulary.

    Called at module registration for both ``consumes`` and
    ``produces_artefacts`` declarations; ``owner`` names the declaring
    module for the error message.
    """
    unknown = sorted(set(kinds) - ALL_KINDS)
    if unknown:
        raise ValueError(
            f"module {owner!r} declares unknown artefact kind(s) {unknown}; "
            f"documented vocabulary: {sorted(ALL_KINDS)} (core/artefact_kinds.py)"
        )
