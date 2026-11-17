# Researcher rulesets

Data files for the ruleset hook of the title-page modules
(`mod_classify_thesis_type`, `mod_determine_publication_year`), decided in
[ADR-0023](../../docs/adr/0023-researcher-cover-rulesets.md). They hold every
rule that is derived from one repository's or institution's layout.

- **Not part of the app.** Nothing here is in the `tta` package or in a release
  binary, and the GUI never applies a ruleset. The shipped default is *no*
  repository rule at all: a professor's collection is read unmodified.
- **Researcher opt-in.** `tta run --cover-rules FILE` (from a source checkout)
  applies one ruleset to that run. (The option keeps its first name; a ruleset
  now does more than skip cover pages.)
- **Never silently mixed.** The ruleset id and a hash of its rules are appended
  to the two module versions (`0.3.0+covers.<id>.<hash>`) and recorded in each
  run's `diagnostics` (`cover_rules`, `cover_pages`, `not_evidence_pages`, and
  `ruleset:<rule id>` as the reason on every rejected date or excluded marker).
  A later run without the option (or with another ruleset) sees those runs as
  stale and re-runs them.

## Rule kinds

| Table | Effect | Match |
|---|---|---|
| `[[covers]]` | leading pages are skipped before the title page is located (at most `max_pages`) | `all_of` strings all present, `min_any` of `any_of` present (after case/accent/whitespace folding) |
| `[[not_evidence_pages]]` | the page is kept but supplies no date and no type marker | as above |
| `[[date_cues]]` | extra negative cue before a date (same line, or a ":" label line above) | `pattern`, regex, case-insensitive, raw text |
| `[[type_passages]]` | type markers inside the match (+ `tail` characters) do not count | `pattern`, regex on the normalised window (lower case, no accents, "ss") |

The full format is in `tta/core/cover_rules.py`; unknown keys are an error.

## Adding a rule

Add a table of the right kind to an existing file (or a new file for another
repository), with a unique `id`, the text or pattern, and an `evidence` note:
which corpus, how many files, an example file id - never personal data. Bump
the file's `version`.

| file | source of the rules | rules |
|---|---|---|
| `eth_research_collection.toml` | ETH Zurich Research Collection; ETH declaration of originality | download cover page, its metadata block, its "Publication date" label, the declaration's list of paper types |
