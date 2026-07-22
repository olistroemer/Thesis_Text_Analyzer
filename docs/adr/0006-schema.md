# ADR-0006: Database schema — unified, source-aware, append-only history

**Status:** Accepted (revision 4 — SHA-256 hashing deferred from add time to first-run time; `pdf_sha256` is NULL until a thesis is first analysed; add-time identity/dedup keys on path, content identity/dedup applies at run time. See #38.)
**Date:** 2026-06-03 (rev. 4: 2026-07-22)
**Drivers:** ADR-0004 (modules + versions), ADR-0005 (producer swap deferred), US-PROF-EXCLUDE, US-PROF-ATTRS, US-RES-IMPORT, US-RES-LOCAL-RERUN, US-RES-LOW-FRICTION (rev. 4: instant add), QA-TEST, QA-PRIV.

## Decision

SQLite database, single unified schema for both the professor's local DB and the researcher's merged DB. Identity is content-addressed (`pdf_sha256`), but the hash is computed **lazily at first-run time**, not at add time (rev. 4, #38): adding a thesis must be instant (no full file read), so `add_thesis` stores `pdf_sha256 = NULL` and dedups on **path** within the source; the content hash is computed once when the thesis is first analysed and persisted then, and content-dedup (folding two path-added rows that turn out to be byte-identical) is applied at that point. Re-runs append rather than overwrite; the "current" state is exposed via the `v_current_metrics` view. Migrations are numbered forward-only SQL files; the migrator records applied versions in `schema_version`.

## Tables

```
schema_version       (version, applied_at)
sources              (id, name, kind ∈ {local, imported}, institution, app_version, …)
theses               (id, source_id, pdf_sha256 NULL-until-first-run, pdf_path, pdf_filename, excluded, …)
module_runs          (id, thesis_id, module_name, module_version, status, started_at, duration_ms)
metric_values        (run_id, metric_name, value_num, value_text)
artefact_files       (thesis_id, kind, relative_path, run_id, …)
```

The former `theses.type` and `theses.language_hint` override columns were **dropped** in favour of a detected `thesis_type` metric and the existing `language_code` metric — see [ADR-0019](0019-thesis-type-by-detection.md).

## Views

- `v_current_metrics` — latest invocation per `(thesis_id, module_name)`; bound by the data grid.
- `v_module_run_history` — full history with `recency_rank = 1` for the current row, `> 1` for older runs.

## Source awareness

Exactly one row in `sources` with `kind='local'` on a freshly-initialised DB. Imported exports add rows with `kind='imported'`. The runner filter at SDD §5.3 ensures only `kind='local'` theses are re-run; imported data is read-only context.

## Why content-addressed identity (`pdf_sha256`)

Content-addressing means a thesis keeps its history across renames/moves and gives a portable cross-export identifier. **The hash is not computed on add** (rev. 4, #38): reading every file to hash it made adding a folder of PDFs feel like the app had hung, which the low-friction contribute loop (US-RES-LOW-FRICTION) cannot afford. Instead:

- **Add time** — `add_thesis` is instant: it stores `pdf_sha256 = NULL` and `pdf_size_bytes` (a cheap `stat`, no read), and dedups on `(source_id, pdf_path)`. Re-adding the same path updates the filename/size and keeps the row's identity and run history.
- **First-run time** — before a thesis's modules execute, the main process (the sole DB writer, [ADR-0013](0013-runner-orchestration.md)) computes the SHA-256 once and persists it. If the freshly-computed hash matches an already-hashed sibling in the same source (two different paths, byte-identical content), the newer row is **folded** into the canonical one: its runs/artefacts are discarded, the canonical adopts the most-recently-seen path, and the duplicate row is removed. The `UNIQUE (source_id, pdf_sha256)` constraint therefore holds over all non-NULL hashes.

The tradeoff: between add and first run, a moved/renamed file added under a new path is a distinct row (its content identity is not yet known); the fold at run time reunites them. This is accepted — analysis is where content identity first matters.

## Alternatives considered

- **Producer-chain table + multi-value-per-metric.** Original design; rolled back in [ADR-0005](0005-producer-swap-deferred.md) as too complex for the professor's experience.
- **Two separate schemas (local vs merged).** Briefly proposed; rolled back — same schema with a `source_id` dimension serves both.
- **File-per-thesis (CSV/JSON in a directory).** Pivot/comparison queries become Python join logic; consistency under concurrent writes is fragile. Rejected.
- **DuckDB.** Nicer analytics SQL, but SQLite is stdlib and ubiquitous, and analyst tooling is widespread. Rejected for MVP.

## Consequences

- ✅ Content-addressed identity makes renaming/moving PDFs safe (reunited at first run, rev. 4).
- ✅ Adding theses is instant regardless of file size or count (rev. 4, #38): no file is read until analysis.
- ⚠️ `pdf_sha256` is NULL for a thesis added but never analysed; any code relying on it (export identity, content-dedup) must tolerate NULL until the first run. Export keeps the column nullable and never fabricates a hash.
- ✅ Append-only history surfaces stale-row detection (`module_runs.module_version` vs live module version) and supports module-version diagnosis.
- ✅ Single schema serves both modes; if we ever split the tools, no schema migration needed.
- ✅ Views isolate query complexity from caller code.
- ✅ Migrations testable from scratch every test run.
- ⚠️ Numeric / text split (`value_num`, `value_text`) forces "is this a metric or an artefact?" decision per output. Good discipline.
- ⚠️ PII annotation is convention only; export module owns enforcement.

## Revisit when

Sample sizes outgrow SQLite ergonomics (unlikely; tens of thousands of theses still fit comfortably).
