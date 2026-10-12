"""Privacy metadata as code - single source of truth (ADR-0009, QA-GDPR).

Every persisted user-originating value has an entry here; the technical
sections of the GDPR Art. 13 statement are rendered from this registry
by `tta privacy report`. A coverage gate (tests/core/test_privacy.py,
CI) fails when a schema column, registered module, or artefact kind is
missing - schema evolution and statement evolution cannot drift.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from importlib import resources

import tta
from tta.core.i18n import DEFAULT_LOCALE, N_, _, active_locale, normalise_locale


class Category(str, Enum):
    TECHNICAL = "technical"  # versions, durations, ids. No PII.
    CONTENT_HASH = "content_hash"  # cryptographic fingerprints. No PII.
    METRIC = "metric"  # numeric/textual analysis output.
    CONTENT = "content"  # raw or near-raw text - high PII risk.
    IDENTIFYING = "identifying"  # paths/filenames/notes - direct PII.


# Registry prose is English and ASCII (ADR-0018) because the SAME registry
# feeds `render_report_json()`, a machine-readable artefact whose wording is a
# contract. N_() marks it; `render_report_md` translates it on the way to the
# rendered statement, so the GDPR statement follows the active locale
# (SDD Sec. 9.6) while the JSON stays stable (ADR-0020).
RETAIN_PROJECT = N_("until the user deletes the project folder")


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
    _f("schema_version", "version", Category.TECHNICAL, N_("track applied DB migrations"), False),
    _f("schema_version", "applied_at", Category.TECHNICAL, N_("track applied DB migrations"), False),
    # sources
    _f("sources", "id", Category.TECHNICAL, N_("key for grouping data by origin"), True),
    _f("sources", "name", Category.TECHNICAL, N_("label of the data origin (institution-level, not personal)"), True),
    _f("sources", "kind", Category.TECHNICAL, N_("distinguish own data from imported cohorts"), True),
    _f("sources", "institution", Category.TECHNICAL, N_("cross-cohort grouping in the merged research DB"), True),
    _f("sources", "app_version", Category.TECHNICAL, N_("reproducibility: which app produced the data"), True),
    _f("sources", "schema_version", Category.TECHNICAL, N_("import compatibility check"), True),
    _f("sources", "pipeline_summary", Category.TECHNICAL, N_("reproducibility: which modules ran"), True),
    _f("sources", "created_at", Category.TECHNICAL, N_("audit trail"), True),
    # theses
    _f("theses", "id", Category.TECHNICAL, N_("internal key"), True),
    _f("theses", "source_id", Category.TECHNICAL, N_("origin of the thesis row"), True),
    _f("theses", "pdf_sha256", Category.CONTENT_HASH, N_("content-addressed identity; computed at first run (NULL until then); survives renames; portable cross-export identifier"), True),
    _f("theses", "pdf_size_bytes", Category.TECHNICAL, N_("coarse size statistics"), True),
    _f("theses", "pdf_path", Category.IDENTIFYING, N_("re-open the file locally (may contain user/student names)"), False),
    _f("theses", "pdf_filename", Category.IDENTIFYING, N_("display label in the grid (may contain student names)"), False),
    _f("theses", "excluded", Category.TECHNICAL, N_("confidential theses opt-out (US-PROF-EXCLUDE); local only - excluded rows are stripped from exports, so the column would be constant-zero (#64)"), False),
    _f("theses", "notes", Category.IDENTIFYING, N_("free-form user notes"), False),
    _f("theses", "tags", Category.IDENTIFYING, N_("free-form user tags"), False),
    _f("theses", "added_at", Category.TECHNICAL, N_("audit trail (exported at day precision only)"), True),
    # module_runs
    _f("module_runs", "id", Category.TECHNICAL, N_("internal key"), True),
    _f("module_runs", "thesis_id", Category.TECHNICAL, N_("which thesis was analysed"), True),
    _f("module_runs", "module_name", Category.TECHNICAL, N_("which analysis ran (QA-REPRO)"), True),
    _f("module_runs", "module_version", Category.TECHNICAL, N_("staleness detection, reproducibility"), True),
    _f("module_runs", "status", Category.TECHNICAL, N_("ok / not-applicable / error"), True),
    _f("module_runs", "reason", Category.TECHNICAL, N_("why a run was na or errored (one line, no content)"), True),
    _f("module_runs", "error_traceback", Category.IDENTIFYING, N_("debugging; may embed filesystem paths"), False),
    _f("module_runs", "diagnostics", Category.CONTENT, N_("module diagnostics; may contain content-derived values"), False),
    _f("module_runs", "started_at", Category.TECHNICAL, N_("audit trail, profiling"), True),
    _f("module_runs", "duration_ms", Category.TECHNICAL, N_("profiling (QA-RES budgets)"), True),
    # metric_values
    _f("metric_values", "run_id", Category.TECHNICAL, N_("internal key"), True),
    _f("metric_values", "metric_name", Category.TECHNICAL, N_("which metric"), True),
    _f("metric_values", "value_num", Category.METRIC, N_("the research signal: numeric metric value"), True),
    _f("metric_values", "value_text", Category.METRIC, N_("the research signal: categorical metric value"), True),
    # artefact_files (table never exported)
    _f("artefact_files", "thesis_id", Category.TECHNICAL, N_("internal key"), False),
    _f("artefact_files", "kind", Category.TECHNICAL, N_("artefact kind of the cached file"), False),
    _f("artefact_files", "relative_path", Category.IDENTIFYING, N_("locate the cached file in the project folder"), False),
    _f("artefact_files", "run_id", Category.TECHNICAL, N_("which run produced the cached file"), False),
)


MODULES: tuple[ModuleEntry, ...] = (
    ModuleEntry("mod_extract_pymupdf", (Category.CONTENT,), (Category.CONTENT, Category.METRIC),
                N_("extract the plain text from the PDF; count pages and characters")),
    ModuleEntry("mod_check_extraction_quality", (Category.CONTENT,), (Category.METRIC,),
                N_("flag garbled or sparse text extractions so bad data is visible")),
    ModuleEntry("mod_classify_language", (Category.CONTENT,), (Category.METRIC,),
                N_("detect the thesis language to select language-aware analyses")),
    ModuleEntry("mod_classify_thesis_type", (Category.CONTENT,), (Category.METRIC,),
                N_("detect the degree (bachelor/master/diploma) from title-page keywords for grouping")),
    ModuleEntry("mod_tokenize", (Category.CONTENT,), (Category.CONTENT,),
                N_("split the text into sentences and words for counting modules")),
    ModuleEntry("mod_surface_counts", (Category.CONTENT,), (Category.METRIC,),
                N_("word/sentence/character counts and length statistics")),
    ModuleEntry("mod_vocabulary", (Category.CONTENT,), (Category.METRIC,),
                N_("vocabulary richness measures (TTR, hapax ratios, Yule's K)")),
    ModuleEntry("mod_readability", (Category.CONTENT,), (Category.METRIC,),
                N_("Flesch (en) / Amstad (de) reading-ease score")),
    ModuleEntry("mod_redundancy", (Category.CONTENT,), (Category.METRIC,),
                N_("repeated word-pair/triple rates")),
    ModuleEntry("mod_count_images", (Category.CONTENT,), (Category.METRIC,),
                N_("count embedded images in the PDF")),
    ModuleEntry("mod_extract_pdf_metadata", (Category.IDENTIFYING,), (Category.IDENTIFYING, Category.METRIC),
                N_("read PDF tool metadata; only categorised, year-precision values become metrics")),
    ModuleEntry("mod_determine_publication_year", (Category.CONTENT, Category.IDENTIFYING), (Category.METRIC,),
                N_("fuse the title-page year and PDF metadata dates into a best-estimate publication year")),
    ModuleEntry("mod_extract_filesystem_metadata", (Category.IDENTIFYING,), (Category.METRIC,),
                N_("read the file's size and modification year from the filesystem; only the year is kept")),
)


ARTEFACT_KINDS: tuple[ArtefactKindEntry, ...] = (
    ArtefactKindEntry("raw_text", Category.CONTENT, N_("full extracted thesis text (UTF-8 file)"), False),
    ArtefactKindEntry("language", Category.METRIC, N_("detected language code + confidence (JSON)"), False),
    ArtefactKindEntry("tokens", Category.CONTENT, N_("sentence/word tokenisation of the full text (JSON)"), False),
    ArtefactKindEntry("pdf_metadata", Category.IDENTIFYING, N_("complete PDF Info dict + XMP, incl. Author/Title (JSON)"), False),
)


# -- report rendering ---------------------------------------------------------

_CATEGORY_LABELS = {
    Category.TECHNICAL: N_("Technical bookkeeping (no personal data)"),
    Category.CONTENT_HASH: N_("Content fingerprints (no personal data recoverable)"),
    Category.METRIC: N_("Analysis results (aggregated text statistics)"),
    Category.CONTENT: N_("Document content (kept on this machine only)"),
    Category.IDENTIFYING: N_(
        "Directly identifying values (kept on this machine only)"
    ),
}


def render_report_md(rights_stub: str = "", controller_stub: str = "") -> str:
    """Sections 1-5 are generated from the registry; 6-7 are reviewed stubs.

    Rendered in the active locale, German by default (SDD Sec. 9.6). The
    registry itself stays English - it is also the source of
    ``render_report_json``, which is a machine contract - so every piece of
    prose is translated here, at render time (ADR-0020). The generated
    timestamp stays ISO 8601: it is an audit value, not display text.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# " + _("Privacy statement - Thesis Text Analyzer"),
        "",
        "*"
        + _("Generated {now} by tta {version} from `core/privacy_metadata.py`.").format(
            now=now, version=tta.__version__
        )
        + "*",
        "",
        "## " + _("1. What we process"),
        "",
    ]
    for category in Category:
        fields = [f for f in FIELDS if f.category is category]
        if not fields:
            continue
        lines.append("### " + _(_CATEGORY_LABELS[category]))
        lines.append("")
        lines.append(
            "| %s | %s | %s |"
            % (
                _("Stored value"),
                _("Purpose"),
                _("Leaves your machine on export"),
            )
        )
        lines.append("|---|---|---|")
        yes, no = _("yes"), _("no")
        for f in fields:
            lines.append(
                f"| `{f.table}.{f.column}` | {_(f.purpose)} | {yes if f.exported else no} |"
            )
        lines.append("")

    lines += [
        "## " + _("2. Module-level processing"),
        "",
        "| %s | %s | %s | %s |"
        % (_("Module"), _("Reads"), _("Produces"), _("Purpose")),
        "|---|---|---|---|",
    ]
    for m in MODULES:
        reads = ", ".join(c.value for c in m.reads_categories)
        writes = ", ".join(c.value for c in m.writes_categories)
        lines.append(f"| `{m.name}` | {reads} | {writes} | {_(m.purpose)} |")

    lines += [
        "",
        "## " + _("3. Cached files (never exported)"),
        "",
        "| %s | %s | %s |" % (_("Kind"), _("Category"), _("Description")),
        "|---|---|---|",
    ]
    for k in ARTEFACT_KINDS:
        lines.append(f"| `{k.kind}` | {k.category.value} | {_(k.description)} |")

    lines += [
        "",
        "## " + _("4. Storage and retention"),
        "",
        _(
            "All data lives in the project folder on this machine and is retained "
            "{retention}. The application is fully offline: it makes no network "
            "connections of any kind."
        ).format(retention=_(RETAIN_PROJECT)),
        "",
        "## " + _("5. What leaves your machine"),
        "",
        _("Only when you explicitly export, and only the following values:"),
        "",
    ]
    for f in FIELDS:
        if f.exported:
            lines.append(f"- `{f.table}.{f.column}` - {_(f.purpose)}")
    lines += [
        "",
        _(
            "Excluded theses, file paths and names, free-form notes and tags, raw "
            "text, tokenisations, full PDF metadata, error tracebacks, and module "
            "diagnostics never leave this machine."
        ),
    ]
    if rights_stub:
        lines += ["", "## " + _("6. Your rights under GDPR"), "", rights_stub.strip()]
    if controller_stub:
        lines += ["", "## " + _("7. Controller contact"), "", controller_stub.strip()]
    lines.append("")
    return "\n".join(lines)


# -- legal stubs (sections 6-7) ----------------------------------------------

#: Section 6 (data-subject rights) and section 7 (controller contact). One
#: pair per locale under core/help/privacy/<locale>/ (ADR-0009 "Legal
#: stubs"); the German pair is the primary version and the fallback.
RIGHTS_STUB = "rights_stub.md"
CONTROLLER_STUB = "controller_stub.md"

_HTML_COMMENT = re.compile(r"<!--.*?-->\s*", re.DOTALL)


def legal_stub_root():
    """The installed stub root (a Traversable, so a frozen build works)."""
    return resources.files("tta.core") / "help" / "privacy"


def load_legal_stub(filename: str, locale: str | None = None) -> str:
    """One legal stub in ``locale`` (default: the active one), comments stripped.

    A locale without its own stub falls back to the German one: a statement
    in the default language is better than one with a missing legal section.
    Returns "" only if not even the German stub is installed, which
    tests/core/test_privacy.py rules out for the shipped tree.
    """
    tag = normalise_locale(locale) or active_locale()
    root = legal_stub_root()
    for candidate in (tag, DEFAULT_LOCALE):
        stub = root / candidate / filename
        if stub.is_file():
            return _HTML_COMMENT.sub("", stub.read_text("utf-8")).strip()
    return ""


def render_statement_md() -> str:
    """The complete statement, sections 1-7, in the active locale.

    The one entry point both adapters use (``tta privacy report`` and the
    GUI's Help -> Privacy statement), so neither can render the generated
    sections without the legal ones.
    """
    return render_report_md(
        rights_stub=load_legal_stub(RIGHTS_STUB),
        controller_stub=load_legal_stub(CONTROLLER_STUB),
    )


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
