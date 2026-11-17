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
| `kind` | yes | `metric` \| `module` \| `concept` \| `guide` (rev. 6) |
| `produced_by` | metric only | the producing module |
| `consumes`, `produces_artefacts`, `produces_metrics` | module only | mirror the `ModuleSpec` |
| `applicability` | yes (modules + metrics) | short prose |
| `references` | optional | list of BibTeX keys |
| `see_also` | optional | list of `kind:slug` URIs |

## Render targets

| Target | Renderer | Cross-refs | Math | Citations |
|---|---|---|---|---|
| GUI (Tk Text widget) | built-in markdown-**subset** renderer in `ui/tk/help_view.py`, no extra dependency (rev. 2) | clickable internal links | plain text (MVP) | `[@key]` inline (MVP); bibliography panel deferred |
| CLI (`tta help <topic>`) | `rich` library's Markdown renderer, over the page **body** only (rev. 5) | "see also" trailing block | plain text | `[Flesch 1948]` inline |
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
`.md` files directly rather than through `ui/tk/help_view.py`, so a content
gate in `core` never depends on the Tk adapter. Since rev. 5 it parses their
front matter with the one core parser, in its strict mode.

**Rev. 3 (2026-08-27, #2) corrects two check paths that named the wrong file:**

- **Check 2** said `core/privacy_metadata.py`. That registry enumerates schema
  columns, modules and artefact kinds -- it holds **no metric names at all**
  (its metric row is the single `metric_values.value_num`/`value_text` pair).
  The single source of truth for the metric catalogue is
  `ModuleSpec.produces_metrics` over `core.modules.registry.default_registry()`,
  which is what the gate reads. 13 modules, 32 metrics (31 until `publication_date_precision`, #81).
- **Check 4** said `core/help/references.bib`. The bibliography already exists
  as **`docs/references.bib`**, cited by the SDD, `docs/model-limitations.md`
  and `docs/dependencies.md`, and that file is authoritative. A second copy
  under `core/help/` would duplicate keys with no consumer to justify it: the
  only render target that resolves `[@key]` is the pandoc PDF pipeline, which
  runs over the repository, and rev. 2 defers citation rendering in the GUI and
  CLI to their `[@key]` source form. `pyproject.toml` also declares the
  packaged corpus as `help/**/*.md`, so a `.bib` placed there would not ship
  anyway. Repository-time bibliography, repository-time gate.

**Rev. 4 (2026-10-12, #36): one in-app link target.** Besides the three
page schemes, a body link may target `app:third_party_licenses`, which the GUI
viewer resolves to the *Third-party licences* window (SDD §9.2) instead of a
page. It is not a slug, so check 3 does not apply to it; instead the gate
fails on any `app:` target other than that one, so a typo cannot render as
an inert link. Other render targets show the link label as text. No front
matter field may carry it (`see_also` stays pages only).

**Rev. 5 (2026-10-12, #78): one front-matter parser, in core.** Front
matter is **parsed, never rendered**, on every render target. The single
implementation is `split_front_matter(text) -> (metadata, body)` in
**`tta/core/help_corpus.py`**. Every consumer uses it: the GUI viewer
(`ui/tk/help_view.py`), the CLI (`tta help`, `tta module show`) and the
corpus gate. No adapter and no test carries a parser of its own. Before this
the tree had two parsers (the viewer's and the gate's) and the CLI had none,
so `tta help` printed every page's front matter as its first paragraph.

- **Why core.** Both adapters need it, and the CLI may not import `tta.ui`
  ([ADR-002](0002-ui-core-boundary.md), SDD §5.2), so the viewer's parser was
  out of its reach. Reading the corpus is not a UI concern.
- **Why next to `core/help/`, not inside it.** `core/help/` is packaged
  *content*: `pyproject.toml` ships `help/**/*.md`, and the PyInstaller spec
  copies the directory as data. A Python module in there would turn the corpus
  into a package and ship a second time, as data. The module also owns the
  corpus layout both adapters share (the three sections, the packaged root).
- **What it parses.** This ADR's flat schema, with no YAML dependency (the
  project has none). It reads `key: value` lines: a scalar stays a string, and
  a value in brackets (`[a, b]`) becomes a list of its stripped items. It skips
  blank lines and `#` comment lines. Only a `---` block that opens on the
  file's **first** line counts; a later `---` (a thematic break) is body. CRLF
  line endings are accepted. A page without front matter yields `({}, text)`.
- **Lenient by default, strict for the gate.** By default, the parser skips a
  line the flat schema cannot express: an indented or `- item` line of nested
  YAML, or a line without a colon. A contributed page written in fuller YAML
  therefore still loads in both viewers. The gate calls the same function with
  `strict=True`, which raises on such a line, so the shipped corpus stays flat.
- **CLI rendering.** `tta help <topic>` renders the body only. The `title`
  becomes the heading when the body does not open with its own `#` heading
  (the GUI's rule; every shipped page has one). `see_also` becomes a trailing
  *See also* block that lists each target's title and the slug `tta help`
  accepts.
- **`tta module show <name>`** prints the module page's `title` and the
  body's first paragraph instead of the module's Python docstring. The
  docstring is English and names internals (*catalogue #7 (SDD Sec. 7.1)*). It
  stays only as the fallback for a module without a page, which means a
  contributed one: the gate guarantees a page for every registered module. The
  page is the module's user-facing description, so it is the single source of
  that description on every surface.

**The scope of checks 5-7 is `modules/`, `metrics/`, `concepts/`.**
`core/help/privacy/` holds the legal stubs of
[ADR-009](0009-privacy-as-code.md) Sec. 6-7, one pair per locale
(`privacy/de/`, `privacy/en/`; ADR-009 rev. 2026-10-12): they are fragments
appended to a generated statement, not help pages, they carry no front matter,
they do carry an HTML status comment, and the viewer's topic tree deliberately
excludes them.

**Rev. 6 (2026-11-17, #92): guide pages - a cover page and the generated
privacy page.** The GUI viewer gains two topics above the three sections, under
a fourth URI scheme, `guide:` (SDD §9.4.1):

- **`guide:cover`**, an authored page with front matter (`kind: guide`; the
  schema's required fields are `slug`, `title`, `kind`, nothing else, and
  `references`/`see_also` stay optional). Unlike the rest of the corpus it is
  **per locale**: `core/help/guide/<locale>/<slug>.md`, `de` and `en`, German
  as the fallback - the layout of `privacy/<locale>/`, because it is the first
  thing a professor reads and must follow the UI language. Its titles are
  therefore per-locale too, which is what rev. 3's label problem lacked; that
  problem stays open for the metric pages. Checks 3 and 5-7 apply to guide
  pages in **every** locale; the corpus size check and the label/title gate
  stay about `modules/`, `metrics/`, `concepts/`.
- **`guide:privacy`**, the ADR-009 statement, **generated at view time** from
  `render_statement_md()` and never stored as a file. It is a valid link
  target - check 3 accepts it as the one generated guide slug - but it is not a
  page of the gate's page set: it has no front matter, and its content is the
  privacy registry's to gate (`tests/core/test_privacy.py`).

The CLI target is unchanged: `tta help` lists and renders the three sections
only, and the statement keeps `tta privacy report`.

The GUI renderer's table fallback changes with it: a GFM table renders as one
item per body row (`first cell - header: cell; ...`), inline-rendered and
word-wrapped, instead of fixed-pitch source lines. The privacy statement's
tables have cells past a hundred characters, and as source lines they showed
the professor `|` markers and a horizontal scrollbar; the corpus's own small
tables gain clickable links from the same change. The **authoring** subset is
unchanged.

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
