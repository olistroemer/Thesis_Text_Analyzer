"""`mod_determine_publication_year` - catalogue #12 (SDD Sec. 7.4, #17).

Best-estimate publication year - the x-axis of the primary research goal
(SDD Sec. 2.1: thesis length over publication date). Fuses signals by
precedence: (1) the in-text title-page year parsed from `raw_text` (most
reliable - the submission year printed on the page), then (2) the PDF-metadata
`creation_year`, then (3) `modification_year` (both re-parsed from the
`pdf_metadata` artefact). The winning signal is recorded in the
`publication_year_source` metric; fusion detail goes in `notes`.

When no signal is available the run is still `ok` with `publication_year` NULL
and source `none` - the report simply skips such theses on the time axis.
Filesystem dates (#18) are a possible future last-resort signal, out of scope.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from tta.core import artefact_kinds
from tta.core.modules import _titlepage
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult

_PDF_DATE_YEAR_RE = re.compile(r"^D:(\d{4})")

SOURCE_TITLE_PAGE = "title_page"
SOURCE_PDF_CREATION = "pdf_creation"
SOURCE_PDF_MODIFICATION = "pdf_modification"
SOURCE_NONE = "none"


def _pdf_year(info: dict, key: str) -> int | None:
    match = _PDF_DATE_YEAR_RE.match(str(info.get(key, "")))
    return int(match.group(1)) if match else None


class DeterminePublicationYear(Module):
    spec = ModuleSpec(
        name="mod_determine_publication_year",
        version="0.1.0",
        consumes=(artefact_kinds.RAW_TEXT, artefact_kinds.PDF_METADATA),
        produces_metrics=("publication_year", "publication_year_source"),
    )

    def run(self, ctx: RunContext) -> RunResult:
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        window = _titlepage.leading_window(text)
        # the most recent plausible year on the title page is the submission
        # year (older years tend to be citations); cap at next year to reject
        # stray future-looking digits.
        next_year = datetime.now(timezone.utc).year + 1
        in_text_candidates = _titlepage.find_years(window, lo=1900, hi=next_year)
        in_text_year = max(in_text_candidates) if in_text_candidates else None

        metadata = json.loads(
            ctx.artefacts[artefact_kinds.PDF_METADATA].read_text(encoding="utf-8")
        )
        info = metadata.get("info", {})
        creation_year = _pdf_year(info, "/CreationDate")
        modification_year = _pdf_year(info, "/ModDate")

        if in_text_year is not None:
            year, source = in_text_year, SOURCE_TITLE_PAGE
        elif creation_year is not None:
            year, source = creation_year, SOURCE_PDF_CREATION
        elif modification_year is not None:
            year, source = modification_year, SOURCE_PDF_MODIFICATION
        else:
            year, source = None, SOURCE_NONE

        return RunResult(
            metrics={"publication_year": year, "publication_year_source": source},
            notes={
                "publication_year": year,
                "source": source,
                "in_text_year": in_text_year,
                "in_text_candidates": in_text_candidates,
                "pdf_creation_year": creation_year,
                "pdf_modification_year": modification_year,
            },
        )
