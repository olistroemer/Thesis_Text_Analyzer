"""Shared plain types crossing the core boundary (SDD §6.1, ADR-0002).

The module contract (``Module``, ``ModuleSpec``, ``RunContext``,
``RunResult``, ``Applicability``) lives in :mod:`pds.core.modules.base`.
"""

from __future__ import annotations

from dataclasses import dataclass

THESIS_TYPES = ("bachelor", "master", "unspecified")


@dataclass
class Thesis:
    """A thesis under analysis (SDD §6.1).

    Identity is content-addressed via ``pdf_sha256`` (ADR-0006): the path
    and filename are mutable, PII-bearing, local-only attributes.
    """

    id: int | None
    pdf_sha256: str
    pdf_path: str
    pdf_filename: str
    type: str = "unspecified"
    language_hint: str | None = None
    excluded: bool = False
