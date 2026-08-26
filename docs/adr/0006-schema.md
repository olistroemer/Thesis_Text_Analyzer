# ADR-0006: Database schema — unified, source-aware, append-only history

**Status:** Accepted (revision 5 — SHA-256 hashing deferred from add time to first-run time (rev. 4, #38); excluding an already-analysed thesis **scrubs** its cached analysis via `purge_analysis`, an intentional, documented exception to append-only history (#11). See below.)
**Date:** 2026-06-03 (rev. 4: 2026-07-22; rev. 5: 2026-07-23)
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

## Excluded-thesis scrub — an intentional append-only exception (rev. 5, #11)

Toggling `excluded` **on** for a thesis that has already been analysed **deletes its cached analysis** (US-PROF-EXCLUDE, QA-PRIV): `Repository.purge_analysis(thesis_id)` removes, in **one transaction**, the thesis's `metric_values` (joined via its `module_runs.run_id`), its `module_runs`, and its `artefact_files` rows, then removes the on-disk `artefacts/<thesis_id>/` tree via `ArtefactStore.purge`. The `theses` row is **kept** with `excluded=1` so the content-addressed identity is remembered and the thesis is never silently re-analysed. Toggling `excluded` **off** clears the flag and the thesis becomes eligible again (it re-runs as "missing").

This **deliberately breaks the append-only-history guarantee** (QA-AUDIT) for that one thesis. The tension is accepted:

- Excluded theses are **already absent** from every export ([ADR-0007](0007-export-format.md): rows where `excluded=1` are stripped, and the whole `artefact_files`/artefact tree never leaves the machine) and from report aggregates ([ADR-0016]). So the scrub changes nothing about what leaves the machine or what a downstream auditor sees.
- The value it adds is **local defence-in-depth**: "I changed my mind — remove the raw text and tokens for this document from my disk now," rather than leaving PII-bearing artefacts cached until the next vacuum. The artefacts (`raw_text`, `tokens`, `pdf_metadata`) are the real PII (`CONTENT`/`IDENTIFYING`, [ADR-0009](0009-privacy-as-code.md)); metrics are non-PII but are scrubbed too for a clean, unambiguous "this thesis carries no analysis" state.
- Excluding **before** any run needs no scrub: the runner's `plan()` already skips excluded theses, so no `raw_text`/tokens are ever extracted or cached in the first place.

The scrub is destructive and irreversible (locally), but the **source PDF is untouched** — re-including and re-running reconstructs the analysis from scratch. Both adapters reach it after a confirmation step (GUI dialog; CLI `tta exclude` prompt, `--yes` to skip). Until rev. 6 this was the *only* sanctioned deletion path; **removal** (next section) is the second, and the two are deliberately different operations. If the on-disk file removal fails (e.g. a locked file), the DB scrub has already committed and the failure is **surfaced** (GUI warning; CLI stderr + `EX_PARTIAL` exit) rather than silently reported as a clean scrub; the residual files never leave the machine ([ADR-0007](0007-export-format.md)), so this is a local-only warning, not a disclosure.

## Removing a mis-added thesis — the second sanctioned deletion path (rev. 6, #63)

`Repository.delete_thesis(thesis_id, store=None)` **forgets** a thesis: in one transaction it deletes the thesis's `metric_values` (joined via its `module_runs`), its `artefact_files` and `module_runs` rows — and then the `theses` row itself — after which `ArtefactStore.purge` removes the on-disk `artefacts/<thesis_id>/` tree. Same ordering and same contract as `purge_analysis`: the DB commit precedes the filesystem step, and an `OSError` from `store.purge` propagates so the caller can warn that local artefact files were not fully removed (those files never leave the machine, [ADR-0007](0007-export-format.md), so it is a local-only warning). The source PDF is untouched.

**Why this is a different operation from exclude, not a stronger setting of it.** The two answer different questions, and the difference is entirely about whether the thesis's *identity* is worth keeping:

- **Exclude** means *"this thesis exists and is deliberately not analysed."* Its identity matters: the `theses` row stays with `excluded=1` so the content-addressed row blocks a silent re-analysis, and un-ticking the box re-admits it. Keeping the row is the point.
- **Remove** means *"this was a mistake; forget it."* A PDF added by fat-fingering the wrong folder has no identity worth remembering — remembering it is precisely the harm, because the remembered row would keep blocking a clean re-add of the same file. So the row goes too, and the same PDF can afterwards be added again as a fresh thesis with a fresh id and no history.

Consequently exclude is **not** a prerequisite for remove, and remove is **not** reversible by including: there is nothing left to include.

**One delete implementation, three callers.** The row-level deletes live in a single private helper; `delete_thesis` wraps it in a transaction and adds the filesystem purge, and the content-dedup fold in `assign_content_hash` calls the same helper *inside its own* transaction (the fold must apply the canonical row's path update and the duplicate's removal atomically, so it cannot nest `delete_thesis`'s transaction). Before rev. 6 the fold carried its own copy of the four `DELETE`s — the only place in the codebase that executed `DELETE FROM theses`, and unreachable by a user.

Both adapters gate removal behind a confirmation that says plainly that the analysis results are destroyed and the row is forgotten (`tta remove <id>`, `--yes` to skip for scripts; a GUI dialog). Removal is destructive and irreversible.

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
- ✅ Adding theses is instant regardless of file **size** (rev. 4, #38: no file is read until analysis) and scales in **count** (#61: a batch of adds is one transaction, so N PDFs cost O(1) commits rather than N fsyncs - see SDD Sec. 8.1).
- ⚠️ `pdf_sha256` is NULL for a thesis added but never analysed; any code relying on it (export identity, content-dedup) must tolerate NULL until the first run. Export keeps the column nullable and never fabricates a hash.
- ✅ Append-only history surfaces stale-row detection (`module_runs.module_version` vs live module version) and supports module-version diagnosis.
- ⚠️ Append-only history has exactly **two** sanctioned exceptions, both scoped, both confirmed in the adapters, both documented above: `purge_analysis` deletes an excluded thesis's cached analysis but keeps its row (rev. 5, #11), and `delete_thesis` deletes the row as well for a thesis added by mistake (rev. 6, #63). No other code path deletes rows; the content-dedup fold shares `delete_thesis`'s implementation.
- ✅ Single schema serves both modes; if we ever split the tools, no schema migration needed.
- ✅ Views isolate query complexity from caller code.
- ✅ Migrations testable from scratch every test run.
- ⚠️ Numeric / text split (`value_num`, `value_text`) forces "is this a metric or an artefact?" decision per output. Good discipline.
- ⚠️ PII annotation is convention only; export module owns enforcement.

## Revisit when

Sample sizes outgrow SQLite ergonomics (unlikely; tens of thousands of theses still fit comfortably).
