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
tta remove      remove a thesis from the project entirely (--yes skips the prompt)
tta export      produce researcher export (--profiling dumps per-run durations)
tta import      import a researcher export
tta db          init / migrate / vacuum
tta help        render help topics
tta privacy     render GDPR statement
tta version     version + module versions
```

`tta exclude <id>` mirrors the GUI Excluded checkbox (US-PROF-EXCLUDE, #11): it sets `theses.excluded=1` and, for an already-analysed thesis, **scrubs** the cached analysis (`Repository.purge_analysis`, [ADR-0006](0006-schema.md) rev. 5). Because the scrub is destructive and irreversible (source PDF untouched), it prompts for confirmation; `--yes` skips the prompt for scripts. `tta include <id>` clears the flag, making the thesis eligible again.

`tta remove <id>` is the harder version, for a PDF added by accident (#63, [ADR-0006](0006-schema.md) rev. 6): it deletes the analysis *and* the `theses` row, so the thesis is forgotten and the same file can be added again cleanly. It is not exclude with a bigger hammer - exclude keeps the row precisely so the identity is remembered, and remove exists because a mis-added thesis has no identity worth remembering. Nothing restores it (there is no row left to `include`), so it prompts for confirmation; `--yes` skips the prompt for scripts. Like `exclude`, an unknown id exits 65 and a filesystem failure during the artefact removal exits `EX_PARTIAL` with a warning rather than claiming a clean removal.

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
