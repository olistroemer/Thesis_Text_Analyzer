# ADR-0015: Performance budget

**Status:** Accepted (note 2026-10-14: [worker reuse](#worker-reuse-2026-10-14-86), #86; note 2026-11-17: [two text views](#two-text-views-2026-11-17-22), #22)
**Date:** 2026-06-03
**Drivers:** QA-RES, US-RES-LOW-FRICTION (step 3 of the contribute loop must finish in reasonable time), US-PROF-INSIGHTS (Report needs current data fast); running on a 10-year-old laptop is a hard requirement, not a stretch goal.

## Decision

The MVP commits to the performance budget in SDD §10. The runner picks worker count from `max(1, os.cpu_count() - 1)`. A `pytest-benchmark` suite enforces per-module and per-pipeline budgets on every CI build with 20 % slack; a 50-thesis end-to-end benchmark runs nightly with 40 % slack and reports trends.

## Headline numbers (50-thesis batch, full pipeline)

| Hardware (typical) | Wall-clock |
|---|---|
| 2-core / 4 GB / HDD (≈ 2016 laptop) | ≤ 60 min |
| 4-core / 8 GB / SSD (≈ 2020 laptop) | ≤ 15 min |
| 8-core / 16 GB / NVMe (≈ 2023 workstation) | ≤ 6 min |

The application must **run without crashing** on the lower-end machine. Headline numbers are derived from the ETH side-quest measurements (PyMuPDF ≈ 6 s/thesis on a modern laptop, ≈ 4× slower on a 2016 dual-core).

## Per-module time budgets (median 100-page thesis, supported tier)

| Module | Budget |
|---|---|
| `mod_extract_pymupdf` | ≤ 6 s |
| `mod_check_extraction_quality` | ≤ 100 ms |
| `mod_classify_language` | ≤ 500 ms |
| `mod_tokenize` | ≤ 4 s |
| `mod_surface_counts` | ≤ 200 ms |
| `mod_vocabulary` | ≤ 300 ms |
| `mod_readability` | ≤ 500 ms |
| `mod_redundancy` | ≤ 400 ms |
| `mod_count_images` | ≤ 2 s |
| `mod_extract_pdf_metadata` | ≤ 1 s |
| **per-thesis sum** | **≤ 15 s** (allowing I/O overhead) |

## Memory budget

- Per worker peak: ≤ 1 GB (≤ 700 MB on the 4 GB tier).
- Main process steady state: ≤ 200 MB.

## Worker reuse (2026-10-14, #86)

Workers are long-lived since [ADR-0013](0013-runner-orchestration.md#worker-reuse) rev. 3, so library start-up (nltk/textstat/langdetect/PyMuPDF) is paid once per worker instead of once per thesis. On the exp-86 reference machine (i7-13700H, native Windows, 200-thesis sample) that is ~2-2.6 s per worker plus a median ~1.1 s per thesis, against ~3.0 s per thesis before (with #85's `mod_count_images`: ~0.9 s per thesis against ~3.0 s, wall clock at 1 worker); the per-module budgets above are unchanged and remain ceilings. Two consequences for this ADR:

- **The ETA no longer takes its priors from the budget table.** The budgets are ceilings that contained the per-thesis start-up; the estimator's priors are the measured warm-worker means per module plus a one-off start-up term (SDD Sec. 5.5).
- **The memory budget now applies to a long-lived worker.** Its steady state is ~330-350 MB once `mod_readability` clears its library caches; a large PDF's transient peak sits on that base. A worker still above the per-worker budget after a thesis is recycled (`[runner] recycle_above_rss_mb`, default 1024 MiB = the budget; the 4 GB tier lowers it by hand).

## Two text views (2026-11-17, #22)

`mod_extract_pymupdf` 0.2.0 serialises each page's `TextPage` twice, as plain text (`raw_text`) and as a span `dict` that the font filter rebuilds into `prose_text` ([ADR-0024](0024-two-text-views.md)). Exp #22 measured the filter (arm B, `dict` only) at +18 % over the plain extraction: median 1.0 s per 100 pages on the full reference corpus with 19 parallel workers on 20 logical cores, 1.6 % of theses over 6 s per 100 pages (plain extraction: 0.8 s, 1 %). The shipped module (one `TextPage`, both serialisations, the whole-document guard, both files written) was measured on a 100-thesis sample of the reference corpus (7,771 pages, one process, median of three runs each, same Windows laptop, PyMuPDF 1.28.2): median **0.25 s per 100 pages** (p90 0.49 s), against 0.12 s for the plain `get_text("text")` of 0.1.0 (without its file write) and 0.21 s for arm B's `dict` alone; per thesis the median ratio is 1.75x the plain extraction and 1.1x arm B. All three stay far inside the unchanged **≤ 6 s** budget; the one sample thesis above it (a 10-page ETH plan, 23 s per 100 pages) is equally slow in every variant. `mod_tokenize` and `mod_readability` read a slightly shorter text, so their budgets are unaffected.

## Pause / resume — a free feature

Because of ADR-0006's append-only history and (thesis × module) granularity, users can quit the app mid-batch and resume on the next launch. "Run all" defaults to picking up missing/stale work. This is the answer to "what if it takes too long in one sitting?" on slow machines — close the laptop, continue tomorrow.

## Adaptive runtime degradation: deferred

The mechanism to detect slow execution mid-batch and offer to skip optional modules is deferred to post-MVP — see SDD §12. The MVP relies on the user manually selecting modules (US-PROF-SELECT) if they want a smaller workload.

## Consequences

- ✅ 10-year-old hardware is explicitly supported.
- ✅ Concrete numbers anchor implementation choices and catch CI regressions.
- ✅ Pause/resume is a free feature from the schema design.
- ⚠️ Without adaptive degradation, slow-machine users must manually choose subsets if the full pipeline is too long.
- ⚠️ The 2-core tier number is derived (× 4 from supported tier), not directly benchmarked; CI runners cover the supported tier as proxy.
- ⚠️ PyMuPDF is the initial extractor; the AGPL release gate forces a swap before distribution, and post-swap numbers will need re-validation.

## Revisit when

- Real-world feedback shows the slow-tier numbers are unacceptable → adopt the §12 adaptive-degradation mechanism.
- LM-based modules land and need their own tier (likely "fast hardware only" with explicit gating).
- Library-comparison study completes; swap budget anchors to the winning extractor.
