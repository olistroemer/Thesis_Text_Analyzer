# ADR-0025: Reference aggregates shipped inside the app

**Status:** Accepted
**Date:** 2026-11-18
**Drivers:** #84 (owner decisions 2026-11-18), #49 (reference baselines), US-PROF-COMPARE, US-PROF-TRENDS, [ADR-0016](0016-report-view.md) rev. 3 (the professor report that consumes them), [ADR-0019](0019-thesis-type-by-detection.md) rev. 3 (`REFERENCE_THESIS_TYPES`), [ADR-0003](0003-cli-first-class.md) (researcher tooling stays out of the GUI), QA-PRIV, QA-REPRO.

## Context

The professor report ([ADR-0016](0016-report-view.md) rev. 3) compares the professor's own theses with the research team's reference corpus (the harvested bachelor and master theses of HU Berlin edoc and the ETH Research Collection). The app is offline (QA-PRIV), so the comparison must travel inside the binary. Shipping the corpus itself, or per-thesis values, is out: it is the wrong size, and per-thesis values of third-party theses have no business in an app handed to professors. What the report needs per year is a centre and a spread, so it ships exactly that.

## Decision

**1. One data file in the package.** `tta/core/report_assets/reference_aggregates.json`, package data (`pyproject.toml` `package-data`, `packaging/tta.spec` `datas`). The report reads it through `core.reference.load_shipped()` (`importlib.resources`, read-only, the `help_corpus` pattern). Nothing writes it at run time; nothing outside the report reads it.

**2. Six statistics per bucket and metric, no counts.** For every bucket and metric: **mean, median, 5th, 25th, 75th and 95th percentile**. Percentiles use linear interpolation between the closest ranks (`statistics.quantiles(..., method="inclusive")`, numpy's default, the same convention as the grid's IQR rule). **No n and no corpus size appear anywhere** in the file or in the report; the file carries only the threshold constant `min_theses` (below). Values are rounded to 4 significant digits.

**3. Buckets.**

| type | language | field | year |
|---|---|---|---|
| `bachelor`, `master` | `de`, `en` | DDC main class `000` ... `900` | 2003-2025 |
| `bachelor`, `master` | `de`, `en` | `all` (every field, **including theses without a known field**) | 2003-2025 |
| `all` | `all` | `all` (yearly summary: every reference thesis of that year) | 2003-2025 |

"Unknown field" is never a bucket of its own; such theses count in the `all` buckets only.

**4. Population.** A reference thesis counts if it is local, not excluded, not `extraction_quality = garbled` (the report's own rule), its detected `thesis_type` is in `REFERENCE_THESIS_TYPES` (`bachelor`, `master`) and its detected `publication_year` lies in 2003-2025. The split buckets additionally need a detected `language_code` of `de` or `en`; the yearly summary takes every language. **Type, language and year are the app's detected metrics** (#81/#82 detectors), never the repository's metadata, so a reference thesis is classified exactly as the professor's own theses are. Per metric, only theses with a value for that metric count.

**5. The threshold: >= 10 theses per bucket and metric.** A statistic is shipped only if at least 10 theses have a value for that metric in that bucket; a bucket with no such metric is not shipped. Every bucket is computed directly from individual theses, so the theses of a dropped small bucket still count in the coarser buckets of the same year (the `all`-field bucket of their type and language, and the yearly summary).

**6. Field = DDC main class from the harvest metadata.** The first DDC code of the repository record (ETH: `info:eu-repo/classification/ddc/NNN`; edoc: `ddc:NNN` and labelled `NNN Label` subjects), folded to its main class (`000`, `100`, ..., `900`). It is joined by PDF file stem through the harvester's `downloads.pdf_path` (`<harvest>/data/<host>/theses.sqlite`), the linkage of the `explore/plotly-report` trial. Field is the one attribute the app cannot detect (subject detection is #44); the report therefore offers it as a filter **on the reference only**.

**7. Metric catalogue.** `core.reference.METRIC_GROUPS`, three groups as in the report: **length** (`word_count`, `n_pages`, `char_count_alpha`, `text_chars`, `sentence_count`, `n_images`, `avg_sentence_len`, and the derived `file_size_mb`, `words_per_page`, `images_per_page`, `kb_per_page`), **style** (`flesch_reading_ease`, `yules_k`, `avg_word_len`, `std_sentence_len`, `bigram_repetition_rate`, `trigram_repetition_rate`) and **vocabulary** (`ttr`, `root_ttr`, `hapax_token_ratio`, `hapax_type_ratio`). Derived metrics are computed by the one function `core.reference.derive_metrics`, used by both the generator and the report, so both sides compute them identically. Metrics the report does not plot (years, confidences, categories) are not aggregated.

**8. Format.**

```json
{
  "_comment": "...",
  "format": "tta-reference-aggregates",
  "format_version": 1,
  "status": "interim",
  "source": "free text: which corpus, which analysis run",
  "generated": "2026-11-18",
  "generator": "tools/reference_aggregates.py (tta 0.x)",
  "analysed_with": ["mod_extract_pymupdf 0.2.0", "..."],
  "years": [2003, 2025],
  "min_theses": 10,
  "stats": ["mean", "median", "p05", "p25", "p75", "p95"],
  "metrics": ["word_count", "..."],
  "fields": ["000", "100", "..."],
  "rows": [
    {"type": "bachelor", "language": "de", "field": "300", "year": 2015,
     "values": {"word_count": [mean, median, p05, p25, p75, p95], "...": []}}
  ]
}
```

`status` is `interim` or `release`. `analysed_with` lists the module versions the reference project's current results were produced with (QA-REPRO: a reader can tell which analysis the numbers belong to). Rows are sorted (year, type, language, field), keys in a fixed order, so a regeneration diffs cleanly.

**9. Generator: `tools/reference_aggregates.py`, researcher tooling.**

```
python tools/reference_aggregates.py --project <reference project folder or tta.sqlite> \
    --harvest-root <harvester>/data [--status interim|release] [--source TEXT] \
    [--out tta/core/report_assets/reference_aggregates.json]
```

It opens the project database **read-only** (an SQLite `mode=ro` URI, never through `Project.open`, which may migrate), so it can read a project another process is still analysing. Harvest-specific code (the harvester's database layout, OAI-DC parsing) lives in the tool; the pure parts (population rule, bucket statistics, threshold, file format) live in `core/reference.py` and are unit-tested.

Why `tools/` and not a `tta` subcommand: the generator depends on the research team's private harvest layout, which is not a contract of the app; it runs when a release is prepared, never at run time; and its output is a committed package file. Under [ADR-0003](0003-cli-first-class.md) a `tta` subcommand would put harvest-specific code into every professor's binary for nothing. `tools/` is never frozen (SDD §5.6.5), like `tools/screenshots.py`.

**10. Interim data (2026-11-18).** The first committed file is generated from the last complete reference run (`TTA-exp22/ref_tta.sqlite`, 2026-09), which predates the #81/#82 detectors and the #22 text views; it is marked `"status": "interim"` with that provenance in `source`, and the report says so in its reference caption. It is replaced by a file generated from a re-run of the HU+ETH corpus with the release's code (with the ETH cover ruleset, [ADR-0023](0023-researcher-cover-rulesets.md)) **before the next release**; the release file carries `"status": "release"`.

Re-running is cheap: the HU+ETH re-run of 2026-11-18 (3,275 PDFs, main `fbe297c`, ETH cover ruleset) took 946 s on the development machine, and the generator reads the finished project in about 6 s:

```
python tools/reference_aggregates.py --project <TTA-ref-2026-11>/project     --harvest-root <harvester>/data --status release     --source "reference theses of HU Berlin (edoc) and ETH Zurich, re-run 2026-11-18, main fbe297c"
```

The `source` text is stored in the package, so it must not contain the repository-specific phrases that [ADR-0023](0023-researcher-cover-rulesets.md) keeps out of `tta/` (its guard test covers `.json` files): say "ETH Zurich", not the repository's own name.

## Alternatives considered

- **Ship per-thesis reference values** (or a histogram per bucket). Would allow percentile ranks and tests in the report, but ships third-party thesis data and grows the file by orders of magnitude. Rejected by the owner.
- **Ship n per bucket.** Lets a reader judge the precision of a band, but reveals the corpus composition per field and year. Rejected by the owner; the >= 10 threshold is the only guarantee.
- **Field by subject detection.** Not available (#44).
- **Generator as `tta reference build`.** See decision 9.

## Consequences

- ✅ The report compares against the reference fully offline, with a few hundred KB of data.
- ✅ One population rule and one derivation for both sides; the threshold and the no-counts rule are tested on the file itself.
- ⚠️ Only the six statistics travel: nothing in the report can use individual reference values (no significance test, no percentile rank, no per-field correlation).
- ⚠️ Bands of a sparse bucket rest on as few as 10 theses and the report cannot say so (no n by decision).
- ⚠️ The reference covers two repositories; fields they rarely serve have no buckets.
- ⚠️ Values belong to one analysis version. A module change that moves a metric makes the shipped file stale until it is regenerated; `analysed_with` records which versions it reflects.

## Revisit when

- A module version change moves a reference metric (regenerate before release).
- More repositories join the reference corpus.
- Subject detection (#44) lands - then the field filter can also act on the professor's theses.
