"""Shared plain types crossing the core boundary (SDD Sec. 6.1, ADR-0002).

The module contract (``Module``, ``ModuleSpec``, ``RunContext``,
``RunResult``, ``Applicability``) lives in :mod:`tta.core.modules.base`.
"""

from __future__ import annotations

from dataclasses import dataclass

from tta.core.i18n import N_, _

#: The value set of the detected ``thesis_type`` metric (ADR-0019, #9). No
#: longer a ``theses`` column; kept here as the shared vocabulary used by
#: ``mod_classify_thesis_type`` and by the grid/report grouping. Rev. 3 (#82)
#: adds magister, mas (Master of Advanced Studies / Nachdiplom), licentiate,
#: semester (Semester-/Studienarbeit) and doctoral.
THESIS_TYPES = (
    "bachelor",
    "master",
    "diploma",
    "magister",
    "mas",
    "licentiate",
    "semester",
    "doctoral",
    "unspecified",
)

#: The types that enter reference-corpus statistics (#49, ADR-0019 rev. 3).
#: Every other detected type is reported to the user but kept out of the
#: reference baselines: the research question is about bachelor and master
#: theses, and the other classes are too rare to carry a baseline.
REFERENCE_THESIS_TYPES = ("bachelor", "master")

#: Display labels of the ``thesis_type`` values for the grid and the report
#: (ADR-0020: marked here, translated at use). The raw value stays the
#: identity everywhere else (DB, export, CLI, sorting keys).
THESIS_TYPE_LABELS: dict[str, str] = {
    "bachelor": N_("Bachelor"),
    "master": N_("Master"),
    "diploma": N_("Diploma"),
    "magister": N_("Magister"),
    "mas": N_("MAS (advanced studies)"),
    "licentiate": N_("Licentiate"),
    "semester": N_("Semester/study paper"),
    "doctoral": N_("Doctoral"),
    "unspecified": N_("Unspecified"),
}


def thesis_type_label(value: str) -> str:
    """The translated label of a ``thesis_type`` value; an unknown value (an
    imported export from a newer version) is shown as it is."""
    label = THESIS_TYPE_LABELS.get(value)
    return _(label) if label else value


@dataclass
class Thesis:
    """A thesis under analysis (SDD Sec. 6.1).

    Identity is content-addressed via ``pdf_sha256`` (ADR-0006), but the
    hash is computed lazily at first-run time (rev. 4, #38): it is ``None``
    for a thesis that has been added but not yet analysed. The path and
    filename are mutable, PII-bearing, local-only attributes. Thesis type
    and language are detected metrics, not attributes (ADR-0019, #9).
    """

    id: int | None
    pdf_sha256: str | None
    pdf_path: str
    pdf_filename: str
    excluded: bool = False
