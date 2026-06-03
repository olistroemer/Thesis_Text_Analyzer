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
| GUI (Tk Text widget) | `markdown` lib → custom Tk renderer | clickable internal links | plain text (MVP) | resolved to bibliography panel |
| CLI (`pds help <topic>`) | `rich` library's Markdown renderer | "see also" trailing block | plain text | `[Flesch 1948]` inline |
| PDF | pandoc + `--citeproc` + xelatex | pandoc internal refs | LaTeX math | full citations |

## CI checks

```
1. Every module in the catalogue has core/help/modules/<name>.md
2. Every metric in core/privacy_metadata.py has core/help/metrics/<name>.md
3. Every cross-reference in any help file resolves to an existing slug
4. Every BibTeX key referenced exists in core/help/references.bib
5. Front-matter validates against the schema above
6. No raw HTML in any help file
7. No external (http://) image links
```

## Alternatives considered

- **One file per module containing both module and metric descriptions.** Less granular; cross-references become anchors which are renaming-fragile. Rejected.
- **Free-form markdown without front matter.** Loses the cross-ref / citation enforcement. Rejected.
- **reStructuredText / Sphinx for the help system.** Heavier tooling; loses the unified pandoc pipeline already chosen in ADR-0010. Rejected.

## Consequences

- ✅ Help is part of the codebase, version-controlled with its referenced code.
- ✅ Same files render to GUI, terminal, and PDF.
- ✅ External researchers contributing modules follow a template; the contribution surface is small and clear.
- ⚠️ Adding a module is now a two-step PR (code + help); CI enforces.
- ⚠️ Math in the GUI is plain text until a v2 with KaTeX or similar.

## Revisit when

- A non-English partner institution requires localised help content.
- Mathematical content becomes load-bearing enough in the GUI that plain-text math is insufficient.
