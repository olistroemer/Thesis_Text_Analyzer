"""Privacy metadata as code - single source of truth (ADR-0009, QA-GDPR).

Every persisted user-originating value has an entry here; the technical
sections of the GDPR Art. 13 statement are rendered from this registry
by `tta privacy report`. A coverage gate (tests/core/test_privacy.py,
CI) fails when a schema column, registered module, or artefact kind is
missing - schema evolution and statement evolution cannot drift.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import tta


class Category(str, Enum):
    TECHNICAL = "technical"  # versions, durations, ids. No PII.
    CONTENT_HASH = "content_hash"  # cryptographic fingerprints. No PII.
    METRIC = "metric"  # numeric/textual analysis output.
    CONTENT = "content"  # raw or near-raw text - high PII risk.
    IDENTIFYING = "identifying"  # paths/filenames/notes - direct PII.


RETAIN_PROJECT = "until the user deletes the project folder"


@dataclass(frozen=True)
class Field:
    table: str
    column: str
    category: Category
    purpose: str
    exported: bool
    retention: str = RETAIN_PROJECT


@dataclass(frozen=True)
class ModuleEntry:
    name: str
    reads_categories: tuple[Category, ...]
    writes_categories: tuple[Category, ...]
    purpose: str


@dataclass(frozen=True)
class ArtefactKindEntry:
    kind: str
    category: Category
    description: str
    exported: bool  # always False for content/identifying kinds in MVP


def _f(table: str, column: str, category: Category, purpose: str, exported: bool) -> Field:
    return Field(table, column, category, purpose, exported)


FIELDS: tuple[Field, ...] = (
    # schema_version
    _f("schema_version", "version", Category.TECHNICAL, "track applied DB migrations", False),
    _f("schema_version", "applied_at", Category.TECHNICAL, "track applied DB migrations", False),
    # sources
    _f("sources", "id", Category.TECHNICAL, "key for grouping data by origin", True),
    _f("sources", "name", Category.TECHNICAL, "label of the data origin (institution-level, not personal)", True),
    _f("sources", "kind", Category.TECHNICAL, "distinguish own data from imported cohorts", True),
    _f("sources", "institution", Category.TECHNICAL, "cross-cohort grouping in the merged research DB", True),
    _f("sources", "app_version", Category.TECHNICAL, "reproducibility: which app produced the data", True),
    _f("sources", "schema_version", Category.TECHNICAL, "import compatibility check", True),
    _f("sources", "pipeline_summary", Category.TECHNICAL, "reproducibility: which modules ran", True),
    _f("sources", "created_at", Category.TECHNICAL, "audit trail", True),
    # theses
    _f("theses", "id", Category.TECHNICAL, "internal key", True),
    _f("theses", "source_id", Category.TECHNICAL, "origin of the thesis row", True),
    _f("theses", "pdf_sha256", Category.CONTENT_HASH, "content-addressed identity; survives renames; portable cross-export identifier", True),
    _f("theses", "pdf_size_bytes", Category.TECHNICAL, "coarse size statistics", True),
    _f("theses", "pdf_path", Category.IDENTIFYING, "re-open the file locally (may contain user/student names)", False),
    _f("theses", "pdf_filename", Category.IDENTIFYING, "display label in the grid (may contain student names)", False),
    _f("theses", "type", Category.TECHNICAL, "bachelor/master grouping (US-PROF-ATTRS)", True),
    _f("theses", "language_hint", Category.TECHNICAL, "user-provided language override", True),
    _f("theses", "excluded", Category.TECHNICAL, "confidential theses opt-out (US-PROF-EXCLUDE)", True),
    _f("theses", "notes", Category.IDENTIFYING, "free-form user notes", False),
    _f("theses", "tags", Category.IDENTIFYING, "free-form user tags", False),
    _f("theses", "added_at", Category.TECHNICAL, "audit trail (exported at day precision only)", True),
    # module_runs
    _f("module_runs", "id", Category.TECHNICAL, "internal key", True),
    _f("module_runs", "thesis_id", Category.TECHNICAL, "which thesis was analysed", True),
    _f("module_runs", "module_name", Category.TECHNICAL, "which analysis ran (QA-REPRO)", True),
    _f("module_runs", "module_version", Category.TECHNICAL, "staleness detection, reproducibility", True),
    _f("module_runs", "status", Category.TECHNICAL, "ok / not-applicable / error", True),
    _f("module_runs", "reason", Category.TECHNICAL, "why a run was na or errored (one line, no content)", True),
    _f("module_runs", "error_traceback", Category.IDENTIFYING, "debugging; may embed filesystem paths", False),
    _f("module_runs", "notes", Category.CONTENT, "module diagnostics; may contain content-derived values", False),
    _f("module_runs", "started_at", Category.TECHNICAL, "audit trail, profiling", True),
    _f("module_runs", "duration_ms", Category.TECHNICAL, "profiling (QA-RES budgets)", True),
    # metric_values
    _f("metric_values", "run_id", Category.TECHNICAL, "internal key", True),
    _f("metric_values", "metric_name", Category.TECHNICAL, "which metric", True),
    _f("metric_values", "value_num", Category.METRIC, "the research signal: numeric metric value", True),
    _f("metric_values", "value_text", Category.METRIC, "the research signal: categorical metric value", True),
    # artefact_files (table never exported)
    _f("artefact_files", "thesis_id", Category.TECHNICAL, "internal key", False),
    _f("artefact_files", "kind", Category.TECHNICAL, "artefact kind of the cached file", False),
    _f("artefact_files", "relative_path", Category.IDENTIFYING, "locate the cached file in the project folder", False),
    _f("artefact_files", "run_id", Category.TECHNICAL, "which run produced the cached file", False),
)


MODULES: tuple[ModuleEntry, ...] = (
    ModuleEntry("mod_extract_pymupdf", (Category.CONTENT,), (Category.CONTENT, Category.METRIC),
                "extract the plain text from the PDF; count pages and characters"),
    ModuleEntry("mod_check_extraction_quality", (Category.CONTENT,), (Category.METRIC,),
                "flag garbled or sparse text extractions so bad data is visible"),
    ModuleEntry("mod_classify_language", (Category.CONTENT,), (Category.METRIC,),
                "detect the thesis language to select language-aware analyses"),
    ModuleEntry("mod_tokenize", (Category.CONTENT,), (Category.CONTENT,),
                "split the text into sentences and words for counting modules"),
    ModuleEntry("mod_surface_counts", (Category.CONTENT,), (Category.METRIC,),
                "word/sentence/character counts and length statistics"),
    ModuleEntry("mod_vocabulary", (Category.CONTENT,), (Category.METRIC,),
                "vocabulary richness measures (TTR, hapax ratios, Yule's K)"),
    ModuleEntry("mod_readability", (Category.CONTENT,), (Category.METRIC,),
                "Flesch (en) / Amstad (de) reading-ease score"),
    ModuleEntry("mod_redundancy", (Category.CONTENT,), (Category.METRIC,),
                "repeated word-pair/triple rates"),
    ModuleEntry("mod_count_images", (Category.CONTENT,), (Category.METRIC,),
                "count embedded images in the PDF"),
    ModuleEntry("mod_extract_pdf_metadata", (Category.IDENTIFYING,), (Category.IDENTIFYING, Category.METRIC),
                "read PDF tool metadata; only categorised, year-precision values become metrics"),
)


ARTEFACT_KINDS: tuple[ArtefactKindEntry, ...] = (
    ArtefactKindEntry("raw_text", Category.CONTENT, "full extracted thesis text (UTF-8 file)", False),
    ArtefactKindEntry("language", Category.METRIC, "detected language code + confidence (JSON)", False),
    ArtefactKindEntry("tokens", Category.CONTENT, "sentence/word tokenisation of the full text (JSON)", False),
    ArtefactKindEntry("pdf_metadata", Category.IDENTIFYING, "complete PDF Info dict + XMP, incl. Author/Title (JSON)", False),
)


# -- report rendering ---------------------------------------------------------

_CATEGORY_LABELS = {
    Category.TECHNICAL: "Technical bookkeeping (no personal data)",
    Category.CONTENT_HASH: "Content fingerprints (no personal data recoverable)",
    Category.METRIC: "Analysis results (aggregated text statistics)",
    Category.CONTENT: "Document content (kept on this machine only)",
    Category.IDENTIFYING: "Directly identifying values (kept on this machine only)",
}


def render_report_md(rights_stub: str = "", controller_stub: str = "") -> str:
    """Sections 1-5 are generated from the registry; 6-7 are reviewed stubs."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Privacy statement - Thesis Text Analyzer",
        "",
        f"*Generated {now} by tta {tta.__version__} from `core/privacy_metadata.py`.*",
        "",
        "## 1. What we process",
        "",
    ]
    for category in Category:
        fields = [f for f in FIELDS if f.category is category]
        if not fields:
            continue
        lines.append(f"### {_CATEGORY_LABELS[category]}")
        lines.append("")
        lines.append("| Stored value | Purpose | Leaves your machine on export |")
        lines.append("|---|---|---|")
        for f in fields:
            lines.append(f"| `{f.table}.{f.column}` | {f.purpose} | {'yes' if f.exported else 'no'} |")
        lines.append("")

    lines += ["## 2. Module-level processing", "", "| Module | Reads | Produces | Purpose |", "|---|---|---|---|"]
    for m in MODULES:
        reads = ", ".join(c.value for c in m.reads_categories)
        writes = ", ".join(c.value for c in m.writes_categories)
        lines.append(f"| `{m.name}` | {reads} | {writes} | {m.purpose} |")

    lines += [
        "",
        "## 3. Cached files (never exported)",
        "",
        "| Kind | Category | Description |",
        "|---|---|---|",
    ]
    for k in ARTEFACT_KINDS:
        lines.append(f"| `{k.kind}` | {k.category.value} | {k.description} |")

    lines += [
        "",
        "## 4. Storage and retention",
        "",
        f"All data lives in the project folder on this machine and is retained {RETAIN_PROJECT}. "
        "The application is fully offline: it makes no network connections of any kind.",
        "",
        "## 5. What leaves your machine",
        "",
        "Only when you explicitly export, and only the following values:",
        "",
    ]
    for f in FIELDS:
        if f.exported:
            lines.append(f"- `{f.table}.{f.column}` - {f.purpose}")
    lines += [
        "",
        "Excluded theses, file paths and names, free-form notes and tags, raw text, "
        "tokenisations, full PDF metadata, error tracebacks, and module diagnostics "
        "never leave this machine.",
    ]
    if rights_stub:
        lines += ["", "## 6. Your rights under GDPR", "", rights_stub.strip()]
    if controller_stub:
        lines += ["", "## 7. Controller contact", "", controller_stub.strip()]
    lines.append("")
    return "\n".join(lines)


def render_report_json() -> str:
    return json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "app_version": tta.__version__,
            "fields": [
                {
                    "table": f.table,
                    "column": f.column,
                    "category": f.category.value,
                    "purpose": f.purpose,
                    "exported": f.exported,
                    "retention": f.retention,
                }
                for f in FIELDS
            ],
            "modules": [
                {
                    "name": m.name,
                    "reads_categories": [c.value for c in m.reads_categories],
                    "writes_categories": [c.value for c in m.writes_categories],
                    "purpose": m.purpose,
                }
                for m in MODULES
            ],
            "artefact_kinds": [
                {
                    "kind": k.kind,
                    "category": k.category.value,
                    "description": k.description,
                    "exported": k.exported,
                }
                for k in ARTEFACT_KINDS
            ],
        },
        indent=2,
    )
