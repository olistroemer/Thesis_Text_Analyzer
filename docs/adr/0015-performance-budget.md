# ADR-0015: Performance budget

**Status:** Accepted
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
