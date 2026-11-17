# ADR-0023: Repository cover pages - a rule-agnostic hook, rules as researcher data, none shipped

**Status:** Accepted
**Date:** 2026-11-17
**Drivers:** #81 and #82 (title-page date and type), #20 (researcher page exclusion), [ADR-0003](0003-cli-first-class.md) rev. 2026-11-17 (the CLI's feature set is a superset of the GUI's), [ADR-0004](0004-module-contract.md) (module versions), [ADR-0013](0013-runner-orchestration.md) (planning: stale = version mismatch), QA-REPRO.

## Context

Some repositories prepend a generated cover page to a PDF on download. In the reference corpus, 2,093 of 2,283 ETH Research Collection files start with one (4 with two stacked covers); its type line and "Publication date" are the repository's metadata, not the thesis's statement (#20). The #81/#82 explorations therefore skipped every leading page carrying the ETH marker sentence before looking for the title page.

That rule names one repository. The owner decided against shipping it: we do not know what a professor's corpus contains, and a rule that explicitly removes ETH cover pages has no business in an app sent to a professor who is not at ETH. The research team, however, needs it - to analyse the reference corpus as the explorations did, and to add similar rules for other repositories found in downloaded theses later.

## Decision

**1. A rule-agnostic hook in core, empty by default.** `tta/core/modules/_titlepage.py` defines `CoverRule` (a page matches when it contains every `all_of` string and, if given, one `any_of` string, compared after the shared normalisation) and `CoverRuleset` (id, version, rules, `max_pages`). Both title-page modules take an optional ruleset; leading pages are skipped while they match, at most `max_pages`. **The default is `None`**: the module registry, the GUI and a plain `tta run` apply no cover rule, and no cover marker text exists anywhere in the `tta` package (a test asserts this).

**2. Rules are data, not shipped code.** Rulesets are TOML files under `research/cover_rules/` in the repository, outside the `tta` package: not in the wheel (`packages.find` includes only `tta*`), not in the PyInstaller spec (`datas` lists only package directories; a test asserts the spec mentions neither `research` nor `cover_rules`). The format is validated strictly by `tta/core/cover_rules.py` (unknown keys are errors, so a typo cannot silently disable a rule) and is easy to extend: a new `[[rules]]` table with an id, the marker text and an evidence note. The only ruleset today is `eth_research_collection.toml` (rule `eth-rc-download-cover`).

**3. Researcher opt-in through the CLI only.** `tta run --cover-rules FILE` applies one ruleset to that invocation. The GUI never offers it. This is not an exception to CLI/GUI parity: under [ADR-0003](0003-cli-first-class.md) rev. 2026-11-17 the CLI's feature set is a superset of the GUI's and may carry researcher options; this is one, decided here. The CLI reaches researchers from a source checkout, where `research/` exists.

**4. Runs with and without a ruleset are never mixed.** Planning already treats a version mismatch as stale (ADR-0013, `module_runs.module_version`). With a ruleset, both title-page modules report the version `<base>+covers.<id>.<hash>` (the hash is over the ruleset id, version, `max_pages` and rules; the file location is not part of it). Consequences:

- `tta run --cover-rules X` on a project analysed without it re-runs exactly the two title-page modules (reason `stale`), and a later plain `tta run` - or the GUI - re-runs them again without it. A project therefore never holds a mixture of the two kinds of result for the current versions.
- Editing a ruleset changes the hash and re-runs the affected theses.
- The version travels into exports with `module_runs`, so an imported result says whether a ruleset was applied.

Each run also records, in its local-only `diagnostics`, `cover_rules` (`null` on the default path, else id, version, fingerprint, rule ids and source file name) and `cover_pages` (`[{page, rule}]` per skipped page).

Rejected alternatives for the provenance: a `tta.toml` setting (the GUI would then read a researcher option, and a project-level switch could not be told apart from the run it produced); a separate metric (`theses` x metrics is the export surface, and a constant string per run is not a metric); diagnostics alone (planning does not read them, so the two kinds of result would mix silently).

**5. The default path still behaves sensibly on a cover page.** Without the ruleset a repository cover page is the first page, and therefore the title page for the date rules and own page 0 for the type rules. Two *generic* exclusions keep it from supplying evidence, without skipping it ([ADR-0022](0022-publication-date-rules.md), [ADR-0019](0019-thesis-type-by-detection.md) rev. 3, catalogue in [`titlepage-rules.md`](../titlepage-rules.md) section 1):

- the date label cue "Publication date";
- a **repository metadata page** - a page with at least two of the deposit labels `Publication date:`, `Permanent link:`, `Rights / license:` - contributes no date candidate and no type marker.

These name no repository and need no marker text; they are exclusions of evidence, not rules that skip a page. The page still counts for positions: the real title page becomes "title page + 1" for the date rules, and the type window ends one own page earlier.

## Measured effect (subset check, not a corpus run)

Owner instruction: no module run over the reference corpus; a comparison on at most 100 theses of the exploration's labelled samples. The subset (`exp-81-82/select_subset.py`, deterministic, seed 8182): all **26** theses labelled in both samples, **37** more from the #81 date sample stratified by repository x labelled precision, and **37** more from the #82 type sample - every doc of a rare or mixed class (13: MAS, Lizentiat, Semesterarbeit, two-type labels) plus 24 stratified by repository x labelled type. 100 theses: 63 with date labels, 63 with type labels; 25 of the date docs and 22 of the type docs start with an ETH cover page. These docs were part of the tuning sample, so the figures check the implementation against the exploration; they do not validate the rules (#50).

| | Exploration rule (reference) | With ETH ruleset | Default path (no cover rule) |
|---|---:|---:|---:|
| **Dates**, title-page answers right / dated (all 63) | 56 / 57 | 56 / 57 | 51 / 57 |
| precision when answering | 100 % | 100 % | 100 % |
| ETH files with a cover page (25, 22 dated) | 21 / 22 | 21 / 22 | 16 / 22 |
| HU (32, 31 dated) | 31 / 31 | 31 / 31 | 31 / 31 |
| **Types**, right / labelled (all 63) | 60 / 63 | 60 / 63 | 60 / 63 |
| ETH files with a cover page (22) | 21 / 22 | 21 / 22 | 21 / 22 |
| HU (30) | 30 / 30 | 30 / 30 | 30 / 30 |

(Types without the metadata-page exclusion: 50 / 63 overall, 11 / 22 on cover files - the cover's "Master Thesis" line won, echoing the repository's type. The previous module, 0.2.0: 31 / 63.)

With the ruleset the implementation reproduces the exploration rules exactly (63 of 63 identical answers for both modules). On the default path the types are unaffected. The dates lose 5 of 22 cover files: the date on the real title page, now "title page + 1", lacks a submission cue or a place prefix and is rejected by the after-title-page restriction; these files then fall back to the PDF creation year, which for ETH downloads is the download year. No wrong title-page date was produced.

A generic variant - "a repository metadata page does not count as the title page" - recovers all five (21 / 22, measured on the same subset) but is cover-page skipping in effect, so it is **not** shipped; the decision is the owner's (see "Revisit when").

## Relation to #20

#20 (researcher option: exclude pages from raw-text extraction) is a different layer: it would remove pages from `raw_text` itself and so change every metric. This hook only changes where the two title-page modules start reading. Nothing here blocks #20: the cover rules could become one source of page exclusions there, and its own provenance would follow the same version-suffix pattern.

## Consequences

- ✅ The shipped app contains no repository-specific rule; a professor's collection is read as it is.
- ✅ The research team applies the ETH rule (and future ones) to the reference corpus and can extend the ruleset by editing data.
- ✅ Results with and without a ruleset are distinguishable by version and diagnostics and are never mixed by the planner.
- ⚠️ Switching a project between the two re-runs the two title-page modules each time (cheap: they read the first pages of `raw_text`).
- ⚠️ On the default path, a repository cover page in front of the title page costs some title-page dates (5 of 22 cover files in the subset), which then fall back to the PDF year.

## Revisit when

- The owner decides whether the generic "repository metadata page is not the title page" variant may ship (it would bring the default path to the ruleset's date figures without naming a repository).
- Downloaded theses from other repositories show cover pages: add rules to `research/cover_rules/` with corpus evidence.
- #20 is implemented: decide whether cover rulesets feed its page exclusion.
