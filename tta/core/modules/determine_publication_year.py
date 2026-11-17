"""`mod_determine_publication_year` - catalogue #12 (SDD Sec. 7.4, #17, #81).

Best-estimate publication year - the x-axis of the primary research goal
(SDD Sec. 2.1: thesis length over publication date). Fuses signals by
precedence: (1) the thesis date read from the title page and the three pages
after it under the date rules of ADR-0022 (`_dates`, catalogue in
`docs/titlepage-rules.md`), then (2) the PDF-metadata `creation_year`, then
(3) `modification_year` (both re-parsed from the `pdf_metadata` artefact).

Metrics: `publication_year`, `publication_year_source` (which signal won) and
`publication_date_precision` (what the winning statement supports: `day`,
`month`, `semester`, `year` or `year_range`; `year` for a PDF-metadata year).
Only the year and the precision become metrics - the day and month stay in the
local-only `diagnostics`, with the matched form, the deciding rule, the page,
the excluded candidates and what the cover rules did (ADR-0023).

When no signal is available the run is still `ok` with `publication_year` NULL
and source `none` - the report simply skips such theses on the time axis.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timezone

from tta.core import artefact_kinds
from tta.core.modules import _dates, _titlepage
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult

_PDF_DATE_YEAR_RE = re.compile(r"^D:(\d{4})")

SOURCE_TITLE_PAGE = "title_page"
SOURCE_PDF_CREATION = "pdf_creation"
SOURCE_PDF_MODIFICATION = "pdf_modification"
SOURCE_NONE = "none"

#: The title page and the three pages after it (#81: 97.5 % of the thesis
#: dates of the labelled sample first appear there).
WINDOW_PAGES = 4

#: Candidates listed in `diagnostics`, so a long front matter stays bounded.
MAX_LISTED_CANDIDATES = 40


def _pdf_year(info: dict, key: str) -> int | None:
    match = _PDF_DATE_YEAR_RE.match(str(info.get(key, "")))
    return int(match.group(1)) if match else None


class DeterminePublicationYear(Module):
    spec = ModuleSpec(
        name="mod_determine_publication_year",
        version="0.2.0",
        consumes=(artefact_kinds.RAW_TEXT, artefact_kinds.PDF_METADATA),
        produces_metrics=(
            "publication_year",
            "publication_year_source",
            "publication_date_precision",
        ),
    )

    def __init__(self, cover_rules: _titlepage.CoverRuleset | None = None):
        # ADR-0023: no cover rules by default; a researcher ruleset changes
        # the effective version so its runs are never mixed with default ones
        self.cover_rules = cover_rules
        if cover_rules is not None:
            self.spec = replace(
                type(self).spec, version=_titlepage.versioned(type(self).spec.version, cover_rules)
            )

    def run(self, ctx: RunContext) -> RunResult:
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        front = _titlepage.front_matter(text, self.cover_rules)
        title_page = front.title_page()
        # cap at next year to reject stray future-looking digits
        max_year = datetime.now(timezone.utc).year + 1
        if title_page is None:
            decision = _dates.Decision(None, None, [])
        else:
            window = list(front.pages[title_page : title_page + WINDOW_PAGES])
            decision = _dates.pick(window, max_year)

        metadata = json.loads(
            ctx.artefacts[artefact_kinds.PDF_METADATA].read_text(encoding="utf-8")
        )
        info = metadata.get("info", {})
        creation_year = _pdf_year(info, "/CreationDate")
        modification_year = _pdf_year(info, "/ModDate")

        winner = decision.winner
        if winner is not None:
            year, source, precision = winner.reported_year, SOURCE_TITLE_PAGE, winner.precision
        elif creation_year is not None:
            year, source, precision = creation_year, SOURCE_PDF_CREATION, _dates.YEAR_PRECISION
        elif modification_year is not None:
            year, source, precision = (
                modification_year,
                SOURCE_PDF_MODIFICATION,
                _dates.YEAR_PRECISION,
            )
        else:
            year, source, precision = None, SOURCE_NONE, None

        diagnostics: dict[str, object] = {
            "publication_year": year,
            "source": source,
            "precision": precision,
            "rules": "date rules v1 (ADR-0022)",
            "title_page": title_page,
            "window_pages": WINDOW_PAGES,
            "title_page_date": None,
            "candidates": [
                {
                    "page": c.page,
                    "form": c.form,
                    "surface": c.surface,
                    "year": c.reported_year,
                    "rejected": reason,
                }
                for c, reason in decision.considered[:MAX_LISTED_CANDIDATES]
            ],
            "pdf_creation_year": creation_year,
            "pdf_modification_year": modification_year,
            **_titlepage.cover_diagnostics(front, self.cover_rules),
        }
        if winner is not None:
            diagnostics["title_page_date"] = {
                "date": winner.iso(),
                "form": winner.form,
                "rule": decision.rule,
                "surface": winner.surface,
                "page": winner.page,
                "page_index": title_page + winner.page,
                "precision": winner.precision,
            }

        return RunResult(
            metrics={
                "publication_year": year,
                "publication_year_source": source,
                "publication_date_precision": precision,
            },
            diagnostics=diagnostics,
        )
