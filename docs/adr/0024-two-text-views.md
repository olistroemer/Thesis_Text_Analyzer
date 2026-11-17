# ADR-0024: Two text views from one extraction — `raw_text` for detection, `prose_text` for the text metrics

**Status:** Accepted
**Date:** 2026-11-17
**Drivers:** #22 (Exp #22: font filter vs layout model, owner decisions 2026-11-17); primary research goal (SDD §2.1: text metrics over publication year); QA-REPRO (values must say which text they were computed on); QA-RES / [ADR-0015](0015-performance-budget.md) (extractor budget ≤ 6 s per 100-page thesis); results of the detection modules must not move (#81, #82).

## Context

`mod_extract_pymupdf` wrote one text, `raw_text`: everything in the PDF's text layer. Every module read it. For the text metrics that includes code listings and formula fragments, which have nothing to do with the author's prose and are concentrated in computer science, maths and physics, so they bias subject comparisons.

Exp #22 compared, on the full reference corpus (3,195 paired theses), three arms: **A** the naive text, **B** a font filter (drop monospaced spans and math-font spans) and **C** a layout model (pymupdf4llm, prose boxes only). Results (issue #22, experiment report): B is a small, targeted cleanup (median change ≤ 1.3 % per metric, rank correlation 0.91-0.99 with A; formal subjects change ~5x more than the rest, the humanities not at all) at +18 % runtime, ~1 s per 100 pages. C changes the numbers a lot (text length -14 %), mostly through table boxes, swallows whole pages of prose on old PDFs and is ~35x slower than B, ~6x over budget. The owner adopted B and left tables/TOC lines to a separate experiment (#97).

Arm B replaced `raw_text` in place. But the detection modules read `raw_text` too: language, publication date (#81), thesis type (#82) and the extraction-quality check. Their rules are corpus-grounded on the unfiltered text; a title page whose date or degree phrase is set in a typewriter font, or a URL that carries a year, would silently change their results.

## Decision

**1. One extraction pass, two text views.** `mod_extract_pymupdf` parses each page once into a PyMuPDF `TextPage` (plain-text flags, `TEXTFLAGS_TEXT`) and serialises two artefacts from that object:

- **`raw_text`** — the `TextPage`'s plain-text output, byte-identical to the previous `page.get_text("text")`. Read by `mod_check_extraction_quality`, `mod_classify_language`, `mod_classify_thesis_type`, `mod_determine_publication_year`.
- **`prose_text`** — a new artefact kind: the same `TextPage`'s `dict` output rebuilt line by line without monospaced spans and math-font spans ("font filter v1", the rule of arm B, stated in SDD §7.4). Read by `mod_tokenize` (and therefore `mod_surface_counts`, `mod_vocabulary`, `mod_redundancy`) and `mod_readability`.

**2. Who reads what.** The split is by purpose:

| Reads `raw_text` | Why | Reads `prose_text` | Why |
|---|---|---|---|
| `mod_check_extraction_quality` | judges the extraction itself; filtering first would hide a garbled layer set in a filtered font | `mod_tokenize` → `mod_surface_counts`, `mod_vocabulary`, `mod_redundancy` | text metrics about the author's prose |
| `mod_classify_language` | owner decision: results must not move; langdetect reads the head of the text and is robust to code | `mod_readability` | Flesch/Amstad over prose, not over code |
| `mod_classify_thesis_type`, `mod_determine_publication_year` | title-page rules grounded on the unfiltered text (#81, #82) | | |

The extractor's own metrics: **`text_chars`** is now the length of `prose_text` (owner decision: length metrics move to the filtered text); **`n_pages`** is a property of the document, the same for both views. Two new metrics, **`removed_monospace_chars`** and **`removed_math_chars`**, count the non-whitespace characters the filter removed per category; a span that is both monospaced and in a math font counts as monospace. The catalogue grows from 32 to 34 metrics and from four to five artefact kinds ([ADR-0011](0011-mvp-module-catalogue.md) rev. 7).

**3. Versions and comparability.** Every module whose output changes gets a new version, so planning re-runs it: `mod_extract_pymupdf` 0.2.0, `mod_tokenize` 0.3.0, `mod_surface_counts` 0.2.0, `mod_vocabulary` 0.3.0, `mod_redundancy` 0.2.0, `mod_readability` 0.2.0. The detection modules keep their versions (their input is unchanged; they re-run once anyway because their producer re-ran). **Values of `text_chars` and of all `prose_text`-based metrics are not comparable with values from earlier versions**; the reference corpus is re-run with the new extraction in the follow-up project, not in this change.

**4. Not a producer swap.** This is not [ADR-0005](0005-producer-swap-deferred.md)'s swap mechanism: one module produces both kinds, so "exactly one producer per kind" still holds. An alternative extractor for the library-comparison study replaces the producer of both views (SDD §7.3).

## Alternatives considered

- **(a) Filter `raw_text` in place (arm B as run).** Simplest, but moves the detection modules' inputs and therefore their results, which were tuned on the unfiltered text (#81, #82). Rejected by the owner.
- **(c) Two passes: `get_text("text")` plus `get_text("dict")`.** Guarantees `raw_text` identity too, but parses every page twice. The single `TextPage` gives the same guarantee at one parse.
- **Rebuild `raw_text` from the `dict` output with the filter off.** One serialisation instead of two, but not byte-identical: the Exp #22 sanity check found a page where the rebuild and `get_text("text")` differ (combining characters). Rejected because decision 1 requires identity.
- **Filter inside each consuming module** (a "view" parameter on `raw_text`). Every consumer would re-implement or re-run the filter and the span information is gone after extraction. Rejected: one rule, one place, one artefact (the design note in #22: "define named text views once, don't filter ad hoc per module").
- **Layout model (arm C).** Too slow (~35 s per 100 pages), fragile (timeouts, swallowed prose) and most of its effect comes from tables. Rejected in Exp #22; tables are #97.
- **A single removed-characters metric.** Acceptable to the owner, but the split costs nothing (the category is known per span) and separates "CS thesis with listings" from "maths thesis with formulas".

## Consequences

- ✅ Detection results (language, quality, type, date) are unchanged; `raw_text` is byte-identical.
- ✅ Text metrics no longer measure code listings and inline math; the removed volume is visible per thesis as two metrics.
- ✅ Runtime within budget: arm B measured +18 %, ~1 s per 100 pages under 19-worker load ([ADR-0015](0015-performance-budget.md) note 2026-11-17).
- ⚠️ A second content artefact per thesis: roughly doubles the cached text on disk (both files are local only, never exported, purged with the thesis).
- ⚠️ All text-metric values change version and are not comparable with earlier runs; mixing them in one analysis is a mistake the version column makes detectable, not impossible.
- ⚠️ The filter is a font proxy with known misses and false positives, including rare whole-document losses (a thesis set in Courier, a Word body in Cambria Math); see [`model-limitations.md`](../model-limitations.md) §5.
- ⚠️ An alternative extractor must produce both views.

## Revisit when

- #97 (table/TOC line heuristic) is adopted: it would further narrow `prose_text` (a "font filter v2" or a third view), with the same version and comparability rules.
- Whole-document false positives matter in practice: a guard (e.g. do not filter a category that would remove most of a document) would be a filter v2.
- The library-comparison study picks a different extractor.
