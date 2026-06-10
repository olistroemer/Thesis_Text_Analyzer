# ADR-0007: Export format — SQLite, PII-stripped, history always included

**Status:** Accepted (revised — history always included; no UI checkbox)
**Date:** 2026-06-03
**Drivers:** US-PROF-EXPORT, US-RES-IMPORT, US-RES-LOW-FRICTION (no extra choices in step 4 of the contribute loop), QA-PRIV, debugging value of run history for the research team.

## Decision

Export is a single SQLite file with the same schema as the local DB minus PII columns and the `artefact_files` table, plus an `export_info` metadata table.

**The export always includes the full `module_runs` + `metric_values` history** (minus PII columns and excluded theses). The research team retains debugging value; the size cost is trivial (~700 KB extra per 100 theses across 5 re-runs). No UI checkbox; one less decision in step 4 of the professor's happy path.

Power users can still use `pds export --current-only` from the CLI to produce a trimmed export from `v_current_metrics` only.

## Why SQLite for export, not JSON / CSV / zip

- Researcher imports trivially via SQL: `ATTACH DATABASE 'professor_export.sqlite' AS src;` then `INSERT-SELECT FROM src.<table>`.
- The schema travels with the data; researcher needs no separate spec to interpret columns.
- Diffable, queryable in any sqlite tool, no parsers to write.
- One file, easy to email.

## What's stripped vs the local DB

- PII columns on `theses`: `pdf_path`, `pdf_filename`, `notes`, `tags`.
- Rows where `theses.excluded = 1`.
- The entire `artefact_files` table (contents = raw text + tokens + full PDF metadata = full PII risk).
- `module_runs.error_traceback` (may include filesystem paths).
- `theses.added_at` is rounded to day to reduce timing fingerprints.
- `theses.id` is preserved as-is (it's just an integer, no PII).
- `pdf_sha256` is preserved (PII-free, used as portable cross-export identifier).

## Pre-export confirmation UI

The GUI's export dialog displays:

- Exact row count being exported.
- File path picker (defaults to `<project>/exports/<institution>-<YYYY-MM-DD>.sqlite`; creates the `exports/` directory if missing).
- A single "Export" confirmation button.

No "history?" checkbox in MVP — history is always included.

## Alternatives considered

- **CSV export.** Loses relational structure; researcher would need to reconstruct foreign keys. Rejected.
- **JSON export.** Same as CSV plus an external schema file. Rejected for the schema-travels-with-data argument.
- **Encrypted zip with signed manifest.** Overkill for the MVP threat model (sending to known colleagues). Future work if institutional ethics boards require it.

## Consequences

- ✅ Researcher's import is one SQL transaction, no glue code.
- ✅ Export file is human-inspectable before sending.
- ✅ History is retained for debugging.
- ⚠️ If a professor's `tags` JSON contains identifying info (their fault), it doesn't escape — we strip `tags` entirely in MVP. Power users with safe tags will complain; we add an allowlist in v2.
- ⚠️ Schema evolution requires migration logic on the import side too — `schema_version` visible in `export_info` lets the importer detect this.

## Revisit when

Strictness from an ethics board requires aggregate-only exports (see SDD §12 entry "Anonymous-aggregate-only export mode").
