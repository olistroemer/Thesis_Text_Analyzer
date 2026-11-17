"""`mod_extract_pymupdf` - PDF text extraction, catalogue #1 (SDD Sec. 7.1).

PyMuPDF is AGPL; the project ships under a copyleft licence, so it may be
distributed (ADR-0017). This is the single file under ``tta/core/``
permitted to import it (CI invariant, SDD Sec. 5.2).

Two text views from one extraction pass (ADR-0024, #22): every page is
parsed once into a ``TextPage`` and serialised twice -

- ``raw_text``: its plain-text output, byte-identical to
  ``page.get_text("text")``; read by the detection modules;
- ``prose_text``: its span ``dict`` rebuilt line by line under "font filter
  v1" (Exp #22 arm B): monospaced spans (code) and math-font spans removed;
  read by the text metrics.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from tta.core import artefact_kinds
from tta.core.i18n import N_
from tta.core.modules._textio import write_text_artefact
from tta.core.modules.base import Applicability, Module, ModuleSpec, RunContext, RunResult
from tta.core.types import Thesis

#: Pages are joined with form feed, the `pdftotext` convention, so page
#: boundaries survive into both text views for alternative-extractor comparison.
PAGE_SEPARATOR = "\f"

#: PyMuPDF span flag bit for a monospaced font (``TEXT_FONT_MONOSPACED``).
FONT_MONOSPACED = 8

#: Removal categories, in precedence order: a span that is both monospaced
#: and set in a math font counts as monospace (SDD Sec. 7.4).
MONOSPACE = "monospace"
MATH = "math"

#: Math fonts: anything with "math" in the name (Cambria Math, STIX Two Math,
#: Latin Modern Math, LMMathItalic, XITS Math, ...) plus the TeX math font
#: families by name prefix (CMMI/CMMIB, CMSY/CMBSY, CMEX, AMS MSAM/MSBM,
#: Euler Fraktur, RSFS script, stmaryrd). ``Symbol`` is deliberately NOT
#: matched - Word uses it for bullets.
_MATH_FONT_RE = re.compile(r"math|^(cmmi|cmsy|cmbsy|cmex|msam|msbm|eufm|rsfs|stmary)", re.I)
_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")

#: How many fonts per category the diagnostics name (most characters first).
TOP_FONTS = 8


def font_base_name(font: str) -> str:
    """Font name without the 6-letter subset tag (``ABCDEF+CMMI10`` -> ``CMMI10``)."""
    return _SUBSET_PREFIX_RE.sub("", font or "")


def is_math_font(font: str) -> bool:
    return bool(_MATH_FONT_RE.search(font_base_name(font)))


def span_category(span: dict) -> str | None:
    """``MONOSPACE`` / ``MATH`` for a span to remove, ``None`` to keep it."""
    if span.get("flags", 0) & FONT_MONOSPACED:
        return MONOSPACE
    if is_math_font(span.get("font", "")):
        return MATH
    return None


def visible_len(text: str) -> int:
    """Non-whitespace characters - the unit of both removed-character counts."""
    return sum(1 for ch in text if not ch.isspace())


def filter_page(page_dict: dict, removed: Counter, fonts: dict[str, Counter]) -> str:
    """Rebuild one page's prose from a ``TextPage.extractDICT()`` result.

    Kept spans of a line are joined in order, as PyMuPDF's own plain text
    does; every kept line ends in a newline; a line whose spans were all
    removed disappears. ``removed`` and ``fonts`` accumulate the removed
    non-whitespace characters per category (and per font).
    """
    out = []
    for block in page_dict.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            kept = []
            for span in line.get("spans", []):
                category = span_category(span)
                if category is None:
                    kept.append(span["text"])
                    continue
                n = visible_len(span["text"])
                removed[category] += n
                if n:
                    fonts[category][font_base_name(span.get("font", ""))] += n
            if kept:
                out.append("".join(kept) + "\n")
    return "".join(out)


class ExtractPymupdf(Module):
    spec = ModuleSpec(
        name="mod_extract_pymupdf",
        version="0.2.0",  # 0.2.0: two text views, font filter v1 (#22, ADR-0024)
        consumes=(),
        produces_artefacts=(artefact_kinds.RAW_TEXT, artefact_kinds.PROSE_TEXT),
        produces_metrics=(
            "text_chars",
            "n_pages",
            "removed_monospace_chars",
            "removed_math_chars",
        ),
    )

    def applicable(self, thesis: Thesis) -> Applicability:
        if Path(thesis.pdf_path).suffix.lower() != ".pdf":
            return Applicability(ok=False, reason=N_("not a PDF"))
        return Applicability(ok=True)

    def run(self, ctx: RunContext) -> RunResult:
        import fitz  # PyMuPDF - lazy: keeps it out of catalogue construction

        removed: Counter = Counter({MONOSPACE: 0, MATH: 0})
        fonts: dict[str, Counter] = {MONOSPACE: Counter(), MATH: Counter()}
        raw_pages, prose_pages = [], []
        with fitz.open(ctx.thesis.pdf_path) as doc:
            for page in doc:
                # one parse per page; the same flags and crop box that
                # get_text("text") / get_text("dict") would use
                textpage = page.get_textpage(flags=fitz.TEXTFLAGS_TEXT)
                raw_pages.append(textpage.extractText())
                page_dict = textpage.extractDICT(cb=page.cropbox)
                prose_pages.append(filter_page(page_dict, removed, fonts))
        raw_text = PAGE_SEPARATOR.join(raw_pages)
        prose_text = PAGE_SEPARATOR.join(prose_pages)

        raw_path = ctx.workdir / "raw_text.txt"
        prose_path = ctx.workdir / "prose_text.txt"
        replaced = {
            artefact_kinds.RAW_TEXT: write_text_artefact(raw_path, raw_text),
            artefact_kinds.PROSE_TEXT: write_text_artefact(prose_path, prose_text),
        }
        return RunResult(
            metrics={
                "text_chars": len(prose_text),
                "n_pages": len(raw_pages),
                "removed_monospace_chars": removed[MONOSPACE],
                "removed_math_chars": removed[MATH],
            },
            artefacts={
                artefact_kinds.RAW_TEXT: raw_path,
                artefact_kinds.PROSE_TEXT: prose_path,
            },
            diagnostics={
                "surrogates_replaced": replaced,
                "removed_fonts_top": {
                    category: dict(counter.most_common(TOP_FONTS))
                    for category, counter in fonts.items()
                },
            },
        )
