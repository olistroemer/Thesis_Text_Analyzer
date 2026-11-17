"""`mod_extract_pymupdf` - PDF text extraction, catalogue #1 (SDD Sec. 7.1).

PyMuPDF is AGPL; the project ships under a copyleft licence, so it may be
distributed (ADR-0017). This is the single file under ``tta/core/``
permitted to import it (CI invariant, SDD Sec. 5.2).

Two text views from one extraction pass (ADR-0024, #22): every page is
parsed once into a ``TextPage`` and serialised twice -

- ``raw_text``: its plain-text output, byte-identical to
  ``page.get_text("text")``; read by the detection modules;
- ``prose_text``: its span ``dict`` rebuilt line by line under "font filter
  v1" (Exp #22 arm B): monospaced spans (code) and math-font spans removed,
  unless the whole-document guard finds that category to be the body font;
  read by the text metrics.

The guard needs document-wide counts, so pages are first classified (spans
tagged with their category) and rendered only after the last page.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
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

#: Whole-document guard (ADR-0024 decision 2a): a category holding more than
#: this share of a document's non-whitespace characters is not filtered for
#: that document. Exp #22 arm B (3,233 theses): largest genuine share 0.627
#: (monospace, listing appendix) / 0.279 (math); whole-document fonts 0.932
#: (Courier body) / 0.963 (Cambria Math body).
GUARD_SHARE = 0.80


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


#: One page as lines of ``(span text, category)``; category ``None`` = prose.
PageLines = list[list[tuple[str, str | None]]]


@dataclass
class FilterTally:
    """Document-wide counts the guard and the metrics are computed from.

    All counts are non-whitespace characters: ``visible`` over every span,
    ``candidates`` / ``fonts`` over the spans of each removal category.
    """

    visible: int = 0
    candidates: Counter = field(default_factory=lambda: Counter({MONOSPACE: 0, MATH: 0}))
    fonts: dict[str, Counter] = field(
        default_factory=lambda: {MONOSPACE: Counter(), MATH: Counter()}
    )


def classify_page(page_dict: dict, tally: FilterTally) -> PageLines:
    """Split one ``TextPage.extractDICT()`` result into lines of categorised
    spans, counting into ``tally``. Image blocks carry no text and are skipped."""
    lines: PageLines = []
    for block in page_dict.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = []
            for span in line.get("spans", []):
                category = span_category(span)
                n = visible_len(span["text"])
                tally.visible += n
                if category is not None:
                    tally.candidates[category] += n
                    if n:
                        tally.fonts[category][font_base_name(span.get("font", ""))] += n
                spans.append((span["text"], category))
            lines.append(spans)
    return lines


def guarded_categories(tally: FilterTally) -> dict[str, float]:
    """Categories the whole-document guard leaves in, with their share
    (ADR-0024 decision 2a): a category holding more than ``GUARD_SHARE`` of
    the document's characters is its body font, not code or math."""
    if not tally.visible:
        return {}
    shares = {c: tally.candidates[c] / tally.visible for c in (MONOSPACE, MATH)}
    return {c: share for c, share in shares.items() if share > GUARD_SHARE}


def render_page(lines: PageLines, keep: frozenset[str] = frozenset()) -> str:
    """Rebuild one page's prose: spans of no category, or of a category in
    ``keep``, are joined in order, as PyMuPDF's own plain text does; every
    kept line ends in a newline; a line whose spans were all removed
    disappears."""
    out = []
    for spans in lines:
        kept = [text for text, category in spans if category is None or category in keep]
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

        tally = FilterTally()
        raw_pages, classified = [], []
        with fitz.open(ctx.thesis.pdf_path) as doc:
            for page in doc:
                # one parse per page; the same flags and crop box that
                # get_text("text") / get_text("dict") would use
                textpage = page.get_textpage(flags=fitz.TEXTFLAGS_TEXT)
                raw_pages.append(textpage.extractText())
                page_dict = textpage.extractDICT(cb=page.cropbox)
                classified.append(classify_page(page_dict, tally))
        skipped = guarded_categories(tally)
        keep = frozenset(skipped)
        raw_text = PAGE_SEPARATOR.join(raw_pages)
        prose_text = PAGE_SEPARATOR.join(render_page(lines, keep) for lines in classified)
        removed = {c: 0 if c in keep else tally.candidates[c] for c in (MONOSPACE, MATH)}

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
                    for category, counter in tally.fonts.items()
                    if category not in keep
                },
                "filter_skipped": {
                    category: {
                        "share": round(share, 4),
                        "chars": tally.candidates[category],
                        "fonts_top": dict(tally.fonts[category].most_common(TOP_FONTS)),
                    }
                    for category, share in skipped.items()
                },
            },
        )
