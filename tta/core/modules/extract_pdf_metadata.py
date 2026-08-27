"""`mod_extract_pdf_metadata` - catalogue #10 (SDD Sec. 7.1, Sec. 7.4).

Writes the full PDF Info dict + XMP (potentially identifying: Author,
Title) to the local-only `pdf_metadata` artefact, but promotes only six
curated, safe metrics. Producer/Creator strings are mapped to a small
categorical - the raw strings never reach the DB; dates are stored to
year precision only. Extra technical fields stay in the artefact
(SDD Sec. 12: promotion is purely additive).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader

from tta.core import artefact_kinds
from tta.core.i18n import N_
from tta.core.modules.base import Applicability, Module, ModuleSpec, RunContext, RunResult
from tta.core.types import Thesis

#: Ordered (category, substring-markers) - first match wins.
_TOOL_CATEGORIES = (
    ("latex", ("latex", "pdftex", "xetex", "luatex", "dvips", "miktex", "tex live")),
    ("word", ("microsoft", "word")),
    ("libreoffice", ("libreoffice",)),
    ("openoffice", ("openoffice",)),
    ("indesign", ("indesign",)),
    ("ghostscript", ("ghostscript",)),
)

_DATE_YEAR_RE = re.compile(r"^D:(\d{4})")


def categorize_tool(raw: str | None) -> str:
    if not raw or not raw.strip():
        return "unknown"
    lowered = raw.lower()
    for category, markers in _TOOL_CATEGORIES:
        if any(marker in lowered for marker in markers):
            return category
    return "other"


def _year_of(info: dict[str, str], key: str) -> int | None:
    match = _DATE_YEAR_RE.match(info.get(key, ""))
    return int(match.group(1)) if match else None


class ExtractPdfMetadata(Module):
    spec = ModuleSpec(
        name="mod_extract_pdf_metadata",
        version="0.1.0",
        produces_artefacts=(artefact_kinds.PDF_METADATA,),
        produces_metrics=(
            "page_count_meta",
            "producer_category",
            "creator_category",
            "creation_year",
            "modification_year",
            "has_outline",
        ),
    )

    def applicable(self, thesis: Thesis) -> Applicability:
        if Path(thesis.pdf_path).suffix.lower() != ".pdf":
            return Applicability(ok=False, reason=N_("not a PDF"))
        return Applicability(ok=True)

    def run(self, ctx: RunContext) -> RunResult:
        reader = PdfReader(ctx.thesis.pdf_path)
        info = {str(k): str(v) for k, v in (reader.metadata or {}).items()}

        try:
            xmp = reader.xmp_metadata
            xmp_raw = xmp.stream.get_data().decode("utf-8", "replace") if xmp else None
        except Exception:
            xmp_raw = None
        try:
            has_outline = len(reader.outline) > 0
        except Exception:
            has_outline = False
        try:
            root = reader.trailer["/Root"]
            acroform = root.get("/AcroForm")
            has_acroform = acroform is not None
            has_xfa = bool(acroform is not None and acroform.get("/XFA") is not None)
        except Exception:
            has_acroform = has_xfa = False

        artefact = {
            "info": info,  # full, including Author/Title - local only, never exported
            "xmp": xmp_raw,
            # technical fields kept here, not promoted to metrics (SDD Sec. 12)
            "pdf_version": reader.pdf_header,
            "is_encrypted": reader.is_encrypted,
            "xmp_present": xmp_raw is not None,
            "has_acroform": has_acroform,
            "has_xfa": has_xfa,
        }
        out_path = ctx.workdir / "pdf_metadata.json"
        out_path.write_text(json.dumps(artefact, ensure_ascii=False), encoding="utf-8")

        return RunResult(
            metrics={
                "page_count_meta": len(reader.pages),
                "producer_category": categorize_tool(info.get("/Producer")),
                "creator_category": categorize_tool(info.get("/Creator")),
                "creation_year": _year_of(info, "/CreationDate"),
                "modification_year": _year_of(info, "/ModDate"),
                "has_outline": has_outline,
            },
            artefacts={artefact_kinds.PDF_METADATA: out_path},
        )
