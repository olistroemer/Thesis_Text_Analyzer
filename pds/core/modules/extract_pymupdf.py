"""`mod_extract_pymupdf` — PDF text extraction, catalogue #1 (SDD §7.1).

PyMuPDF is AGPL: development-phase only. This is the single file under
``pds/core/`` permitted to import it (CI invariant, SDD §5.2); the release
gate (ADR-0011, ADR-0014) blocks distributed builds until a non-AGPL
extractor replaces it.
"""

from __future__ import annotations

from pathlib import Path

from pds.core import artefact_kinds
from pds.core.modules.base import Applicability, Module, ModuleSpec, RunContext, RunResult
from pds.core.types import Thesis

#: Pages are joined with form feed, the `pdftotext` convention, so page
#: boundaries survive into `raw_text` for alternative-extractor comparison.
PAGE_SEPARATOR = "\f"


class ExtractPymupdf(Module):
    spec = ModuleSpec(
        name="mod_extract_pymupdf",
        version="0.1.0",
        consumes=(),
        produces_artefacts=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("text_chars", "n_pages"),
    )

    def applicable(self, thesis: Thesis) -> Applicability:
        if Path(thesis.pdf_path).suffix.lower() != ".pdf":
            return Applicability(ok=False, reason="not a PDF")
        return Applicability(ok=True)

    def run(self, ctx: RunContext) -> RunResult:
        import fitz  # PyMuPDF — lazy: the `pymupdf` extra is optional (dev-only, AGPL)

        with fitz.open(ctx.thesis.pdf_path) as doc:
            pages = [page.get_text("text") for page in doc]
        text = PAGE_SEPARATOR.join(pages)
        out_path = ctx.workdir / "raw_text.txt"
        out_path.write_text(text, encoding="utf-8")
        return RunResult(
            metrics={"text_chars": len(text), "n_pages": len(pages)},
            artefacts={artefact_kinds.RAW_TEXT: out_path},
        )
