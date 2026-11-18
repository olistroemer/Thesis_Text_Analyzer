"""The professor report (SDD Sec. 9.8, ADR-0016 rev. 3, ADR-0025, US-PROF-INSIGHTS).

Two pure halves, both stdlib-only:

* ``collect(repo)`` turns ``v_current_metrics`` over local, non-excluded
  theses into one record per thesis; garbled extractions are dropped and
  counted in a caption.
* ``render_html(data)`` returns one complete, self-contained HTML document
  as a string: CSS, the vendored plotly.js bundle, one JSON data block and
  the report script, all inline. It opens no network connection and
  references no external resource (QA-PRIV).

The comparison comes only from the reference aggregates shipped with the
app (``core.reference``); every highlight level is computed here, in Python,
so the script only picks the level that matches the current filter.

The report is a local product for the professor: it shows file names and
links to the local PDFs, and says at its top that it is not meant to be
sent to the research team (ADR-0016 rev. 3). Nothing here writes a file or
opens a browser - the adapters own those side effects (ADR-0002).
"""

from __future__ import annotations

import hashlib
import html
import json
import random
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from importlib import resources
from pathlib import Path

import tta
from tta.core import reference as ref
from tta.core.db.repository import Repository
from tta.core.i18n import N_, _, active_locale, format_datetime, format_number
from tta.core.types import REFERENCE_THESIS_TYPES, thesis_type_label

#: Post-run auto-open preference (`ui.open_report_after_run` in tta.toml, #70).
OPEN_REPORT_MODES = ("ask", "always", "never")

#: Where adapters put the generated file, relative to the project (Sec. 9.8.3).
REPORTS_DIRNAME = "reports"

#: The vendored plotly.js bundle and its pin (ADR-0016 rev. 3, dependencies.md 4.1).
PLOTLY_FILENAME = "plotly-cartesian-4.3.0.min.js"
PLOTLY_SHA256 = "38d5da8c29f94a5ba9bce10fd48ef0601dfb47bb2490c2e305137993ae7ba175"
SCRIPT_FILENAME = "report.js"

#: A year needs this many of the professor's theses for a box (Sec. 9.8.3).
MIN_BOX_THESES = 3

#: Half-width of the within-year jitter of the points.
JITTER = 0.28

#: Display labels of ``creator_category`` / ``producer_category`` values.
TOOL_LABELS = {
    "latex": "LaTeX",
    "word": "Word",
    "libreoffice": "LibreOffice",
    "openoffice": "OpenOffice",
    "indesign": "InDesign",
    "ghostscript": "Ghostscript",
    "other": N_("other"),
    "unknown": N_("unknown"),
}

GROUP_TITLES = {
    "length": N_("Length metrics over time"),
    "style": N_("Style metrics over time"),
    "vocabulary": N_("Vocabulary metrics over time"),
}
GROUP_NOTES = {
    "length": N_(
        "How long the theses are. Length grows with the subject and the degree, so "
        "compare within one type and language."
    ),
    "style": N_(
        "Style metrics that depend little on length: a thesis far outside the band "
        "writes differently from most theses of its year, not just longer or shorter."
    ),
    "vocabulary": N_(
        "Vocabulary ratios fall mechanically with text length; read them together "
        "with the length panel."
    ),
}

LANGUAGE_LABELS = {"de": N_("German"), "en": N_("English")}


def default_report_path(project_dir: Path | str, today: date | None = None) -> Path:
    """``<project>/reports/report-<YYYY-MM-DD>.html`` (Sec. 9.8.3).

    Pure path arithmetic so both adapters land on the same file: the caller
    creates the directory and writes the bytes (ADR-0002 - core does no
    I/O). A same-day file is overwritten; a report is derived data, unlike
    an export, which refuses to overwrite."""
    stamp = today or date.today()
    return Path(project_dir) / REPORTS_DIRNAME / f"report-{stamp:%Y-%m-%d}.html"


@dataclass
class ThesisRecord:
    """One of the professor's theses as the report sees it."""

    id: int
    filename: str
    uri: str | None
    thesis_type: str  # detected, "unspecified" when none
    language: str | None
    year: int | None
    tool: str
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class ReportData:
    theses: int = 0
    excluded: int = 0
    garbled: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_language: dict[str, int] = field(default_factory=dict)
    median_words: float | None = None
    year_range: tuple[int, int] | None = None
    records: list[ThesisRecord] = field(default_factory=list)


def _tool(values: dict) -> str:
    """Creator category, the producer where the creator says nothing specific."""
    creator = values.get("creator_category")
    producer = values.get("producer_category")
    for candidate in (creator, producer):
        if isinstance(candidate, str) and candidate not in ("other", "unknown"):
            return candidate
    if "other" in (creator, producer):
        return "other"
    return "unknown"


def _file_uri(path: str) -> str | None:
    try:
        return Path(path).resolve().as_uri()
    except (OSError, ValueError):
        return None


def collect(repo: Repository) -> ReportData:
    theses = {t.id: t for t in repo.list_theses(local_only=True, include_excluded=True)}
    data = ReportData(excluded=sum(t.excluded for t in theses.values()))
    included = {tid: t for tid, t in theses.items() if not t.excluded}

    values: dict[int, dict[str, float | str]] = {tid: {} for tid in included}
    for row in repo.current_metrics():
        if row["thesis_id"] in values and row["metric_name"] is not None:
            value = row["value_num"] if row["value_num"] is not None else row["value_text"]
            values[row["thesis_id"]][row["metric_name"]] = value

    garbled_ids = {tid for tid, v in values.items() if v.get("extraction_quality") == "garbled"}
    data.garbled = len(garbled_ids)
    words, years = [], []
    for tid, v in values.items():
        if tid in garbled_ids:
            continue
        # thesis type is the detected `thesis_type` metric (ADR-0019); theses
        # with no detected type group under "unspecified"
        detected = v.get("thesis_type")
        thesis_type = detected if isinstance(detected, str) else "unspecified"
        data.by_type[thesis_type] = data.by_type.get(thesis_type, 0) + 1
        language = v.get("language_code") if isinstance(v.get("language_code"), str) else None
        if language:
            data.by_language[language] = data.by_language.get(language, 0) + 1
        # the time axis is the fused publication_year (#17), not creation_year
        year = v.get("publication_year")
        year = int(year) if isinstance(year, (int, float)) and not isinstance(year, bool) else None
        if year is not None:
            years.append(year)
        metrics = ref.derive_metrics(v)
        if "word_count" in metrics:
            words.append(metrics["word_count"])
        thesis = included[tid]
        data.records.append(
            ThesisRecord(
                id=tid,
                filename=thesis.pdf_filename,
                uri=_file_uri(thesis.pdf_path),
                thesis_type=thesis_type,
                language=language,
                year=year,
                tool=_tool(v),
                metrics=metrics,
            )
        )
    data.theses = len(data.records)
    if words:
        data.median_words = statistics.median(words)
    if years:
        data.year_range = (min(years), max(years))
    return data


# -- post-run policy (#70) ----------------------------------------------------


def should_offer_report(mode: str, *, cancelled: bool, ok: int) -> str:
    """Decide what a finished run should do about the report (Sec. 9.8.3).

    Returns "open" (generate and open without asking), "ask" (prompt), or
    "skip". A cancelled run and a run with no successful pair produced
    nothing worth reporting, so both skip regardless of the preference.
    Pure on purpose: both adapters share it and it is testable without a
    display (the ``core/progress.py`` pattern)."""
    if cancelled or ok <= 0:
        return "skip"
    if mode == "never":
        return "skip"
    if mode == "always":
        return "open"
    return "ask"  # "ask", and any unknown value, falls back to asking


# -- comparison ---------------------------------------------------------------


def comparison_options(reference: ref.Reference | None) -> list[str]:
    """The comparison buckets a thesis can be compared with, in the order of
    its level string: the yearly summary, then "all fields" and every field
    the reference has (for the thesis's own type and language)."""
    fields = reference.fields if reference is not None else []
    return ["summary", ref.ALL] + fields


def level_string(record: ThesisRecord, metric: str, reference: ref.Reference | None,
                 options: list[str]) -> str:
    """One character per comparison option: the ``band_level`` (0/1/2) of the
    thesis's value against that bucket's bands, ``-`` without a comparison
    (year outside the reference, no bucket or statistic, no reference)."""
    value = record.metrics[metric]
    comparable = (
        reference is not None
        and record.year is not None
        and ref.year_in_range(record.year)
    )
    split = record.thesis_type in REFERENCE_THESIS_TYPES and record.language in ref.LANGUAGES
    out = []
    for option in options:
        stats = None
        if comparable:
            if option == "summary":
                stats = reference.stats(ref.ALL, ref.ALL, ref.ALL, record.year, metric)
            elif split:
                stats = reference.stats(record.thesis_type, record.language, option,
                                        record.year, metric)
        out.append("-" if stats is None else str(ref.band_level(value, stats)))
    return "".join(out)


def _jitter(record: ThesisRecord) -> float:
    """Stable within-year offset: seeded by the thesis id."""
    return round(random.Random(record.id).uniform(-JITTER, JITTER), 3)


# -- the document -------------------------------------------------------------


_STYLE = """
:root {
  color-scheme: light;
  --surface: #fcfcfb; --card: #ffffff; --line: #e4e3df; --grid: #eceae5;
  --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #7a7975;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-4: #eda100;
  --series-5: #e87ba4; --series-6: #008300; --series-7: #6250d6; --series-x: #9a9994;
  --serious: #ec835a; --critical: #d03b3b;
  --band-outer: rgba(82, 81, 78, 0.10); --band-inner: rgba(82, 81, 78, 0.22);
  --note-bg: #fff6e5; --note-line: #f0c36d;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --surface: #1a1a19; --card: #232322; --line: #35342f; --grid: #2c2b28;
    --ink: #ffffff; --ink-2: #c3c2b7; --ink-3: #9b9a92;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
    --series-5: #d55181; --series-6: #008300; --series-7: #9085e9; --series-x: #8d9199;
    --band-outer: rgba(195, 194, 183, 0.10); --band-inner: rgba(195, 194, 183, 0.22);
    --note-bg: #33291a; --note-line: #8a6a2a;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 28px 20px 56px; background: var(--surface); color: var(--ink);
  font: 15px/1.55 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
main { max-width: 1120px; margin: 0 auto; }
h1 { font-size: 25px; letter-spacing: -0.01em; margin: 0 0 4px; }
h3 { font-size: 15px; font-weight: 600; margin: 0 0 6px; }
.sub { color: var(--ink-2); margin: 0 0 12px; }
.privacy { background: var(--note-bg); border: 1px solid var(--note-line); border-radius: 10px;
           padding: 10px 14px; margin: 0 0 16px; font-size: 14px; }
.privacy strong { display: block; margin-bottom: 2px; }
.cards { display: grid; gap: 12px; margin: 0;
         grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
        padding: 12px 14px; }
.card dt { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
           color: var(--ink-3); margin: 0 0 4px; }
.card dd { margin: 0; font-size: 21px; font-weight: 600; letter-spacing: -0.01em; }
.card dd small { display: block; font-size: 12px; font-weight: 400; color: var(--ink-2);
                 letter-spacing: 0; }
.filters { position: sticky; top: 0; z-index: 5; background: var(--surface);
           display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: end;
           padding: 12px 0 10px; margin-top: 18px; border-bottom: 1px solid var(--line); }
.filters label, .picker { display: flex; flex-direction: column; font-size: 12px;
                          color: var(--ink-3); gap: 3px; }
select { font: inherit; font-size: 14px; color: var(--ink); background: var(--card);
         border: 1px solid var(--line); border-radius: 8px; padding: 5px 8px; min-width: 150px; }
select:disabled { opacity: 0.55; }
.hint { color: var(--ink-3); font-size: 12.5px; margin: 6px 0 0; }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
         padding: 16px; margin-top: 18px; }
.panel .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
.plot { width: 100%; min-height: 360px; }
.plot.short { min-height: 300px; }
.note, .caption { color: var(--ink-3); font-size: 12.5px; margin: 6px 0 0; }
.empty { color: var(--ink-3); font-size: 13.5px; margin: 0; padding: 28px 0; text-align: center; }
.outside { margin-top: 10px; font-size: 13px; }
.outside summary { cursor: pointer; color: var(--ink-2); }
.scroll { overflow-x: auto; margin-top: 6px; }
table { border-collapse: collapse; font-size: 13px; width: 100%; }
th, td { text-align: left; padding: 4px 12px 4px 0; border-bottom: 1px solid var(--line);
         white-space: nowrap; }
th { color: var(--ink-3); font-weight: 600; }
a { color: var(--series-1); }
noscript p { background: var(--note-bg); padding: 10px 14px; border-radius: 10px; }
footer { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--line);
         color: var(--ink-3); font-size: 12.5px; }
@media print {
  body { padding: 0; background: #ffffff; }
  .filters { position: static; }
  .panel { break-inside: avoid; border-color: #cccccc; }
}
"""


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _asset(name: str) -> str:
    return (resources.files("tta.core") / ref.ASSETS_DIR / name).read_text(encoding="utf-8")


def plotly_js() -> str:
    """The vendored library, verified against its pin (ADR-0016 rev. 3)."""
    raw = (resources.files("tta.core") / ref.ASSETS_DIR / PLOTLY_FILENAME).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLOTLY_SHA256:
        raise RuntimeError(f"{PLOTLY_FILENAME} does not match its pinned SHA-256")
    return raw.decode("utf-8")


def _card(term: str, value: str, note: str = "") -> str:
    detail = f"<small>{_esc(note)}</small>" if note else ""
    return f'<div class="card"><dt>{_esc(term)}</dt><dd>{_esc(value)}{detail}</dd></div>'


def _summary_cards(data: ReportData) -> str:
    languages = " ".join(f"{k}={n}" for k, n in sorted(data.by_language.items())) or "-"
    years = f"{data.year_range[0]}-{data.year_range[1]}" if data.year_range else "-"
    types = " | ".join(
        f"{thesis_type_label(k)}: {n}" for k, n in sorted(data.by_type.items())
    ) or _("no type detected")
    median = format_number(data.median_words, 0) if data.median_words is not None else "-"
    return (
        '<dl class="cards">'
        + _card(_("Theses analysed"), str(data.theses), types)
        + _card(_("Excluded"), str(data.excluded), _("left out of every panel"))
        + _card(_("Languages"), languages)
        + _card(_("Publication years"), years)
        + _card(_("Median length"), median, _("words"))
        + "</dl>"
    )


def _select(element_id: str, label: str, options: list[tuple[str, str]]) -> str:
    items = "".join(f'<option value="{_esc(v)}">{_esc(t)}</option>' for v, t in options)
    return (
        f'<label>{_esc(label)}<select id="{_esc(element_id)}">{items}</select></label>'
    )


def _filters(reference: ref.Reference | None) -> str:
    types = [(ref.ALL, _("all types"))] + [
        (code, thesis_type_label(code)) for code in REFERENCE_THESIS_TYPES
    ]
    languages = [(ref.ALL, _("all languages"))] + [
        (code, _(LANGUAGE_LABELS[code])) for code in ref.LANGUAGES
    ]
    fields = [(ref.ALL, _("all fields"))] + [
        (code, _(ref.DDC_MAIN_CLASSES[code]))
        for code in (reference.fields if reference is not None else [])
    ]
    return (
        '<div class="filters">'
        + _select("f-type", _("Thesis type"), types)
        + _select("f-lang", _("Language"), languages)
        + _select("f-field", _("Field (reference only)"), fields)
        + "</div>"
        + '<p class="hint" id="f-hint"></p>'
    )


def _reference_caption(reference: ref.Reference | None) -> str:
    if reference is None:
        text = _(
            "No reference data is available in this version of the app; the panels "
            "show your theses only."
        )
    else:
        first, last = reference.years
        text = _(
            "Reference: bachelor's and master's theses from two university repositories "
            "(HU Berlin, ETH Zurich), {first}-{last}. Per year, the line is the median "
            "and the bands span the 25th-75th and the 5th-95th percentile. The median "
            "and the 25th-75th band are shown where at least {inner} reference theses "
            "have a value, the 5th-95th band only where at least {outer} do; without "
            "it, the highlights only tell inside from outside the 25th-75th percentile."
        ).format(first=first, last=last, inner=reference.min_inner, outer=reference.min_outer)
        if reference.status == "interim":
            text += " " + _(
                "Interim reference values: computed with an earlier version of the "
                "analysis; they will be replaced before the release."
            )
    return f'<p class="caption">{_esc(text)}</p>'


def _picker(element_id: str, metrics) -> str:
    options = "".join(
        f'<option value="{_esc(m)}">{_esc(_(ref.METRIC_LABELS[m]))}</option>' for m in metrics
    )
    return (
        f'<label class="picker">{_esc(_("Metric"))}'
        f'<select id="{_esc(element_id)}">{options}</select></label>'
    )


def _panel(panel_id: str, title: str, body: str, picker: str = "", note: str = "") -> str:
    note_html = f'<p class="note">{_esc(note)}</p>' if note else ""
    return (
        f'<section class="panel" id="{_esc(panel_id)}"><div class="head">'
        f"<h3>{_esc(title)}</h3>{picker}</div>{body}{note_html}</section>"
    )


def _strings() -> dict[str, str]:
    """Every user-visible text the script shows, translated here (ADR-0020)."""
    return {
        "year": _("publication year"),
        "theses": _("theses"),
        "median": _("reference median"),
        "inner": _("reference 25th-75th percentile"),
        "outer": _("reference 5th-95th percentile"),
        "level0": _("your theses: inside the 25th-75th percentile"),
        "level1": _("outside the 25th-75th percentile"),
        "level2": _("outside the 5th-95th percentile"),
        "levelNone": _("no comparison"),
        "noData": _("Not enough data for this selection."),
        "noComparisonYears": _(
            "{count} thesis(es) are dated outside the reference years and are shown "
            "without a comparison."
        ),
        "undated": _("{count} thesis(es) without a publication year are not on the time axis."),
        "fieldHint": _(
            "The field applies to the reference only (the app does not know the subject "
            "of your theses). Choose a thesis type and a language to compare with one field."
        ),
        "fieldHintActive": _(
            "Your theses of this type and language are compared with the reference "
            "theses of the chosen field."
        ),
        "outsideTitle": _("Theses outside the 5th-95th percentile of the reference: {count}"),
        "outsideMore": _("{count} more outside the 25th-75th percentile."),
        "outsideInner": _("Theses outside the 25th-75th percentile of the reference: {count}"),
        "colThesis": _("Thesis"),
        "colYear": _("Year"),
        "colValue": _("Value"),
        "colBand": _("Reference 5th-95th percentile"),
        "boxesNote": _(
            "Box: 25th to 75th percentile with the median; whiskers reach the most "
            "extreme thesis within 1.5 x IQR. Years with at least {minimum} theses."
        ).format(minimum=MIN_BOX_THESES),
    }


def _payload(data: ReportData, reference: ref.Reference | None) -> dict:
    options = comparison_options(reference)
    theses = []
    for record in sorted(data.records, key=lambda r: (r.year or 0, r.id)):
        meta = " | ".join(
            part
            for part in (
                thesis_type_label(record.thesis_type),
                record.language or "",
                str(record.year) if record.year is not None else "",
            )
            if part
        )
        theses.append(
            {
                "id": record.id,
                "name": record.filename,
                "uri": record.uri,
                "type": record.thesis_type,
                "lang": record.language,
                "year": record.year,
                "x": None if record.year is None else record.year + _jitter(record),
                "tool": record.tool,
                "head": f"<b>{_esc(record.filename)}</b><br>{_esc(meta)}",
                "m": {k: float(f"{v:.6g}") for k, v in record.metrics.items()},
                "lv": {
                    k: level_string(record, k, reference, options) for k in record.metrics
                },
            }
        )
    bands: dict[str, dict[str, list]] = {}
    years = list(range(ref.YEARS[0], ref.YEARS[1] + 1))
    if reference is not None:
        for (thesis_type, language, field_code, year), values in reference.rows.items():
            key = f"{thesis_type}|{language}|{field_code}"
            for metric, stats in values.items():
                series = bands.setdefault(key, {}).setdefault(metric, [None] * len(years))
                if year in years:
                    series[years.index(year)] = stats
    return {
        "locale": active_locale(),
        "separators": ",." if active_locale() == "de" else ".,",
        "years": years,
        "options": options,
        "groups": {name: list(metrics) for name, metrics in ref.METRIC_GROUPS.items()},
        "labels": {m: _(ref.METRIC_LABELS[m]) for m in ref.METRICS},
        "tools": {k: (_(v) if k in ("other", "unknown") else v) for k, v in TOOL_LABELS.items()},
        "toolOrder": list(TOOL_LABELS),
        "minBox": MIN_BOX_THESES,
        "strings": _strings(),
        "theses": theses,
        "bands": bands,
    }


def _json_block(payload: dict) -> str:
    # "<" escaped so no sequence inside can end or confuse the script element
    text = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/json" id="tta-data">{text}</script>'


_SHIPPED = object()


def render_html(data: ReportData, reference=_SHIPPED, generated_at: datetime | None = None) -> str:
    """One self-contained HTML document, as a string (Sec. 9.8).

    ``reference`` defaults to the aggregates shipped with the app; ``None``
    renders without a comparison. The document makes no external request:
    everything, plotly.js included, is inline (QA-PRIV)."""
    if reference is _SHIPPED:
        reference = ref.load_shipped()
    stamp = format_datetime(generated_at or datetime.now())
    garbled = (
        '<p class="caption">%s</p>'
        % _esc(
            _(
                "{count} thesis(es) with a garbled text extraction are left out of "
                "every panel."
            ).format(count=data.garbled)
        )
        if data.garbled
        else ""
    )
    privacy = (
        '<div class="privacy" role="note"><strong>%s</strong>%s</div>'
        % (
            _esc(_("This report may contain personal data.")),
            _esc(
                _(
                    "It shows file names, file paths and links to your PDFs. It is meant "
                    "for you and is not intended to be sent to the research team - for "
                    "that, use the anonymised export."
                )
            ),
        )
    )
    group_panels = "".join(
        _panel(
            f"p-{name}",
            _(GROUP_TITLES[name]),
            f'<div class="plot" id="g-{name}"></div><div class="outside" id="o-{name}"></div>',
            _picker(f"m-{name}", metrics),
            _(GROUP_NOTES[name]) + " " + _("Click a point to open the PDF."),
        )
        for name, metrics in ref.METRIC_GROUPS.items()
    )
    body = (
        f"<h1>{_esc(_('Thesis report'))}</h1>"
        + '<p class="sub">%s</p>'
        % _esc(
            _("Thesis Text Analyzer - {count} analysed thesis(es), generated {stamp}").format(
                count=data.theses, stamp=stamp
            )
        )
        + privacy
        + _summary_cards(data)
        + garbled
        + "<noscript><p>%s</p></noscript>"
        % _esc(
            _(
                "The charts of this report need JavaScript. It runs locally in your "
                "browser; nothing is loaded from the network."
            )
        )
        + _filters(reference)
        + _reference_caption(reference)
        + _panel(
            "p-coverage",
            _("Coverage"),
            '<div class="plot short" id="g-coverage"></div><p class="note" id="n-coverage"></p>',
            note=_("Your theses per publication year, for the selected type and language."),
        )
        + group_panels
        + _panel(
            "p-boxes",
            _("Your theses per year"),
            '<div class="plot" id="g-boxes"></div>',
            _picker("m-boxes", ref.METRICS),
            _strings()["boxesNote"],
        )
        + _panel(
            "p-tools",
            _("Authoring tools"),
            '<div class="plot short" id="g-tools"></div>',
            note=_(
                "Your theses per year by the application that created the PDF (the PDF "
                "producer where the creator is not recognised)."
            ),
        )
        + "<footer>"
        + _esc(
            _(
                "Generated locally by tta {version}. This file is self-contained and "
                "works offline: it loads nothing from the network. Regenerate it any "
                "time from the Report button or `tta report`."
            ).format(version=tta.__version__)
        )
        + "</footer>"
    )
    # The document declares the locale it was rendered in (SDD Sec. 9.6).
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{_esc(active_locale())}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(_('Thesis Text Analyzer - thesis report {stamp}').format(stamp=stamp))}</title>"
        f"<style>{_STYLE}</style></head><body><main>"
        + body
        + "</main>"
        + _json_block(_payload(data, reference))
        + f"<script>{plotly_js()}</script>"
        + f"<script>{_asset(SCRIPT_FILENAME)}</script>"
        + "</body></html>\n"
    )
