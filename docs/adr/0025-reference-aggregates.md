# ADR-0025: Reference aggregates shipped inside the app

**Status:** Accepted (rev. 2 - decision 5: one threshold per statistic, median/quartiles/mean from 4 theses, 5th/95th percentile from 20; rev. 1's single threshold of 10 is superseded)
**Date:** 2026-11-18 (rev. 2: 2026-11-18, for release 1.0.0)
**Drivers:** #84 (owner decisions 2026-11-18), #49 (reference baselines), US-PROF-COMPARE, US-PROF-TRENDS, [ADR-0016](0016-report-view.md) rev. 3 (the professor report that consumes them), [ADR-0019](0019-thesis-type-by-detection.md) rev. 3 (`REFERENCE_THESIS_TYPES`), [ADR-0003](0003-cli-first-class.md) (researcher tooling stays out of the GUI), QA-PRIV, QA-REPRO.

## Context

The professor report ([ADR-0016](0016-report-view.md) rev. 3) compares the professor's own theses with the research team's reference corpus (the harvested bachelor and master theses of HU Berlin edoc and the ETH Research Collection). The app is offline (QA-PRIV), so the comparison must travel inside the binary. Shipping the corpus itself, or per-thesis values, is out: it is the wrong size, and per-thesis values of third-party theses have no business in an app handed to professors. What the report needs per year is a centre and a spread, so it ships exactly that.

## Decision

**1. One data file in the package.** `tta/core/report_assets/reference_aggregates.json`, package data (`pyproject.toml` `package-data`, `packaging/tta.spec` `datas`). The report reads it through `core.reference.load_shipped()` (`importlib.resources`, read-only, the `help_corpus` pattern). Nothing writes it at run time; nothing outside the report reads it.

**2. Six statistics per bucket and metric, no counts.** For every bucket and metric: **mean, median, 5th, 25th, 75th and 95th percentile**. Percentiles use linear interpolation between the closest ranks (`statistics.quantiles(..., method="inclusive")`, numpy's default, the same convention as the grid's IQR rule). **No n and no corpus size appear anywhere** in the file or in the report; the file carries only the threshold constants `min_theses` (below). A statistic below its threshold is `null` (rev. 2). Values are rounded to 4 significant digits.

**3. Buckets.**

| type | language | field | year |
|---|---|---|---|
| `bachelor`, `master` | `de`, `en` | DDC main class `000` ... `900` | 2003-2025 |
| `bachelor`, `master` | `de`, `en` | `all` (every field, **including theses without a known field**) | 2003-2025 |
| `all` | `all` | `all` (yearly summary: every reference thesis of that year) | 2003-2025 |

"Unknown field" is never a bucket of its own; such theses count in the `all` buckets only.

**4. Population.** A reference thesis counts if it is local, not excluded, not `extraction_quality = garbled` (the report's own rule), its detected `thesis_type` is in `REFERENCE_THESIS_TYPES` (`bachelor`, `master`) and its detected `publication_year` lies in 2003-2025. The split buckets additionally need a detected `language_code` of `de` or `en`; the yearly summary takes every language. **Type, language and year are the app's detected metrics** (#81/#82 detectors), never the repository's metadata, so a reference thesis is classified exactly as the professor's own theses are. Per metric, only theses with a value for that metric count.

**5. The thresholds (rev. 2): one per statistic.** Per bucket and metric, the **centre and the inner band - median, 25th and 75th percentile, and the mean with them - ship from 4 theses** with a value for that metric (`MIN_THESES_INNER = 4`); the **outer band - 5th and 95th percentile - ships only from 20** (`MIN_THESES_OUTER = 20`). Between 4 and 19 theses a metric ships its mean, median, p25 and p75 and `null` for p05 and p95; below 4 it does not ship; a bucket with no metric is not shipped. The mean belongs to the inner group: like the median it is a centre, and it is as stable as the median on a short series (it is not plotted; it only appears on hover). Every statistic is still computed from individual theses, and every bucket directly from them, so the theses of a dropped small bucket still count in the coarser buckets of the same year (the `all`-field bucket of their type and language, and the yearly summary). See "Revision 2" below for the analysis behind the two numbers.

*Rev. 1 (superseded):* a single threshold, >= 10 theses per bucket and metric for all six statistics.

**6. Field = DDC main class from the harvest metadata.** The first DDC code of the repository record (ETH: `info:eu-repo/classification/ddc/NNN`; edoc: `ddc:NNN` and labelled `NNN Label` subjects), folded to its main class (`000`, `100`, ..., `900`). It is joined by PDF file stem through the harvester's `downloads.pdf_path` (`<harvest>/data/<host>/theses.sqlite`), the linkage of the `explore/plotly-report` trial. Field is the one attribute the app cannot detect (subject detection is #44); the report therefore offers it as a filter **on the reference only**.

**7. Metric catalogue.** `core.reference.METRIC_GROUPS`, three groups as in the report: **length** (`word_count`, `n_pages`, `char_count_alpha`, `text_chars`, `sentence_count`, `n_images`, `avg_sentence_len`, and the derived `file_size_mb`, `words_per_page`, `images_per_page`, `kb_per_page`), **style** (`flesch_reading_ease`, `yules_k`, `avg_word_len`, `std_sentence_len`, `bigram_repetition_rate`, `trigram_repetition_rate`) and **vocabulary** (`ttr`, `root_ttr`, `hapax_token_ratio`, `hapax_type_ratio`). Derived metrics are computed by the one function `core.reference.derive_metrics`, used by both the generator and the report, so both sides compute them identically. Metrics the report does not plot (years, confidences, categories) are not aggregated.

**8. Format.**

```json
{
  "_comment": "...",
  "format": "tta-reference-aggregates",
  "format_version": 2,
  "status": "release",
  "source": "free text: which corpus, which analysis run",
  "generated": "2026-11-18",
  "generator": "tools/reference_aggregates.py (tta 0.x)",
  "analysed_with": ["mod_extract_pymupdf 0.2.0", "..."],
  "years": [2003, 2025],
  "min_theses": {"mean": 4, "median": 4, "p05": 20, "p25": 4, "p75": 4, "p95": 20},
  "stats": ["mean", "median", "p05", "p25", "p75", "p95"],
  "metrics": ["word_count", "..."],
  "fields": ["000", "100", "..."],
  "rows": [
    {"type": "bachelor", "language": "de", "field": "300", "year": 2015,
     "values": {"word_count": [mean, median, p05, p25, p75, p95],
                "yules_k": [mean, median, null, p25, p75, null], "...": []}}
  ]
}
```

`format_version` 2 (rev. 2): `min_theses` is an object with one threshold per statistic, in `stats` order, and p05/p95 may be `null`. The reader (`core.reference.Reference`) stays strict: it accepts only version 2, a `min_theses` object with exactly the six statistics (one value for the inner four, one for the outer two, outer >= inner) and per metric six entries whose mean, median, p25 and p75 are numbers and whose p05 and p95 are both numbers or both `null`. A version-1 file is refused (the report then renders without bands), so a stale file cannot slip through.

`status` is `interim` or `release`. `analysed_with` lists the module versions the reference project's current results were produced with (QA-REPRO: a reader can tell which analysis the numbers belong to). Rows are sorted (year, type, language, field), keys in a fixed order, so a regeneration diffs cleanly.

**9. Generator: `tools/reference_aggregates.py`, researcher tooling.**

```
python tools/reference_aggregates.py --project <reference project folder or tta.sqlite> \
    --harvest-root <harvester>/data [--status interim|release] [--source TEXT] \
    [--out tta/core/report_assets/reference_aggregates.json]
```

It opens the project database **read-only** (an SQLite `mode=ro` URI, never through `Project.open`, which may migrate), so it can read a project another process is still analysing. Harvest-specific code (the harvester's database layout, OAI-DC parsing) lives in the tool; the pure parts (population rule, bucket statistics, threshold, file format) live in `core/reference.py` and are unit-tested.

Why `tools/` and not a `tta` subcommand: the generator depends on the research team's private harvest layout, which is not a contract of the app; it runs when a release is prepared, never at run time; and its output is a committed package file. Under [ADR-0003](0003-cli-first-class.md) a `tta` subcommand would put harvest-specific code into every professor's binary for nothing. `tools/` is never frozen (SDD §5.6.5), like `tools/screenshots.py`.

**10. Shipped data: released (2026-11-18).** The first committed file was interim: generated from the last complete reference run of 2026-09 (`TTA-exp22/ref_tta.sqlite`), which predated the #81/#82 detectors and the #22 text views, marked `"status": "interim"` and announced as such in the report's reference caption. The same day it was **replaced** (owner decision) by a file generated from the re-run of the HU+ETH reference corpus (`TTA-ref-2026-11`: 3,275 PDFs, code snapshot of main `fbe297c`, ETH cover ruleset [ADR-0023](0023-researcher-cover-rulesets.md), 946 s on the development machine). It carries `"status": "release"`, its `source` names that run and `analysed_with` its module versions (`mod_extract_pymupdf 0.2.0`, `mod_classify_thesis_type 0.3.0+covers...`, `mod_determine_publication_year 0.2.0+covers...`, `mod_count_images 0.2.0`, `mod_vocabulary 0.3.0`, ...). The report shows no interim notice for it. Regenerating it reads the finished project in about 6 s:

```
python tools/reference_aggregates.py --project <TTA-ref-2026-11>/project \
    --harvest-root <harvester>/data --status release \
    --source "Reference theses of HU Berlin (edoc) and ETH Zurich, ... re-run of <date> ..."
```

A module change that moves a reference metric means a new re-run and a regenerated file before the next release (Revisit when).

The `source` text is stored in the package, so it must not contain the repository-specific phrases that [ADR-0023](0023-researcher-cover-rulesets.md) keeps out of `tta/` (its guard test covers `.json` files): say "ETH Zurich", not the repository's own name.

**11. The report under two thresholds (rev. 2).** A bucket whose metric has only the inner statistics draws the median line and the 25th-75th band and **no 5th-95th band** for that year; the outer band is drawn in runs of consecutive years that have it, exactly like the inner band in runs of years with a bucket, and a lone year is a short block. Highlighting (`band_level`) then only distinguishes inside / outside the 25th-75th percentile: a value outside it is level 1, never level 2 - the report makes no "outside the 5th-95th percentile" claim without p05/p95. The reference caption names both thresholds.

## Revision 2 (2026-11-18): one threshold per statistic

**Why.** Rev. 1's single threshold of 10 left the bachelor reference almost empty: German bachelor theses had an all-fields band in only 3 of 23 years. Lowering one common threshold closes that gap but makes the outer band erratic: with few values the 5th and 95th percentiles are effectively the minimum and maximum of the bucket, i.e. close to individual theses, and the "outside 5-95" highlights would follow single reference theses. Median and quartiles are much more stable on a short series. So each statistic gets the threshold its stability allows (owner decision 2026-11-18, for release 1.0.0).

**Analysis.** On the released source (the 2026-11-18 HU+ETH re-run, `TTA-ref-2026-11`), the generator (`build_aggregates` with one common threshold k; a bucket counts if at least one metric reaches k; n >= 10 reproduces rev. 1's 122 buckets):

| bucket | n>=2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| yearly summary (all/all/all) | 23 | 23 | 23 | 23 | 22 | 22 | 22 | 22 | 22 |
| bachelor/de, all fields | 21 | 18 | 15 | 13 | 12 | 7 | 5 | 4 | 3 |
| bachelor/en, all fields | 15 | 12 | 12 | 11 | 11 | 9 | 7 | 7 | 7 |
| master/de, all fields | 23 | 22 | 22 | 22 | 22 | 22 | 22 | 22 | 22 |
| master/en, all fields | 23 | 23 | 22 | 22 | 22 | 22 | 22 | 22 | 21 |
| bachelor/de, single field | 25 | 11 | 6 | 2 | 1 | 1 | 1 | 0 | 0 |
| bachelor/en, single field | 20 | 16 | 5 | 1 | 1 | 0 | 0 | 0 | 0 |
| master/de, single field | 49 | 39 | 37 | 32 | 29 | 27 | 24 | 21 | 19 |
| master/en, single field | 81 | 73 | 62 | 55 | 47 | 43 | 37 | 29 | 28 |
| total buckets | 280 | 237 | 204 | 181 | 167 | 153 | 140 | 127 | 122 |
| metric statistics (bucket x metric) | 5880 | 4977 | 4284 | 3801 | 3507 | 3213 | 2940 | 2667 | 2562 |

n >= 4 is where the bachelor gap mostly closes (bachelor/de all fields 3 -> 15 years); below it, the quartiles of 2-3 values are no longer a band.

**Result under rev. 2** (same source, regenerated with `--status release`; a bucket "also gets the outer band" if at least one of its metrics reaches 20):

| bucket | with inner band (n>=4) | also with outer band (n>=20) |
|---|---:|---:|
| yearly summary (all/all/all) | 23 | 22 |
| bachelor/de, all fields | 15 | 0 |
| bachelor/en, all fields | 12 | 5 |
| master/de, all fields | 22 | 18 |
| master/en, all fields | 22 | 18 |
| bachelor/de, single field | 6 | 0 |
| bachelor/en, single field | 5 | 0 |
| master/de, single field | 37 | 6 |
| master/en, single field | 62 | 10 |
| **total buckets** | **204** | **79** |

4,284 metric series ship (each with mean, median, p25, p75), 1,659 of them also with p05 and p95: 20,454 numbers (rev. 1: 2,562 series x 6 = 15,372). The file grows from 158 KB to 255 KB (158,403 -> 255,436 bytes). German bachelor theses get an inner band in 15 years but an outer band in none: no year has 20 of them in the reference.

## Alternatives considered

- **Ship per-thesis reference values** (or a histogram per bucket). Would allow percentile ranks and tests in the report, but ships third-party thesis data and grows the file by orders of magnitude. Rejected by the owner.
- **Ship n per bucket.** Lets a reader judge the precision of a band, but reveals the corpus composition per field and year. Rejected by the owner; the thresholds are the only guarantee.
- **One common threshold** (rev. 1: 10 for all six statistics). Either too high for the bachelor buckets (10) or too low for a meaningful outer band (4). Superseded by rev. 2.
- **Common threshold below 4** (2 or 3). More bachelor buckets (bachelor/de single field: 25 at n >= 2), but quartiles of two or three values are not a band. Rejected.
- **Field by subject detection.** Not available (#44).
- **Generator as `tta reference build`.** See decision 9.

## Consequences

- ✅ The report compares against the reference fully offline, with a few hundred KB of data.
- ✅ One population rule and one derivation for both sides; the threshold and the no-counts rule are tested on the file itself.
- ⚠️ Only the six statistics travel: nothing in the report can use individual reference values (no significance test, no percentile rank, no per-field correlation).
- ⚠️ An inner band of a sparse bucket rests on as few as 4 theses, an outer band on as few as 20, and the report cannot say so (no n by decision); the caption names both thresholds.
- ⚠️ Where only the inner band exists, the report cannot say whether a thesis is far outside the reference, only that it is outside the middle half (rev. 2).
- ⚠️ The reference covers two repositories; fields they rarely serve have no buckets.
- ⚠️ Values belong to one analysis version. A module change that moves a metric makes the shipped file stale until it is regenerated; `analysed_with` records which versions it reflects.

## Revisit when

- A module version change moves a reference metric (regenerate before release).
- More repositories join the reference corpus.
- The HAW/Mittweida follow-up corpus fills the bachelor buckets: re-run the bucket-count analysis of rev. 2; with enough bachelor theses per year a single, higher threshold (or an outer band for bachelor/de) may be within reach.
- Subject detection (#44) lands - then the field filter can also act on the professor's theses.
