# Researcher cover-page rulesets

Data files for the cover-page hook of the title-page modules
(`mod_classify_thesis_type`, `mod_determine_publication_year`), decided in
[ADR-0023](../../docs/adr/0023-researcher-cover-rulesets.md).

- **Not part of the app.** Nothing here is in the `tta` package or in a release
  binary, and the GUI never applies a cover rule. The shipped default is *no*
  cover rules: a professor's collection is read as it is.
- **Researcher opt-in.** `tta run --cover-rules FILE` (from a source checkout)
  applies one ruleset to that run. Leading pages that match a rule are skipped
  before the title page is located.
- **Never silently mixed.** The ruleset id and a hash of its rules are appended
  to the two module versions (`0.3.0+covers.<id>.<hash>`) and recorded in each
  run's `diagnostics` (`cover_rules`, `cover_pages`). A later run without the
  option (or with another ruleset) sees those runs as stale and re-runs them.

## Adding a rule

Add a `[[rules]]` table to an existing file (or a new file for another
repository), with a unique `id`, the marker text in `all_of` (every string must
occur on the page) and/or `any_of` (one must occur), and an `evidence` note:
which corpus, how many files, an example file id - never personal data. Bump
the file's `version`. Matching is substring matching after case, accent and
whitespace folding, so copy the marker text as printed on the page.

| file | repository | rules |
|---|---|---|
| `eth_research_collection.toml` | ETH Zurich Research Collection | download cover page |
