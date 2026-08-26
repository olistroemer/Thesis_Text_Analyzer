# ADR-0003: CLI as first-class primary adapter

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-RES-CLI, QA-TEST.

## Decision

Ship a polished CLI as a peer of the GUI. Subcommand layout (Click or Typer):

```
tta run         run analyses on inputs
tta list        list known theses + status
tta module      list / show module details
tta exclude     exclude a thesis (scrub its cached analysis; --yes skips the prompt)
tta include     re-include a previously excluded thesis
tta export      produce researcher export
tta import      import a researcher export
tta db          init / migrate / vacuum
tta help        render help topics
tta privacy     render GDPR statement
tta version     version + module versions
tta doctor      dump diagnostics for a support / bug report
```

`tta exclude <id>` mirrors the GUI Excluded checkbox (US-PROF-EXCLUDE, #11): it sets `theses.excluded=1` and, for an already-analysed thesis, **scrubs** the cached analysis (`Repository.purge_analysis`, [ADR-0006](0006-schema.md) rev. 5). Because the scrub is destructive and irreversible (source PDF untouched), it prompts for confirmation; `--yes` skips the prompt for scripts. `tta include <id>` clears the flag, making the thesis eligible again.

`tta doctor` (#42) bundles everything a bug report needs — app and module versions, Python and OS (including whether this is a frozen build, [ADR-0014](0014-distribution.md)), the project's applied `schema_version` and a SQLite `PRAGMA integrity_check`, the effective config, and named **checks** each `ok`/`warn`/`fail`. Two constraints follow from what it is for: it is strictly **read-only** (a diagnostic that repairs what it inspects hides the fault being reported, so it bypasses `Project.open`, creates nothing, and opens the DB read-only; a missing project is a `warn`, since a user filing a bug may have none yet), and its **offline self-check really blocks the network** — the three pieces that plausibly could reach out (NLTK `punkt_tab`, `langdetect`, `textstat`) are exercised with outbound sockets disabled, because asserting offline-ness in prose is not a check. Exit code is 1 if any check fails, so `tta doctor >/dev/null || echo broken` scripts; `--format json` is the machine contract. Implementation detail with teeth: those three libraries cost ~0.6 s to import, so `doctor` defers them into the probes — no other command may pay for them.

## Output rules

- Default to a pretty human-readable table on stdout.
- `--format {human, json, csv}` toggles machine-readable output. JSON is the contract for any scripting; human output may change between versions.
- Logs / progress go to stderr (Unix convention) so `tta run … | jq …` stays clean.
- Exit codes follow `sysexits.h`: 0 success, 1 partial (some theses failed), 64 misuse, 65 data error, 70 internal error.
- `Ctrl-C` during `tta run` installs a SIGINT handler that calls `Runner.cancel()` (skip-pending, ADR-0013): no new theses are submitted, in-flight ones finish, then the command exits with the partial code (1).

## Context

The researcher persona iterates on modules and runs analyses headlessly. A CLI is not an afterthought to the GUI; both adapters need to be first-class from MVP. ADR-0002 makes this clean architecturally.

## Alternatives considered

- **CLI as a deferred post-MVP feature.** Would have forced module developers to use the GUI to test modules — slow iteration. Rejected.
- **CLI as a minimal `python -m tta.runner` script.** Adequate for the researcher loop but unfriendly to non-team users who want to integrate the tool into scripts. Rejected.

## Consequences

- ✅ Researcher iteration loop is fast and scriptable.
- ✅ Integration tests run via the CLI on fixture inputs; no GUI process needed.
- ✅ CI checks can `tta run` on test fixtures and diff output.
- ⚠️ CLI design (subcommands, flags, output formats) needs its own maintenance.
- ⚠️ Two adapters means double the UI surface to keep in sync; accepted cost.

## Revisit when

If the GUI grows features the CLI cannot easily mirror (e.g., interactive comparison views). The asymmetry should be documented but the CLI itself remains in scope.
