"""Grid column model (SDD Sec. 9.2/Sec. 9.3): lead columns + metric columns
derived from the module catalogue; basic mode shows a curated subset.

Also the interim source of the **human-friendly column labels** (#16,
US-PROF-EXPLAIN): the grid headers, the details panel and the help viewer all
show "Readability (Flesch)" rather than ``flesch_reading_ease``. Labels and
help text are English ASCII msgids (ADR-0018) resolved through ``_()``
(ADR-0020), so the German UI is a catalog entry, not a second table here.

ADR-0012 wanted each help page's front-matter ``title:`` to become the durable
label source. #2 authored the corpus and the migration is blocked, not pending
(ADR-0020 Sec. 8): a German-only corpus (SDD Sec. 9.6) cannot source an English
label, while this dict plus the catalog carry both. Titles are worded to match.
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
ARTEFACT_COLUMNS = ("raw_text", "prose_text", "language", "tokens", "pdf_metadata")

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

#: Human-friendly column headers (#16, US-PROF-EXPLAIN). Keyed by the raw
#: column name; the raw name stays the column *identity* (sort keys, the DB,
#: the export) and stays visible in the details panel, so nothing about the
#: label is load-bearing. Marked with N_() because this dict is built at import
#: time, before any locale is resolved.
COLUMN_LABELS: dict[str, str] = {
    # lead columns
    "excluded": N_("Excluded"),
    "state": N_("State"),
    "file": N_("File"),
    "type": N_("Type"),
    # artefact presence columns (extended mode). Named "Cached ..." so they do
    # not collide with the metric on the same subject - the `language`
    # artefact column and the `language_code` metric sit side by side.
    "raw_text": N_("Cached text"),
    "prose_text": N_("Cached prose text"),
    "language": N_("Cached language"),
    "tokens": N_("Cached tokens"),
    "pdf_metadata": N_("Cached PDF metadata"),
    # metrics
    "text_chars": N_("Characters (extracted)"),
    "n_pages": N_("Pages"),
    "removed_monospace_chars": N_("Removed characters (monospace)"),
    "removed_math_chars": N_("Removed characters (math fonts)"),
    "n_images": N_("Images"),
    "page_count_meta": N_("Pages (PDF metadata)"),
    "producer_category": N_("Producer tool"),
    "creator_category": N_("Creator tool"),
    "creation_year": N_("Created (year)"),
    "modification_year": N_("Modified (year)"),
    "publication_year": N_("Publication year"),
    "publication_year_source": N_("Publication year source"),
    "publication_date_precision": N_("Publication date precision"),
    "has_outline": N_("Bookmarks"),
    "extraction_quality": N_("Extraction quality"),
    "thesis_type": N_("Thesis type"),
    "language_code": N_("Language"),
    "language_confidence": N_("Language confidence"),
    "flesch_reading_ease": N_("Readability (Flesch)"),
    "word_count": N_("Words"),
    "char_count_alpha": N_("Letters"),
    "sentence_count": N_("Sentences"),
    "avg_word_len": N_("Avg. word length"),
    "avg_sentence_len": N_("Avg. sentence length"),
    "std_sentence_len": N_("Sentence length variation"),
    "ttr": N_("Vocabulary richness (TTR)"),
    "root_ttr": N_("Vocabulary richness (Guiraud)"),
    "hapax_token_ratio": N_("Once-only words (of tokens)"),
    "hapax_type_ratio": N_("Once-only words (of types)"),
    "yules_k": N_("Vocabulary richness (Yule's K)"),
    "bigram_repetition_rate": N_("Repeated word pairs"),
    "trigram_repetition_rate": N_("Repeated word triples"),
    "file_size_bytes": N_("File size"),
    "fs_modified_year": N_("File modified (year)"),
}

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
        "Detected thesis type (bachelor, master, diploma, magister, ...); "
        "blank until analysed."
    ),
    # artefact presence columns (extended mode)
    "raw_text": N_("Cached extracted plain text. Double-click to open it."),
    "prose_text": N_(
        "Cached extracted text without code and formulas, the input of the "
        "text metrics. Double-click to open it."
    ),
    "language": N_("Cached language-detection artefact. Double-click to open it."),
    "tokens": N_("Cached tokenisation artefact. Double-click to open it."),
    "pdf_metadata": N_("Cached full PDF metadata artefact. Double-click to open it."),
    # metrics
    "text_chars": N_(
        "Number of characters in the text extracted from the PDF, without "
        "code and formulas."
    ),
    "n_pages": N_("Page count from the PDF text layer."),
    "removed_monospace_chars": N_(
        "Characters removed from the text because they are set in a "
        "monospaced font (code, often also URLs)."
    ),
    "removed_math_chars": N_(
        "Characters removed from the text because they are set in a math "
        "font (formulas)."
    ),
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
    "publication_date_precision": N_(
        "How precise the date behind the publication year is: day, month, "
        "semester, year or year range."
    ),
    "has_outline": N_("Whether the PDF carries a bookmarks/outline tree."),
    "extraction_quality": N_(
        "Verdict on how reliable the extracted text is (ok vs garbled)."
    ),
    "thesis_type": N_(
        "Detected degree from the first pages: bachelor, master, diploma, "
        "magister, MAS, licentiate, semester paper, doctoral or unspecified."
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
    # #18's two filesystem metrics shipped without help entries; the details
    # panel had nothing to say about them (found while adding the #16 labels).
    "file_size_bytes": N_("Size of the PDF file on disk, in bytes."),
    "fs_modified_year": N_(
        "Year the file was last modified on disk. A weak signal: copying or "
        "downloading a file resets it, so it is not used for the publication "
        "year."
    ),
}


def column_help(name: str) -> str | None:
    """Details-panel help for a column by its raw name, or None if unknown."""
    text = COLUMN_HELP.get(name)
    return _(text) if text else None


def column_label(name: str) -> str:
    """Human-friendly header for a column by its raw name (#16).

    Falls back to the raw name, which is the honest thing to show for a metric
    a contributed module added without a label - and keeps the grid readable
    rather than blank.
    """
    label = COLUMN_LABELS.get(name)
    return _(label) if label else name


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
