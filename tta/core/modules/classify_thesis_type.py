"""`mod_classify_thesis_type` - catalogue #11 (SDD Sec. 7.1/7.4, ADR-0019, #9).

Detects the degree from the title page of `raw_text` with a lightweight,
case-insensitive, accent/umlaut-tolerant keyword heuristic (German + English) -
NOT ML. Produces the single `thesis_type` metric in {bachelor, master, diploma,
unspecified}; matched markers go into `notes` (no separate confidence metric).
`diploma` covers pre-Bologna German theses (#67, ADR-0019 rev. 2).

Mirrors `mod_classify_language`. Unlike it, garbled/sparse or keyword-free text
returns `unspecified` (a valid answer), never `NotApplicable` - the type metric
is always present so the grid/report can group by it. Replaces the removed
add-time type dialog and the dropped `theses.type` column; in-app correction of
a mis-detected value is deferred to editable metrics (#10).
"""

from __future__ import annotations

from tta.core import artefact_kinds
from tta.core.modules import _titlepage
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult

# Keyword sets in the normalised form produced by `_titlepage.normalise`
# (case-folded, apostrophes dropped, eszett -> ss, accents stripped). Bare
# ambiguous abbreviations ("ma", "msc" without a dot) are deliberately excluded
# to avoid false positives; the dotted forms below match "M.Sc."/"M. Sc.".
MASTER_KEYWORDS = (
    "masterarbeit",
    "master-arbeit",
    "masterthesis",
    "master thesis",
    "masters thesis",
    "master of science",
    "master of arts",
    "master of engineering",
    "m.sc",
    "m. sc",
    "m.eng",
)
BACHELOR_KEYWORDS = (
    "bachelorarbeit",
    "bachelor-arbeit",
    "bachelorthesis",
    "bachelor thesis",
    "bachelors thesis",
    "bachelor of science",
    "bachelor of arts",
    "bachelor of engineering",
    "b.sc",
    "b. sc",
    "b.eng",
)
# Pre-Bologna German theses (#67, ADR-0019 rev. 2). Bare "diplom" and "dipl."
# are deliberately absent: supervisor and examiner titles ("Betreuer:
# Dipl.-Inform. X", "Prof. Dr.-Ing. Dipl.-Ing. Y") sit inside the very same
# leading window, so either short form would mis-classify a Bachelor- or
# Masterarbeit. `normalise` does not strip hyphens, so hyphenated variants are
# spelled out. "diplom-ingenieur" survives because the abbreviated supervisor
# form that actually occurs is "Dipl.-Ing.", which does not contain it.
DIPLOMA_KEYWORDS = (
    "diplomarbeit",
    "diplom-arbeit",
    "diplomthesis",
    "diploma thesis",
    "diplom-ingenieur",
)

BACHELOR, MASTER, DIPLOMA, UNSPECIFIED = "bachelor", "master", "diploma", "unspecified"

#: Candidate classes in a fixed order. Ordering is only a tie-break for the
#: (practically unreachable) case of two markers starting at the same index;
#: the real decision is which marker appears earliest in the window.
TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (BACHELOR, BACHELOR_KEYWORDS),
    (DIPLOMA, DIPLOMA_KEYWORDS),
    (MASTER, MASTER_KEYWORDS),
)


class ClassifyThesisType(Module):
    spec = ModuleSpec(
        name="mod_classify_thesis_type",
        version="0.2.0",
        consumes=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("thesis_type",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        window = _titlepage.normalise(_titlepage.leading_window(text))

        hits: list[tuple[int, str]] = []
        notes: dict[str, object] = {"window_chars": len(window)}
        for name, keywords in TYPE_KEYWORDS:
            notes[f"{name}_markers"] = _titlepage.matched_keywords(window, keywords)
            at = _titlepage.first_index_of_any(window, keywords)
            if at is not None:
                hits.append((at, name))
        # several degrees named on the title page: the marker appearing first
        # wins (ADR-0019 rev. 2 - generalises the old pairwise comparison)
        decision = min(hits, key=lambda hit: hit[0])[1] if hits else UNSPECIFIED
        notes["thesis_type"] = decision

        return RunResult(metrics={"thesis_type": decision}, notes=notes)
