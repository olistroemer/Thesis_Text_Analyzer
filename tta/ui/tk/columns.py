"""Grid column model (SDD Sec. 9.2/Sec. 9.3): lead columns + metric columns
derived from the module catalogue; basic mode shows a curated subset.

The column help text is English ASCII msgids (ADR-0018) resolved through
``_()`` (ADR-0020), so the German UI is a catalog entry rather than a second
table here.
"""

from __future__ import annotations

from dataclasses import dataclass

from tta.core.i18n import N_, _
from tta.core.modules.registry import ModuleRegistry

# The four lead columns shown in BOTH modes (SDD Sec. 9.3 "Column sets").
# "excluded" leads: it is a professor-facing privacy control, not a power-user
# feature (US-PROF-EXCLUDE, SDD Sec. 9.2, #11). "state" is the per-row file /
# extraction state, in its own column so the marker is sortable and does not
# shift the file names horizontally row to row (Sec. 9.9, #65).
LEAD_COLUMNS = ("excluded", "state", "file", "type")

#: Artefact-presence columns, extended mode only (Sec. 9.2). Named here so
#: the grid, the sort keys and COLUMN_HELP all agree on the set and order.
ARTEFACT_COLUMNS = ("raw_text", "language", "tokens", "pdf_metadata")

#: Curated basic-mode metric subset (Sec. 9.3 "limited columns visible by default").
BASIC_METRICS = (
    "n_pages",
    # The publication year is the project's primary research axis (Sec. 2.1) and
    # the professor persona defaults to basic mode, so it must be visible without
    # switching modes (Sec. 9.3, #65).
    "publication_year",
    "language_code",
    "word_count",
    "flesch_reading_ease",
    "yules_k",
    "extraction_quality",
)

#: One-line column-header explanations, shown in the details panel (Sec. 9.9).
#: The grid has no hover tooltips any more (#66) but the text outlived them.
#: English ASCII msgids (ADR-0018); marked here, translated at use (ADR-0020).
#: Keyed by the raw column name, so the sort suffix that the grid appends to
#: headers (" (asc)"/" (desc)") is irrelevant here.
COLUMN_HELP: dict[str, str] = {
    # lead columns
    "excluded": N_(
        "Exclude this thesis from analysis and exports. Excluding an already-"
        "analysed thesis deletes its cached analysis (artefacts + metrics) from "
        "this machine after a confirmation; the source PDF is not touched."
    ),
    "state": N_(
        "Per-row state. '[!]' means text extraction was flagged as garbled for "
        "this thesis, so every metric in this row may be unreliable "
        "(US-PROF-QUALITY); blank means no problem was detected."
    ),
    "file": N_("File name of the thesis PDF. Double-click to open the PDF."),
    "type": N_(
        "Detected thesis type (bachelor / master / unspecified); blank until analysed."
    ),
    # artefact presence columns (extended mode)
    "raw_text": N_("Cached extracted plain text. Double-click to open it."),
    "language": N_("Cached language-detection artefact. Double-click to open it."),
    "tokens": N_("Cached tokenisation artefact. Double-click to open it."),
    "pdf_metadata": N_("Cached full PDF metadata artefact. Double-click to open it."),
    # metrics
    "text_chars": N_("Number of characters in the text extracted from the PDF."),
    "n_pages": N_("Page count from the PDF text layer."),
    "n_images": N_("Number of embedded images detected in the PDF."),
    "page_count_meta": N_("Page count reported by the PDF's own metadata."),
    "producer_category": N_("Category of the PDF 'Producer' tool (e.g. LaTeX, Word)."),
    "creator_category": N_("Category of the PDF 'Creator' tool (e.g. LaTeX, Word)."),
    "creation_year": N_("Year the PDF was created, from its metadata."),
    "modification_year": N_("Year the PDF was last modified, from its metadata."),
    "publication_year": N_(
        "Best-estimate publication year (title-page year, else PDF dates)."
    ),
    "publication_year_source": N_(
        "Which signal set the publication year (title page vs PDF metadata)."
    ),
    "has_outline": N_("Whether the PDF carries a bookmarks/outline tree."),
    "extraction_quality": N_(
        "Verdict on how reliable the extracted text is (ok vs garbled)."
    ),
    "thesis_type": N_(
        "Detected degree from the title page: bachelor, master, or unspecified."
    ),
    "language_code": N_("Detected primary language as an ISO 639 code."),
    "language_confidence": N_("Confidence of the language detection, from 0 to 1."),
    "flesch_reading_ease": N_("Flesch Reading Ease; higher scores read more easily."),
    "word_count": N_("Total number of words in the extracted text."),
    "char_count_alpha": N_("Number of alphabetic characters in the text."),
    "sentence_count": N_("Total number of sentences detected."),
    "avg_word_len": N_("Average word length, in characters."),
    "avg_sentence_len": N_("Average sentence length, in words."),
    "std_sentence_len": N_("Standard deviation of sentence length, in words."),
    "ttr": N_("Type-token ratio: distinct words divided by total words."),
    "root_ttr": N_("Root type-token ratio (Guiraud's index); length-robust richness."),
    "hapax_token_ratio": N_("Share of tokens that occur exactly once."),
    "hapax_type_ratio": N_("Share of word types that occur exactly once."),
    "yules_k": N_("Yule's K: vocabulary richness, robust to text length."),
    "bigram_repetition_rate": N_("Fraction of repeated word bigrams (two-word runs)."),
    "trigram_repetition_rate": N_(
        "Fraction of repeated word trigrams (three-word runs)."
    ),
}


def column_help(name: str) -> str | None:
    """Details-panel help for a column by its raw name, or None if unknown."""
    text = COLUMN_HELP.get(name)
    return _(text) if text else None


@dataclass(frozen=True)
class MetricColumn:
    metric: str
    module: str


def metric_columns(registry: ModuleRegistry, extended: bool) -> list[MetricColumn]:
    columns = [
        MetricColumn(metric=metric, module=module.spec.name)
        for module in registry.in_topological_order()
        for metric in module.spec.produces_metrics
    ]
    if extended:
        return columns
    by_name = {c.metric: c for c in columns}
    return [by_name[m] for m in BASIC_METRICS if m in by_name]
