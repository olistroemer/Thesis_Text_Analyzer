"""`mod_extract_filesystem_metadata` - catalogue #13 (SDD Sec. 7.1/7.4, #18).

A root module reading the PDF path directly (like `mod_count_images`) via
stdlib ``os.stat``. Promotes exactly two metrics:

* ``file_size_bytes`` - size observed at RUN time. An independent second
  observation of the add-time ``theses.pdf_size_bytes`` column, so a file
  swapped between adding and analysing becomes visible.
* ``fs_modified_year`` - mtime at year precision, matching the privacy
  posture of `mod_extract_pdf_metadata`'s dates (no day, no clock time).

Reliability caveat (SDD Sec. 7.4): filesystem timestamps describe *this
machine's copy of the file*, not the thesis - copying, downloading,
unzipping or syncing resets them - so ``fs_modified_year`` is at best a
loose upper bound on the submission year. It is surfaced as its own
labelled metric and is deliberately NOT a precedence step in
`mod_determine_publication_year` (#17).

atime and ctime are deliberately NOT promoted:

* ``st_atime`` is worthless - ``noatime``/``relatime`` mount options
  commonly disable it, and merely reading the PDF during analysis updates
  it, so the metric would partly measure tta itself.
* ``st_ctime`` is not one fact but two - creation time on Windows, inode
  change time on POSIX - and ``st_birthtime`` does not exist on Linux, so
  one metric name would carry incomparable meanings across the platforms
  the app ships on (ADR-0014).

Both are kept at full precision in the run's local-only ``diagnostics`` so the
discarded signals stay inspectable on the machine that produced them
without becoming exportable metrics.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from tta.core.i18n import N_
from tta.core.modules.base import Applicability, Module, ModuleSpec, RunContext, RunResult
from tta.core.types import Thesis


def _year_of(epoch_seconds: float) -> int:
    """Calendar year of a POSIX timestamp, in UTC.

    UTC rather than local time so the metric does not silently change
    value when the same project is opened in another timezone (QA-REPRO).
    """
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).year


class ExtractFilesystemMetadata(Module):
    spec = ModuleSpec(
        name="mod_extract_filesystem_metadata",
        version="0.1.0",
        produces_metrics=("file_size_bytes", "fs_modified_year"),
    )

    def applicable(self, thesis: Thesis) -> Applicability:
        # Only needs the Thesis row, so it belongs here rather than in run()
        # (base.py). The path is PII and never leaves the reason string.
        if not Path(thesis.pdf_path).exists():
            return Applicability(ok=False, reason=N_("file not found"))
        return Applicability(ok=True)

    def run(self, ctx: RunContext) -> RunResult:
        stat = os.stat(ctx.thesis.pdf_path)
        return RunResult(
            metrics={
                "file_size_bytes": stat.st_size,
                "fs_modified_year": _year_of(stat.st_mtime),
            },
            diagnostics={
                # Local-only, full precision: the signals not promoted to
                # metrics stay inspectable here (SDD Sec. 7.4).
                "st_size": stat.st_size,
                "st_mtime": stat.st_mtime,
                "st_atime": stat.st_atime,
                "st_ctime": stat.st_ctime,
                "st_birthtime": getattr(stat, "st_birthtime", None),
                "platform": os.name,
                "caveat": (
                    "filesystem timestamps describe this machine's copy of the file; "
                    "copying/downloading resets them (SDD Sec. 7.4, #18)"
                ),
            },
        )
