# ADR-0003: CLI as first-class primary adapter

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-RES-CLI, QA-TEST.

## Decision

Ship a polished CLI as a peer of the GUI. Subcommand layout (Click or Typer):

```
pds run         run analyses on inputs
pds list        list known theses + status
pds module      list / show module details
pds export      produce researcher export
pds import      import a researcher export
pds db          init / migrate / vacuum
pds help        render help topics
pds privacy     render GDPR statement
pds version     version + module versions
```

## Output rules

- Default to a pretty human-readable table on stdout.
- `--format {human, json, csv}` toggles machine-readable output. JSON is the contract for any scripting; human output may change between versions.
- Logs / progress go to stderr (Unix convention) so `pds run … | jq …` stays clean.
- Exit codes follow `sysexits.h`: 0 success, 1 partial (some theses failed), 64 misuse, 65 data error, 70 internal error.

## Context

The researcher persona iterates on modules and runs analyses headlessly. A CLI is not an afterthought to the GUI; both adapters need to be first-class from MVP. ADR-0002 makes this clean architecturally.

## Alternatives considered

- **CLI as a deferred post-MVP feature.** Would have forced module developers to use the GUI to test modules — slow iteration. Rejected.
- **CLI as a minimal `python -m pds.runner` script.** Adequate for the researcher loop but unfriendly to non-team users who want to integrate the tool into scripts. Rejected.

## Consequences

- ✅ Researcher iteration loop is fast and scriptable.
- ✅ Integration tests run via the CLI on fixture inputs; no GUI process needed.
- ✅ CI checks can `pds run` on test fixtures and diff output.
- ⚠️ CLI design (subcommands, flags, output formats) needs its own maintenance.
- ⚠️ Two adapters means double the UI surface to keep in sync; accepted cost.

## Revisit when

If the GUI grows features the CLI cannot easily mirror (e.g., interactive comparison views). The asymmetry should be documented but the CLI itself remains in scope.
