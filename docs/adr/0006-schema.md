# ADR-0006: Database schema — unified, source-aware, append-only history

**Status:** Accepted (revision 3)
**Date:** 2026-06-03
**Drivers:** ADR-0004 (modules + versions), ADR-0005 (producer swap deferred), US-PROF-EXCLUDE, US-PROF-ATTRS, US-RES-IMPORT, US-RES-LOCAL-RERUN, QA-TEST, QA-PRIV.

## Decision

SQLite database, single unified schema for both the professor's local DB and the researcher's merged DB. Identity is content-addressed (`pdf_sha256`). Re-runs append rather than overwrite; the "current" state is exposed via the `v_current_metrics` view. Migrations are numbered forward-only SQL files; the migrator records applied versions in `schema_version`.

## Tables

```
schema_version       (version, applied_at)
sources              (id, name, kind ∈ {local, imported}, institution, app_version, …)
theses               (id, source_id, pdf_sha256, pdf_path, …, type, language_hint, excluded, …)
module_runs          (id, thesis_id, module_name, module_version, status, started_at, duration_ms)
metric_values        (run_id, metric_name, value_num, value_text)
artefact_files       (thesis_id, kind, relative_path, run_id, …)
```

## Views

- `v_current_metrics` — latest invocation per `(thesis_id, module_name)`; bound by the data grid.
- `v_module_run_history` — full history with `recency_rank = 1` for the current row, `> 1` for older runs.

## Source awareness

Exactly one row in `sources` with `kind='local'` on a freshly-initialised DB. Imported exports add rows with `kind='imported'`. The runner filter at SDD §5.3 ensures only `kind='local'` theses are re-run; imported data is read-only context.

## Why content-addressed identity (`pdf_sha256`)

Renaming or moving the PDF doesn't lose its history. Loaders compute the hash on add; if a hash already exists, the path is updated but invocations are preserved.

## Alternatives considered

- **Producer-chain table + multi-value-per-metric.** Original design; rolled back in [ADR-0005](0005-producer-swap-deferred.md) as too complex for the professor's experience.
- **Two separate schemas (local vs merged).** Briefly proposed; rolled back — same schema with a `source_id` dimension serves both.
- **File-per-thesis (CSV/JSON in a directory).** Pivot/comparison queries become Python join logic; consistency under concurrent writes is fragile. Rejected.
- **DuckDB.** Nicer analytics SQL, but SQLite is stdlib and ubiquitous, and analyst tooling is widespread. Rejected for MVP.

## Consequences

- ✅ Content-addressed identity makes renaming/moving PDFs safe.
- ✅ Append-only history surfaces stale-row detection (`module_runs.module_version` vs live module version) and supports module-version diagnosis.
- ✅ Single schema serves both modes; if we ever split the tools, no schema migration needed.
- ✅ Views isolate query complexity from caller code.
- ✅ Migrations testable from scratch every test run.
- ⚠️ Numeric / text split (`value_num`, `value_text`) forces "is this a metric or an artefact?" decision per output. Good discipline.
- ⚠️ PII annotation is convention only; export module owns enforcement.

## Revisit when

Sample sizes outgrow SQLite ergonomics (unlikely; tens of thousands of theses still fit comfortably).
