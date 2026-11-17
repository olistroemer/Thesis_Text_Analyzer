# ADR-0023: Repository-specific rules - a rule-agnostic hook, rules as researcher data, none shipped

**Status:** Accepted
**Date:** 2026-11-17
**Drivers:** #81 and #82 (title-page date and type), #20 (researcher page exclusion), [ADR-0003](0003-cli-first-class.md) rev. 2026-11-17 (the CLI's feature set is a superset of the GUI's), [ADR-0004](0004-module-contract.md) (module versions), [ADR-0013](0013-runner-orchestration.md) (planning: stale = version mismatch), QA-REPRO.

## Context

The #81/#82 explorations found text in the reference corpus that is not the thesis's own statement but an artefact of where the PDF came from:

- **Cover pages.** The ETH Research Collection prepends a generated cover page on download: 2,093 of 2,283 ETH files start with one, 4 with two stacked covers (#20). Its type line and its "Publication date" are the repository's metadata, not the thesis's statement.
- **Metadata blocks.** That cover carries the labels `Publication date:`, `Permanent link:`, `Rights / license:`.
- **Forms.** The ETH declaration of originality, bound into many ETH theses, lists every paper type ("... a component of every semester paper, Bachelor's thesis, Master's thesis and any other degree paper ...").

The explorations skipped the cover, ignored the label, and excluded the declaration list. All of these rules are derived from one repository's or one institution's layout.

**Owner decisions:**

- **No such rule ships.** We do not know what a professor's corpus contains, and rules that exclude ETH's pages and forms have no business in an app sent to a professor who is not at ETH. Without researcher opt-in, every thesis is processed unmodified.
- **The research team keeps them.** It needs them to analyse the reference corpus as the explorations did, and to add similar rules for other repositories found in downloaded theses later.

## Decision

**1. A rule-agnostic hook in core, empty by default.** `tta/core/modules/_titlepage.py` defines a `CoverRuleset` with four kinds of rule. On the default path (`None`) none applies:

| Kind | Effect | Matching |
|---|---|---|
| `covers` | leading pages are **skipped** before the title page is located: from the first page on while a page matches, at most `max_pages` (default 3) | page rule: every `all_of` string and at least `min_any` (default 1) of `any_of`, after the shared normalisation |
| `not_evidence_pages` | the page is **kept** (it still counts for the title-page position and the windows) but supplies no date candidate and no type marker | page rule, as above |
| `date_cues` | an extra **negative date cue**, checked like the built-in cues (same line before the date, or a label line ending in ":" directly above) | regular expression, case-insensitive, on the raw page text |
| `type_passages` | type markers inside a match (and up to `tail` characters after it) **do not count** | regular expression on the normalised type window |

The module registry, the GUI and a plain `tta run` pass `None`. No rule text of any of these kinds exists under `tta/` - sources, help pages or catalogues; a test asserts this for every moved phrase (`generated automatically upon download`, `research collection`, `publication date:`, `permanent link`, `rights / license`, `component of every`, `bestandteil jeder`), and a second test asserts that no built-in date cue matches "Publication date:".

**2. Rules are data, not shipped code.** Rulesets are TOML files under `research/cover_rules/` in the repository, outside the `tta` package: not in the wheel (`packages.find` includes only `tta*`), not in the PyInstaller spec (a test asserts the spec mentions neither `research` nor `cover_rules`). `tta/core/cover_rules.py` validates them strictly: unknown keys are errors, so a typo cannot silently disable a rule; patterns must compile; rule ids are unique across kinds. Adding a rule means adding one table with an id, its text or pattern and an `evidence` note.

The one ruleset today, `eth_research_collection.toml` (version 2), holds:

| Kind | Rule id | Content |
|---|---|---|
| `covers` | `eth-rc-download-cover` | "This page was generated automatically upon download from the ETH Zurich Research Collection" |
| `not_evidence_pages` | `eth-rc-metadata-block` | at least 2 of `Publication date:`, `Permanent link:`, `Rights / license:` (for a cover page the cover rule did not skip, e.g. a third stacked cover) |
| `date_cues` | `eth-rc-publication-date-label` | `publication date` |
| `type_passages` | `eth-declaration-of-originality` | `(?:component of every\|bestandteil jeder).{0,160}?(?:degree paper\|abschlussarbeit\|arbeit)`, tail 40 |

The option keeps its first name, `--cover-rules`, although a ruleset now does more than skip cover pages; a rename buys nothing functional.

**3. Researcher opt-in through the CLI only.** `tta run --cover-rules FILE` applies one ruleset to that invocation. The GUI never offers it. This is not an exception to CLI/GUI parity: under [ADR-0003](0003-cli-first-class.md) rev. 2026-11-17 the CLI's feature set is a superset of the GUI's and may carry researcher options; this is one, decided here. The CLI reaches researchers from a source checkout, where `research/` exists.

**4. Runs with and without a ruleset are never mixed.** Planning already treats a version mismatch as stale (ADR-0013, `module_runs.module_version`). With a ruleset, both title-page modules report the version `<base>+covers.<id>.<hash>`; the hash covers the ruleset id and version, `max_pages` and every rule of all four kinds, but not the file location. For example, `mod_determine_publication_year` reports `0.2.0+covers.eth-research-collection.49402e14` and `mod_classify_thesis_type` reports `0.3.0+covers.eth-research-collection.49402e14`, against `0.2.0` / `0.3.0` without a ruleset. Consequences:

- **Switching the option re-plans.** `tta run --cover-rules X` on a project analysed without it re-runs exactly the two title-page modules (reason `stale`). A later plain `tta run`, or the GUI, re-runs them again without it. A project therefore never holds a mixture of the two kinds of result for the current versions.
- **Editing a ruleset re-plans.** A changed rule changes the hash, so the affected theses are re-run.
- **Exports carry the choice.** The version travels into exports with `module_runs`, so an imported result says whether a ruleset was applied.

Each run also records in its local-only `diagnostics`:

- `cover_rules`: `null` on the default path, else id, version, fingerprint, rule ids and source file name;
- `cover_pages` and `not_evidence_pages`: `[{page, rule}]`;
- the rejection or exclusion reason `ruleset:<rule id>` on every candidate or marker a ruleset ruled out.

**Rejected alternatives for the provenance:**

- a `tta.toml` setting: the GUI would then read a researcher option, and a project-level switch could not be told apart from the run it produced;
- a separate metric: the metrics are the export surface, and a constant string per run is not a metric;
- diagnostics alone: planning does not read them, so the two kinds of result would mix silently.

**5. What remains on the default path.** Only generic detection rules that are tied to no repository or institution: the date forms, linguistic cues and positional restrictions of [ADR-0022](0022-publication-date-rules.md), and the spelled-out markers and precedence of [ADR-0019](0019-thesis-type-by-detection.md) rev. 3. The full list is in [`titlepage-rules.md`](../titlepage-rules.md) section 5.

## Measured effect (subset check, not a corpus run)

**Scope (owner instruction):** no module run over the reference corpus; a comparison on at most 100 theses of the exploration's labelled samples.

**Subset** (`exp-81-82/select_subset.py`, deterministic, seed 8182):

- all **26** theses labelled in both samples;
- **37** more from the #81 date sample, stratified by repository × labelled precision;
- **37** more from the #82 type sample: every doc of a rare or mixed class (13: MAS, Lizentiat, Semesterarbeit, two-type labels) plus 24 stratified by repository × labelled type.

That is 100 theses: 63 with date labels and 63 with type labels. 25 of the date docs and 22 of the type docs start with an ETH cover page. These docs were part of the tuning sample, so the figures check the implementation against the exploration; they do not validate the rules (#50).

| | Exploration rule (reference) | With ETH ruleset | Default (no ruleset) |
|---|---:|---:|---:|
| **Dates**, year right from the text / dated (all 63) | 56 / 57 | 56 / 57 | 57 / 57 |
| ETH files with a cover page (25, 22 dated) | 21 / 22 | 21 / 22 | 22 / 22 - **all 25 answered from the cover's "Publication date"** |
| precision level = the label's (cover files, 22 dated) | | 21 / 22 | 4 / 22 |
| undated theses given a year from the text (6) | 0 | 0 | 3 (the cover's deposit year) |
| HU (32, 31 dated) | 31 / 31 | 31 / 31 | 31 / 31 |
| **Types**, right / labelled (all 63) | 60 / 63 | 60 / 63 | 50 / 63 |
| ETH files with a cover page (22) | 21 / 22 | 21 / 22 | 11 / 22 |
| HU (30) | 30 / 30 | 30 / 30 | 30 / 30 |

(The previous type module, 0.2.0: 31 / 63.)

**With the ruleset**, the implementation reproduces the exploration rules exactly: 63 of 63 identical answers for both modules.

**On the default path**, a repository cover page is read like any other page. It is the first page with text, so it becomes the title page:

- **Dates:** its labelled deposit date ("Publication date: \| 2015") carries the generic submission cue `date:` and wins on every cover file. At year level that coincides with the thesis year on all 22 dated cover files of this subset; ETH's deposit year agreed with the thesis year in 104 of 106 sample theses in the exploration. The result is nevertheless the *repository's* date:
  - its precision is usually `year` (precision level right in 4 of 22, against 21 of 22 with the ruleset);
  - its source says `title_page`;
  - it also dates 3 theses that state no date at all.
- **Types:** the cover's type line ("Master Thesis") is the earliest marker and wins, echoing the repository's type (11 / 22 on cover files). That is wrong for Diplom-, MAS-, Lizentiat- and semester papers in ETH's "master" set; corpus-wide the exploration estimates ~15 % of ETH files.
- **HU** files and ETH files without a cover page are unaffected.

## Relation to #20

#20 (researcher option: exclude pages from raw-text extraction) works on a different layer: it would remove pages from `raw_text` itself and so change every metric. This hook only changes what the two title-page modules read as evidence. Nothing here blocks #20: the page rules could become one source of page exclusions there, and its own provenance would follow the same version-suffix pattern.

## Consequences

- ✅ The shipped app contains no repository- or institution-specific rule; a professor's collection is read unmodified.
- ✅ The research team applies the ETH rules, and future ones, to the reference corpus and extends them by editing data.
- ✅ Results with and without a ruleset are distinguishable by version and diagnostics, and the planner never mixes them.
- ⚠️ On the default path, a repository cover page in front of the title page supplies the date and the type: the repository's deposit year (often right at year level, but at the wrong precision, and for undated theses too) and the repository's type (wrong where the repository's type is wrong).
- ⚠️ Switching a project between the two modes re-runs the two title-page modules each time. That is cheap: they read only the first pages of `raw_text`.

## Revisit when

- **Professors' corpora show download covers in front of their theses:** decide whether some *generic* handling belongs on the default path. Today the line is drawn at "nothing tied to a repository or institution".
- **Downloaded theses from other repositories show cover pages, metadata blocks or forms:** add rules to `research/cover_rules/`, with corpus evidence.
- **#20 is implemented:** decide whether researcher rulesets feed its page exclusion.
