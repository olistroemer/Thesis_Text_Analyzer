# ADR-0003: CLI as first-class primary adapter

**Status:** Accepted (revision 2026-11-17 - the CLI's feature set is a superset of the GUI's)
**Date:** 2026-06-03 (rev. 2026-10-12, rev. 2026-11-17)
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
tta doctor      dump diagnostics for a support / bug report
```

`tta exclude <id>` mirrors the GUI Excluded checkbox (US-PROF-EXCLUDE, #11): it sets `theses.excluded=1` and, for an already-analysed thesis, **scrubs** the cached analysis (`Repository.purge_analysis`, [ADR-0006](0006-schema.md) rev. 5). Because the scrub is destructive and irreversible (source PDF untouched), it prompts for confirmation; `--yes` skips the prompt for scripts. `tta include <id>` clears the flag, making the thesis eligible again.

`tta remove <id>` is the harder version, for a PDF added by accident (#63, [ADR-0006](0006-schema.md) rev. 6): it deletes the analysis *and* the `theses` row, so the thesis is forgotten and the same file can be added again cleanly. It is not exclude with a bigger hammer - exclude keeps the row precisely so the identity is remembered, and remove exists because a mis-added thesis has no identity worth remembering. Nothing restores it (there is no row left to `include`), so it prompts for confirmation; `--yes` skips the prompt for scripts. Like `exclude`, an unknown id exits 65 and a filesystem failure during the artefact removal exits `EX_PARTIAL` with a warning rather than claiming a clean removal.

`tta doctor` (#42) bundles everything a bug report needs — app and module versions, Python and OS (including whether this is a frozen build, [ADR-0014](0014-distribution.md)), the project's applied `schema_version` and a SQLite `PRAGMA integrity_check`, the effective config, and named **checks** each `ok`/`warn`/`fail`. Two constraints follow from what it is for: it is strictly **read-only** (a diagnostic that repairs what it inspects hides the fault being reported, so it bypasses `Project.open`, creates nothing, and opens the DB read-only; a missing project is a `warn`, since a user filing a bug may have none yet), and its **offline self-check really blocks the network** — the three pieces that plausibly could reach out (NLTK `punkt_tab`, `langdetect`, `textstat`) are exercised with outbound sockets disabled, because asserting offline-ness in prose is not a check. Exit code is 1 if any check fails, so `tta doctor >/dev/null || echo broken` scripts; `--format json` is the machine contract. Implementation detail with teeth: those three libraries cost ~0.6 s to import, so `doctor` defers them into the probes — no other command may pay for them.

**Revision (2026-10-12): the CLI reaches its users from source, not as a release binary.** Its users are the research team and technically versed power users, who check out the repository and run `pip install -e .` anyway; professors use the GUI. Releases therefore ship only `tta-gui` per target ([ADR-0014](0014-distribution.md)). The CLI is still frozen on every CI run, because the frozen CLI is the vehicle of the packaged-binary acceptance check (run -> list -> export on every target), but that binary is a test artefact and is not uploaded. "Peer of the GUI" now describes the feature surface, not the download. One consequence: `tta doctor` is not in a professor's hands as a frozen tool, so a professor's bug report goes through the research team, who run it from source.

**Revision (2026-11-17): the CLI's feature set is a superset of the GUI's.** "Peer of the GUI" (and the SDD's former "equal in capability to the GUI") is sharpened into a rule with a direction:

- **Everything the GUI can do, the CLI can do.** A GUI feature without a CLI path is a defect, not a design choice, unless decided as below.
- **The CLI may additionally offer researcher and developer options** that a professor never needs and that the GUI therefore does not show. The first is the researcher cover-page ruleset of `tta run --cover-rules` ([ADR-0023](0023-researcher-cover-rulesets.md), #81/#82): it changes what the title-page modules read, is applied to the reference corpus by the research team, and has no meaning for a professor's own collection.
- **Any other divergence is a deliberate, recorded decision.** A GUI-only feature, or a new CLI-only option, is weighed on its own and recorded in an ADR (a new one or a revision of the ADR that owns the feature) - it must not just happen because one adapter was extended and the other was not.

This fits the revision above: the CLI reaches researchers from source, the GUI reaches professors as the release binary, so the extra surface lives exactly where its users are. CLI-only options must keep results distinguishable from the GUI's default behaviour wherever they change what a module computes (for the cover rules: the module version and `diagnostics` record the ruleset, ADR-0023), so data produced by the two adapters is never silently mixed.

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
- ⚠️ The CLI is not a release download (revision 2026-10-12): using it requires a source checkout and a Python install.

## Revisit when

If the GUI grows features the CLI cannot easily mirror (e.g., interactive comparison views). Under the superset rule (revision 2026-11-17) such a feature is a recorded exception, decided in an ADR; the CLI itself remains in scope.
