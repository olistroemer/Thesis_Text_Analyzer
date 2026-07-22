"""Grid column model (SDD Sec. 9.2/Sec. 9.3): lead columns + metric columns
derived from the module catalogue; basic mode shows a curated subset."""

from __future__ import annotations

from dataclasses import dataclass

from tta.core.modules.registry import ModuleRegistry

LEAD_COLUMNS = ("file", "type")

#: Curated basic-mode metric subset (Sec. 9.3 "limited columns visible by default").
BASIC_METRICS = (
    "n_pages",
    "language_code",
    "word_count",
    "flesch_reading_ease",
    "yules_k",
    "extraction_quality",
)

#: One-line column-header explanations for the hover tooltips (Sec. 9.9). ASCII
#: only (ADR-0018). Keyed by the raw column name, so the sort suffix that the
#: grid appends to headers (" (asc)"/" (desc)") is irrelevant here.
COLUMN_HELP: dict[str, str] = {
    # lead columns
    "file": "File name of the thesis PDF. Double-click to open the PDF.",
    "type": "Thesis type, e.g. bachelor or master.",
    # artefact presence columns (extended mode)
    "raw_text": "Cached extracted plain text. Double-click to open it.",
    "language": "Cached language-detection artefact. Double-click to open it.",
    "tokens": "Cached tokenisation artefact. Double-click to open it.",
    "pdf_metadata": "Cached full PDF metadata artefact. Double-click to open it.",
    # metrics
    "text_chars": "Number of characters in the text extracted from the PDF.",
    "n_pages": "Page count from the PDF text layer.",
    "n_images": "Number of embedded images detected in the PDF.",
    "page_count_meta": "Page count reported by the PDF's own metadata.",
    "producer_category": "Category of the PDF 'Producer' tool (e.g. LaTeX, Word).",
    "creator_category": "Category of the PDF 'Creator' tool (e.g. LaTeX, Word).",
    "creation_year": "Year the PDF was created, from its metadata.",
    "modification_year": "Year the PDF was last modified, from its metadata.",
    "has_outline": "Whether the PDF carries a bookmarks/outline tree.",
    "extraction_quality": "Verdict on how reliable the extracted text is (ok vs garbled).",
    "language_code": "Detected primary language as an ISO 639 code.",
    "language_confidence": "Confidence of the language detection, from 0 to 1.",
    "flesch_reading_ease": "Flesch Reading Ease; higher scores read more easily.",
    "word_count": "Total number of words in the extracted text.",
    "char_count_alpha": "Number of alphabetic characters in the text.",
    "sentence_count": "Total number of sentences detected.",
    "avg_word_len": "Average word length, in characters.",
    "avg_sentence_len": "Average sentence length, in words.",
    "std_sentence_len": "Standard deviation of sentence length, in words.",
    "ttr": "Type-token ratio: distinct words divided by total words.",
    "root_ttr": "Root type-token ratio (Guiraud's index); length-robust richness.",
    "hapax_token_ratio": "Share of tokens that occur exactly once.",
    "hapax_type_ratio": "Share of word types that occur exactly once.",
    "yules_k": "Yule's K: vocabulary richness, robust to text length.",
    "bigram_repetition_rate": "Fraction of repeated word bigrams (two-word runs).",
    "trigram_repetition_rate": "Fraction of repeated word trigrams (three-word runs).",
}


def column_help(name: str) -> str | None:
    """Header tooltip for a column by its raw name, or None if unknown."""
    return COLUMN_HELP.get(name)


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
