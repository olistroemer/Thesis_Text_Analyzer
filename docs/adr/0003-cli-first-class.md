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

`tta doctor` (#42) is the support command: one bundle of everything a bug report needs, so a user never has to be walked through collecting it. It reports the app and module versions, Python and OS/platform (including whether this is a frozen build, [ADR-0014](0014-distribution.md)), the resolved project path with its applied `schema_version` and a SQLite `PRAGMA integrity_check`, the effective configuration, and a set of named **checks** with an `ok`/`warn`/`fail` status each.

Two design constraints follow from what the command is for:

- **It must be read-only.** A diagnostic that repairs what it inspects hides the fault being reported, so `doctor` does not go through `Project.open` (which migrates), never creates a project, and opens the database read-only. A missing project is a `warn`, not a failure - a user filing a bug may have no project yet.
- **The offline self-check actually blocks the network.** QA-PRIV promises the app never reaches out, and the three third-party pieces that plausibly could (NLTK `punkt_tab`, `langdetect`, `textstat`) are probed with outbound sockets disabled for the duration. Asserting offline-ness in prose is not a check; attempting the work with the network unplugged is.

Exit code is 0 when every check passes or warns and **1** when any check fails - the partial code, so `tta doctor >/dev/null || echo broken` works in a script. `--format json` emits the whole bundle as the scripting contract.

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
- ✅ `tta doctor` makes a bug report one command instead of a checklist (#42).
- ⚠️ CLI design (subcommands, flags, output formats) needs its own maintenance.
- ⚠️ Two adapters means double the UI surface to keep in sync; accepted cost.

## Revisit when

If the GUI grows features the CLI cannot easily mirror (e.g., interactive comparison views). The asymmetry should be documented but the CLI itself remains in scope.
