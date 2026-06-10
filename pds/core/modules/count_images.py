"""`mod_count_images` — catalogue #9 (SDD §7.1).

Counts embedded image XObjects via pypdf. A POC for smarter figure
analysis (SDD §12): fragments are not clustered, so vector-heavy theses
under-count and tiled rasters over-count.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from pds.core.modules.base import Applicability, Module, ModuleSpec, RunContext, RunResult
from pds.core.types import Thesis


class CountImages(Module):
    spec = ModuleSpec(
        name="mod_count_images",
        version="0.1.0",
        produces_metrics=("n_images",),
    )

    def applicable(self, thesis: Thesis) -> Applicability:
        if Path(thesis.pdf_path).suffix.lower() != ".pdf":
            return Applicability(ok=False, reason="not a PDF")
        return Applicability(ok=True)

    def run(self, ctx: RunContext) -> RunResult:
        reader = PdfReader(ctx.thesis.pdf_path)
        n_images = sum(len(page.images) for page in reader.pages)
        return RunResult(metrics={"n_images": n_images})
