"""`mod_classify_thesis_type` - catalogue #11 (SDD Sec. 7.1/7.4, ADR-0019, #9).

Detects the degree from the title page of `raw_text` with a lightweight,
case-insensitive, accent/umlaut-tolerant keyword heuristic (German + English) -
NOT ML. Produces the single `thesis_type` metric in {bachelor, master,
unspecified}; matched markers go into `notes` (no separate confidence metric).

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

BACHELOR, MASTER, UNSPECIFIED = "bachelor", "master", "unspecified"


class ClassifyThesisType(Module):
    spec = ModuleSpec(
        name="mod_classify_thesis_type",
        version="0.1.0",
        consumes=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("thesis_type",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        window = _titlepage.normalise(_titlepage.leading_window(text))

        master_at = _titlepage.first_index_of_any(window, MASTER_KEYWORDS)
        bachelor_at = _titlepage.first_index_of_any(window, BACHELOR_KEYWORDS)
        if master_at is None and bachelor_at is None:
            decision = UNSPECIFIED
        elif bachelor_at is None:
            decision = MASTER
        elif master_at is None:
            decision = BACHELOR
        else:
            # both named on the title page: the marker that appears first wins
            decision = MASTER if master_at < bachelor_at else BACHELOR

        return RunResult(
            metrics={"thesis_type": decision},
            notes={
                "thesis_type": decision,
                "master_markers": _titlepage.matched_keywords(window, MASTER_KEYWORDS),
                "bachelor_markers": _titlepage.matched_keywords(window, BACHELOR_KEYWORDS),
                "window_chars": len(window),
            },
        )
