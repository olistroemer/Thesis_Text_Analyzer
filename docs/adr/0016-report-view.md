# ADR-0016: Report as a stand-alone HTML file

**Status:** Accepted (rev. 3; rev. 2's inline-SVG charts and its privacy rule are superseded by rev. 3, rev. 1's "matplotlib charts in a Tk notebook tab" by rev. 2)
**Date:** 2026-06-03, revised 2026-08-26 (#51, #70), revised 2026-11-18 (#84)
**Drivers:** US-PROF-INSIGHTS (the professor's motivation to use the app at all), US-PROF-TRENDS, US-PROF-COMPARE, US-PROF-NOTICE. Without this report, the MVP serves only US-RES-LOW-FRICTION — i.e. the professor has no reason to use the app beyond doing the researcher a favour.

## Revision 3 (2026-11-18, #84): the interactive professor report

The exploratory trial on branch `explore/plotly-report` showed what the report gains from interactivity and from a comparison with the reference corpus. The owner decided (2026-11-18) to grow it into **the** professor report. Rev. 3 replaces rev. 2's charts, content and privacy rule; everything else in rev. 2 stands (pure `collect`/`render_html` in core, adapters write and open, output path, post-run offer #70).

**One report.** The interactive report replaces the SVG report. It is what the GUI's Report button and `tta report` write; there is no second report.

**Charts: plotly.js, embedded inline.** The document embeds the official **plotly.js "cartesian" partial bundle** (`plotly.js-cartesian-dist-min` 4.3.0, MIT, 1,516,234 bytes; trace types bar, box, contour, heatmap, histogram, histogram2d(contour), image, pie, scatter, scatterternary, violin — the report uses scatter, bar and box). It is vendored in the repository at `tta/core/report_assets/plotly-cartesian-4.3.0.min.js` with its licence, pinned by SHA-256 in `core/report.py`, recorded in `docs/dependencies.md` and in `THIRD_PARTY_LICENSES.txt`. The "basic" bundle lacks box plots; the full bundle is three times the size for trace types the report does not use. **No Python plotting or data package enters the app**: aggregation is plain Python (lists, dicts, `statistics`, seeded `random` for the jitter), no `tta` module imports pandas, numpy, scipy or the Python plotly package, and pandas, scipy and plotly (Python) are on the packaging FORBIDDEN list (`plotly` added by #84). The report's own script (`report_assets/report.js`) builds the figures from one inline JSON block; every user-visible string in it comes from Python through `_()` (ADR-0020).

**Content.** Top to bottom:

1. **A note at the top**: the report may contain personal data (file names, paths, links to the PDFs); it is meant for the professor and not for sending to the research team — that is what the anonymised export is for.
2. **Summary cards** over the professor's theses (no reference size anywhere).
3. **Filters**: thesis type, language, field. Type and language filter both the professor's theses and the reference; **field acts on the reference only** (the app does not know a thesis's subject; detection is #44), default "all fields". A field comparison needs a concrete type and language; with "all" in either, the yearly reference summary is used.
4. **Coverage**: the professor's theses per publication year.
5. **Length / style / vocabulary metrics over time**, each with a metric picker: the reference **median line**, a band from the 25th to the 75th percentile and a lighter band from the 5th to the 95th per year ([ADR-0025](0025-reference-aggregates.md)), and the professor's theses as points (jittered within the year), **highlighted when outside the 25th-75th percentile and more strongly when outside the 5th-95th**. Each panel lists the theses outside the 5th-95th band with a link to the PDF. Theses dated outside the reference years (2003-2025) are shown without a comparison.
6. **Per-year boxes** of the professor's theses (years with at least 3 theses).
7. **Authoring tools**: the professor's theses per year by creating application (PDF creator, producer as fallback).

Dropped from the trial: fields, sample-vs-reference per field, the 2023 shift, correlations, scatter matrix, year/type detection against the repository (they need individual reference values or are researcher diagnostics; an extended researcher report may come later). Dropped from rev. 2: length by type, reading-ease histogram, language mix and the "notable theses" list (replaced by the highlights against the reference). Axes stay linear.

**Privacy rule (replaces rev. 2's "the report is an emission channel").** The report is a **local product for the professor**, not something meant to be sent to us. It **may show everything the local application can see**: file names, file paths, `file://` links to the local PDFs. It carries the note of item 1 at the top. The anonymised export ([ADR-0007](0007-export-format.md), §8.3) remains the only channel meant to leave the machine, and the privacy registry's `exported` flag keeps its single meaning. No new registry entries: the report is written into the project folder like the analysis data it is derived from.

**Offline, no external resources.** The document opens no network connection and references no external resource of any kind: no CDN, no web font, no remote image or script. Enforced by tests: (a) outside the embedded library the document contains no `http://` or `https://` at all; (b) the embedded library is byte-identical to the pinned file; (c) every `src`/`href` in the document is either absent or a local `file:` link to a PDF. The library itself contains URL strings (SVG/XML namespaces, the Chart Studio endpoint, the topojson CDN of the geo traces, which this bundle does not contain); the report's plotly configuration switches off every feature that could use them (`showLink`, `showSendToCloud`, `showEditInChartStudio`, `topojsonURL` empty, no MathJax).

**Size.** A report is ~1.7-2 MB (the library is 1.5 MB), against ~50 KB for rev. 2. The binary grows by the compressed library and the aggregates (~0.6 MB); measured in [ADR-0014](0014-distribution.md).

**Revisit when** a professor needs the report on a machine where scripts are disabled in local files (then: a static fallback), or plotly.js drops the partial bundles.

The rev. 2 text below is kept as history. Where it conflicts with rev. 3, rev. 3 wins.

## Decision (rev. 2)

The report is a **generated, self-contained HTML file**, opened in the user's browser. It is not a view inside the application.

- **Aggregation and rendering live in `core/report.py`** — `collect(repo) -> ReportData` and `render_html(data) -> str`. Both are pure, toolkit-free, stdlib-only, and perform **no I/O**: `render_html` returns a string. Direct precedent: `render_report_md()` / `render_report_json()` in `core/privacy_metadata.py`, consumed by both adapters.
- **Adapters own the side effects.** The GUI's "Report" toolbar button writes `<project>/reports/report-<YYYY-MM-DD>.html` (overwriting a same-day file) and calls `webbrowser.open`. The CLI gets `tta report [--out PATH]`, which writes the same default path when `--out` is omitted and prints where it went. **Core never writes files and never opens a browser** ([ADR-0002](0002-ui-core-boundary.md)).
- **Charts are hand-rolled inline SVG.** No matplotlib, no JavaScript, no web fonts, no CDN. The two statistics matplotlib used to supply — boxplot quartiles/whiskers/fliers and histogram binning — are reimplemented as the pure functions `core.report.box_stats` and `core.report.histogram`, following matplotlib's own conventions (1.5 × IQR fences, whiskers to the most extreme datum inside the fence; `numpy.histogram`'s equal-width bins with the last bin closed on both ends). Both are unit-tested, including an equivalence test against matplotlib/numpy where those are importable.
- **The Report toolbar button stays**, in both modes, with rev. 1's disabled-until-one-successful-run rule unchanged. The `ttk.Notebook` loses its Report tab; the main window is grid-only.

## Why rev. 1 was reversed

- Design and interactivity freedom. Two of rev. 1's six panels (summary cards, notable theses) were plain `ttk.Label`s — text pretending to be a report. HTML gives typography, layout, and tables for free; Tk gives none of it.
- The report becomes an **artefact the professor can keep, print, and send** rather than a screen that vanishes with the window. This is what "the professor's reward" actually looks like.
- The aggregation was on the wrong side of the boundary. `collect()` was toolkit-agnostic domain logic sitting in the Tk adapter, which is why the CLI had **no report at all** and why the report had **no unit test** — coverage reached it only through the GUI smoke test.
- Not a size argument. The matplotlib cluster is ~26 MB uncompressed, roughly 10 MB of the binary — rev. 1's estimate was accurate, and 10 MB was never the problem. Dropping the dependency from `pyproject.toml` and the PyInstaller spec was a **separate follow-up**, done in #53.

## Content

Unchanged from rev. 1 except where noted: summary cards; length over time (scatter + trend line); length by type (box plots); reading-ease distribution (histogram, by language); language mix (bar chart); notable theses. Linear axes throughout (per the project's no-log-scale preference).

The only content change is the **notable-theses label** — see Privacy below.

## Self-containment (QA-PRIV, SDD §10)

One file, no second file, no directory of assets: **all CSS and all SVG are inline**, and the document makes **zero external requests**. QA-PRIV forbids any network operation, which also rules out a Plotly/Chart.js CDN. A unit test asserts the rendered output contains no `http://` and no `https://` reference.

## Privacy: the report is now an emission channel

Rev. 1 stated the report *"does not transmit, export, or otherwise emit data. No new entries in `core/privacy_metadata.py`."* Writing a file makes the first clause false: the report is a second emission channel next to `core/export.py`, and the user can send the file to anyone.

**Resolution: the report emits only values the privacy registry already marks `exported=True`** (categories `technical` and `metric`). Concretely, `theses.pdf_filename` — `Category.IDENTIFYING`, "may contain student names", stripped from every export ([§8.3.1](../SDD.md#831-anonymisation-rules)) — is **removed** from the notable-theses list. Notable theses are identified by `theses.id` instead.

Consequences of that choice:

- No new entries in `core/privacy_metadata.py`. The registry's per-column `exported` flag keeps its single, cross-checkable meaning ("this column travels in the researcher export"), which the coverage gate verifies against a real export file; overloading it with a second channel would have broken that check.
- No pre-generation confirmation dialog (unlike `export_flow`): there is no PII to warn about.
- The privacy statement needs no new clause. The app is still fully offline; the report is still written inside the project folder; §5 "What leaves your machine" is still exactly the export.
- A test asserts the rendered HTML contains neither `pdf_filename` nor `pdf_path` for a thesis that is flagged as notable.

**Known cost:** a bare thesis id is not resolvable in the GUI grid, which shows filenames and has no id column; `tta list` does show ids. Accepted for MVP. Adding an id column, or a per-project stable pseudonym, is the follow-up if professors ask.

## What rev. 2 gives up

- **Live re-render on `RunCompleted`.** A written file cannot re-render itself, and the tab that used to do it is gone. This behaviour is deliberately surrendered. Its replacement is the post-run offer below (#70), which regenerates from current data on demand.
- The Report tab, and with it the ability to flick between grid and report inside one window. The browser holds the report instead.

## Auto-open after a run (#70)

Finishing a run is the natural point to look at the report (SDD [§9.7](../SDD.md#97-happy-path-walkthrough) step 4), so the GUI offers it rather than making the professor find the button again.

- The decision is a pure function, `core.report.should_offer_report(mode, cancelled=..., ok=...) -> "open" | "ask" | "skip"`, unit-tested without a display (the `core/progress.py` pattern). It returns `"skip"` for a **cancelled** run and for a run with **zero `ok`** pairs — an all-errored batch produced nothing new to report.
- `mode` comes from `ui.open_report_after_run` in `tta.toml`: `ask` (default) | `always` | `never`.
- In `ask` mode the GUI shows a **non-modal** prompt (a `Toplevel`, no `grab_set`) with Open / Not now and a "Don't ask again" checkbox; ticking it and answering persists `always` or `never`, so the prompt can be silenced permanently. Nothing about the prompt blocks the grid.
- **CLI:** `tta run --open-report`, off by default — a CLI must not launch a browser unasked. The flag is the explicit ask, so it ignores the config preference; it still respects the cancelled / zero-`ok` suppression.

## Alternatives considered

- **Keep the tab *and* write a file.** Two renderers for one report, two sets of chart code, and the tab's live re-render still needs matplotlib. Rejected: the tab is the half with less value.
- **matplotlib `savefig` to an SVG string, embedded in the HTML.** Least new code, and it keeps the maths we trust. Rejected: it keeps a 10 MB dependency and a ~500 ms first-import for four small charts we can draw in ~150 lines, and it drags matplotlib's font machinery into a frozen build for no user-visible gain.
- **Vendored Plotly / Chart.js.** Interactive, and legal to vendor, but it is megabytes of JavaScript inside every generated report file and a second language in the codebase. Rejected.
- **PDF via reportlab / weasyprint.** A nicer thing to archive, a much heavier dependency, and no zoom. Rejected for MVP; the browser prints the HTML to PDF perfectly well.
- **Report inside the app, rendered as HTML in a `tkinterweb` widget.** New dependency, poor CSS support, and it re-creates the tab we decided to drop. Rejected.
- **Markdown instead of HTML.** No charts. Rejected.

## Consequences

- ✅ The professor gets an artefact: keepable, printable, sendable, and PII-free by construction.
- ✅ `collect()` is unit-testable without a display, and the CLI has a report for the first time (`tests/core/test_report.py`, QA-TEST).
- ✅ The GUI drops matplotlib and `FigureCanvasTkAgg` from its import graph entirely; the main window is a grid plus a toolbar.
- ✅ One file, zero external requests — QA-PRIV holds trivially, and the file survives being copied onto a stick.
- ⚠️ The chart maths is ours now. Mitigated by unit tests, including an equivalence check against matplotlib/numpy. Since #53 removed matplotlib from the dependency set that check is `importorskip`-guarded: it runs for a developer who has matplotlib installed and skips everywhere else, so it is a corroboration, not a gate.
- ⚠️ Hand-rolled SVG has no free polish: no interactive tooltips, no automatic legend layout, no font metrics. Axis ticks and label placement are chosen by simple rules and can look cramped on unusual data.
- ⚠️ Losing the live re-render is a real regression for someone watching a long batch. #70's post-run offer covers the common case, not that one.
- ⚠️ `<project>/reports/` is a new directory in the project folder. It is derived data: safe to delete, regenerated on demand, and never exported.
- ⚠️ Notable theses are identified by id, which the grid cannot currently resolve (see Known cost above).

## Revisit when

- Professors ask for interactivity (filter, drill-down, hover values) that inline SVG cannot carry — that is when a vendored chart library earns its megabytes.
- The report needs to be a PDF for archiving, and browser print is not good enough.
- Someone asks to see the report update live during a batch, at which point a written file is the wrong shape and this decision is back on the table.
