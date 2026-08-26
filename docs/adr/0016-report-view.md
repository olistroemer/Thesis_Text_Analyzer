# ADR-0016: Report as a stand-alone HTML file

**Status:** Accepted (rev. 2; rev. 1's "matplotlib charts in a Tk notebook tab" is superseded)
**Date:** 2026-06-03, revised 2026-08-26 (#51, #70)
**Drivers:** US-PROF-INSIGHTS (the professor's motivation to use the app at all), US-PROF-TRENDS, US-PROF-COMPARE, US-PROF-NOTICE. Without this report, the MVP serves only US-RES-LOW-FRICTION — i.e. the professor has no reason to use the app beyond doing the researcher a favour.

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
