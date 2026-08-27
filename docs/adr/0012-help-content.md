# ADR-0012: Help-content authoring — markdown with front matter, three categories, cross-refs as URI scheme

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-PROF-EXPLAIN (help pages with cross-refs), ADR-0010 (markdown source + pandoc pipeline), QA-TEST (CI-enforceable coverage), external-researcher modules contributing help content.

## Decision

Help content lives under `core/help/`, split into three directories: `modules/`, `metrics/`, `concepts/`. Files are markdown with required YAML front matter; markdown subset is CommonMark + GFM tables + pandoc footnotes + pandoc math. Cross-references use a URI scheme (`metric:`, `module:`, `concept:`) resolved at render time. Citations live in `references.bib` in BibTeX format, referenced inline via `[@key]`.

## Front-matter schema

| Field | Required | Notes |
|---|---|---|
| `slug` | yes | matches filename |
| `title` | yes | rendered as h1 |
| `kind` | yes | `metric` \| `module` \| `concept` |
| `produced_by` | metric only | the producing module |
| `consumes`, `produces_artefacts`, `produces_metrics` | module only | mirror the `ModuleSpec` |
| `applicability` | yes (modules + metrics) | short prose |
| `references` | optional | list of BibTeX keys |
| `see_also` | optional | list of `kind:slug` URIs |

## Render targets

| Target | Renderer | Cross-refs | Math | Citations |
|---|---|---|---|---|
| GUI (Tk Text widget) | built-in markdown-**subset** renderer in `ui/tk/help_view.py`, no extra dependency (rev. 2) | clickable internal links | plain text (MVP) | `[@key]` inline (MVP); bibliography panel deferred |
| CLI (`tta help <topic>`) | `rich` library's Markdown renderer | "see also" trailing block | plain text | `[Flesch 1948]` inline |
| PDF | pandoc + `--citeproc` + xelatex | pandoc internal refs | LaTeX math | full citations |

## CI checks

```
1. Every module in the catalogue has core/help/modules/<name>.md
2. Every metric in the catalogue has core/help/metrics/<name>.md
3. Every cross-reference in any help file resolves to an existing slug
4. Every BibTeX key referenced exists in docs/references.bib
5. Front-matter validates against the schema above
6. No raw HTML in any help file
7. No external (http://) image links
```

Implemented as `tests/core/test_help_corpus.py` (#2), mirroring
`tests/core/test_privacy.py`: the test module *is* the gate. It reads the
`.md` files directly with its own front-matter parser rather than through
`ui/tk/help_view.py`, so a content gate in `core` never depends on the Tk
adapter.

**Rev. 3 (2026-08-27, #2) corrects two check paths that named the wrong file:**

- **Check 2** said `core/privacy_metadata.py`. That registry enumerates schema
  columns, modules and artefact kinds -- it holds **no metric names at all**
  (its metric row is the single `metric_values.value_num`/`value_text` pair).
  The single source of truth for the metric catalogue is
  `ModuleSpec.produces_metrics` over `core.modules.registry.default_registry()`,
  which is what the gate reads. 13 modules, 31 metrics.
- **Check 4** said `core/help/references.bib`. The bibliography already exists
  as **`docs/references.bib`**, cited by the SDD, `docs/model-limitations.md`
  and `docs/dependencies.md`, and that file is authoritative. A second copy
  under `core/help/` would duplicate keys with no consumer to justify it: the
  only render target that resolves `[@key]` is the pandoc PDF pipeline, which
  runs over the repository, and rev. 2 defers citation rendering in the GUI and
  CLI to their `[@key]` source form. `pyproject.toml` also declares the
  packaged corpus as `help/**/*.md`, so a `.bib` placed there would not ship
  anyway. Repository-time bibliography, repository-time gate.

**The scope of checks 5-7 is `modules/`, `metrics/`, `concepts/`.**
`core/help/privacy/` holds the two reviewed legal stubs of
[ADR-009](0009-privacy-as-code.md) Sec. 6-7: they are fragments appended to a
generated statement, not help pages, they carry no front matter, they do carry
an HTML review comment, and the viewer's topic tree deliberately excludes them.

## Alternatives considered

- **One file per module containing both module and metric descriptions.** Less granular; cross-references become anchors which are renaming-fragile. Rejected.
- **Free-form markdown without front matter.** Loses the cross-ref / citation enforcement. Rejected.
- **reStructuredText / Sphinx for the help system.** Heavier tooling; loses the unified pandoc pipeline already chosen in ADR-0010. Rejected.

## Consequences

- ✅ Help is part of the codebase, version-controlled with its referenced code.
- ✅ Same files render to GUI, terminal, and PDF.
- ✅ External researchers contributing modules follow a template; the contribution surface is small and clear.
- ⚠️ Adding a module is now a two-step PR (code + help); CI enforces.
- ⚠️ **Rev. 2 (2026-08-26, #72):** the GUI target renders a documented markdown *subset* (SDD [§9.4.1](../SDD.md#941-gui-help-viewer)) instead of the full CommonMark + GFM surface: tables, footnotes and math fall back to their plain source lines, and `references.bib` citations stay as `[@key]`. Reason: pulling the `markdown` library into the frozen single-file bundle for a handful of read-only pages is not defensible against QA-RES, and a Tk renderer has to be hand-written either way. The **authoring** rules in this ADR (front matter, subset, cross-ref URIs, BibTeX) are unchanged — only the GUI renderer's implementation and its citation fidelity are.
- ⚠️ Math in the GUI is plain text until a v2 with KaTeX or similar.
- ⚠️ **The front-matter `title:` does not replace `COLUMN_LABELS`** (#2, #79, against
  this ADR's original intent). The MVP corpus is authored German-only
  ([SDD §9.6](../SDD.md#96-i18n-posture)), so a page carries exactly one title and it is
  German -- while the gettext catalogue holds *both* the English msgid and the German
  translation for every column. Migrating the labels into the front matter would hand
  the English UI German headers: a broken locale traded for a removed duplicate. **The
  catalogue is canonical**; the page title is a second copy of the German string, and
  `tests/core/test_help_corpus.py` asserts the two agree so they cannot drift. Revisit
  if a second-language corpus or per-locale title fields arrive.

## Revisit when

- A language beyond the MVP's **German-only** help corpus is needed (e.g. an English or third-language corpus). The MVP help is authored German-first per SDD §9.6; ADR-0012's authoring conventions are language-agnostic and unchanged.
- Mathematical content becomes load-bearing enough in the GUI that plain-text math is insufficient — or GFM tables / citation rendering in the GUI become load-bearing enough to justify a real markdown dependency, reverting rev. 2's subset renderer.
