"""Shared plain types crossing the core boundary (SDD Sec. 6.1, ADR-0002).

The module contract (``Module``, ``ModuleSpec``, ``RunContext``,
``RunResult``, ``Applicability``) lives in :mod:`tta.core.modules.base`.
"""

from __future__ import annotations

from dataclasses import dataclass

THESIS_TYPES = ("bachelor", "master", "unspecified")


@dataclass
class Thesis:
    """A thesis under analysis (SDD Sec. 6.1).

    Identity is content-addressed via ``pdf_sha256`` (ADR-0006), but the
    hash is computed lazily at first-run time (rev. 4, #38): it is ``None``
    for a thesis that has been added but not yet analysed. The path and
    filename are mutable, PII-bearing, local-only attributes.
    """

    id: int | None
    pdf_sha256: str | None
    pdf_path: str
    pdf_filename: str
    type: str = "unspecified"
    language_hint: str | None = None
    excluded: bool = False
