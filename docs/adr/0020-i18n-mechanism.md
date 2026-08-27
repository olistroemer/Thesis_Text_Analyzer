# ADR-0020: i18n mechanism — stdlib gettext, committed catalogs, no external tools

**Status:** Accepted
**Date:** 2026-08-27
**Drivers:** [SDD §9.6](../SDD.md#96-i18n-posture) (German-first MVP), #29 (gettext foundation), #16 (human-friendly metric labels), #28 (`de` catalog), [ADR-0018](0018-ascii-source.md) (ASCII-only Python source), [ADR-0011](0011-mvp-module-catalogue.md) (lean declared dependency set), [ADR-0014](0014-distribution.md) (frozen single-file binaries), QA-RES, QA-REPRO, QA-PRIV.

SDD §9.6 already fixes the **posture** — German default, English msgids, English still selectable, locale-aware date/number formatting, no RTL. It says nothing about the **mechanism**. This ADR is the mechanism.

## Decision

### 1. stdlib `gettext`. No new dependency.

Translation goes through Python's `gettext` module. `babel` is rejected: §9.6 names gettext, the dependency set is deliberately lean ([ADR-0011](0011-mvp-module-catalogue.md) library-choice policy), and #53 has just removed matplotlib specifically to shrink the frozen binary. Adding a locale-data package to gain `babel.dates`/`babel.numbers` would buy two formatting helpers for several MB of CLDR data, in a product that ships exactly two locales.

The two locale-aware helpers §9.6 requires are therefore hand-written in `core/i18n.py`: a decimal-comma number formatter and a date formatter. They are per-locale table lookups, not a CLDR implementation, and are honest about that.

### 2. Catalogs at `tta/locale/<lang>/LC_MESSAGES/tta.po` **plus the compiled `tta.mo`** — both committed.

`gettext` reads the compiled binary catalog at run time, so the `.mo` must exist wherever the application runs. Generating it at install time is not an option: there is no build step for a from-source run, `msgfmt` is not guaranteed present on a Windows developer machine, and a missing `.mo` fails **silently** — `gettext` falls back to the msgid, so a German-first application would quietly come up in English. Committing the `.mo` makes the German UI a property of the checkout.

The obvious objection to a binary in git is drift: a `.po` edit with no recompile ships a stale catalog. That is answered mechanically rather than by discipline — `tests/core/test_i18n_catalogs.py` recompiles every `.po` into a temp dir and **byte-compares** against the committed `.mo`, and regenerates the `.pot` from source and compares that too. Both generators are deterministic (see 3), so the comparison is exact, not fuzzy.

There is **no `en` catalog**. English *is* the msgid set: under `en` the loader installs a `NullTranslations` and `_()` returns its argument. "English is selectable" therefore costs zero bytes and cannot drift from the source.

### 3. No external tools. Two deterministic scripts under `packaging/`.

`xgettext` and `msgfmt` are part of GNU gettext, which is not installed on a stock Windows or macOS machine and is not a Python dependency we can declare. Both directions are therefore implemented in-repo:

| Script | Does | How |
|---|---|---|
| `packaging/extract_messages.py` | `tta/**/*.py` → `tta/locale/tta.pot` | `ast` walk for `_("literal")` and `N_("literal")` calls |
| `packaging/compile_catalogs.py` | `tta/locale/*/LC_MESSAGES/tta.po` → `tta.mo` | pure-Python GNU MO writer |
| `packaging/pocatalog.py` | shared PO/POT parse + write, MO write | — |

Neither is imported as `packaging.<name>`: the repo's `packaging/` directory is not a Python package and the name collides with the third-party `packaging` distribution. Tests load them by path, exactly as `tests/packaging/conftest.py` already does for `check_build.py`.

Both are deterministic by construction — entries are emitted in sorted msgid order, source references sorted, and no timestamp is written into the `.pot` header. That is what makes "regenerate and byte-compare" a usable CI gate.

An `ast`-based extractor is also stricter than `xgettext -L Python` in the one way that matters here: it sees only real calls to `_`/`N_` with a single string-literal argument, so a runtime-computed msgid cannot silently enter the catalog and then fail to translate.

### 4. Locale resolution: `[ui] locale` in `tta.toml` → `TTA_LOCALE` → default `de`. **Not** the OS locale.

```
tta.toml   [ui] locale = "en"      per project, persisted, the user's own setting
env        TTA_LOCALE=en           per invocation; scripts, CI, tests
default    "de"                    no configuration anywhere
```

Unknown values fall back to the default rather than raising: a hand-edited `tta.toml` must not make the application unstartable.

**The OS locale is deliberately not consulted.** This is the interesting half of the decision. `locale.getdefaultlocale()` would look like the helpful thing to do, and it is what most applications do, but it is wrong for this product:

- German-first is a **product decision** (§9.6), not an inference about the user. The professor persona is at a German institution and gets a German UI because that is what the tool is for.
- German institutional IT very commonly ships **English-locale Windows**. Deriving the UI language from the OS would hand exactly the target user an English UI, unpredictably, on a machine-by-machine basis — and the person affected has no idea why their colleague's copy speaks German.
- It makes the UI language a property of the machine rather than of the project, which breaks QA-REPRO for anything that renders text: two people opening the same project folder would generate differently-worded reports and privacy statements.
- A deterministic default is testable. "Whatever this CI runner's `LANG` says" is not.

The escape hatch stays cheap and explicit: one line in `tta.toml`, or one environment variable.

### 5. One `_()` for both adapters, resolved through `tta/core/i18n.py`.

`core/i18n.py` owns `install()`, `_()`, `N_()`, `active_locale()` and the formatting helpers. The CLI, the Tk GUI, the HTML report and the GDPR statement all import the same `_`.

This does not violate [ADR-0002](0002-ui-core-boundary.md). `gettext` is stdlib text lookup, not a UI toolkit; core already renders user-facing text (`core/report.py` produces the whole HTML document, `core/privacy_metadata.py` the whole statement), and it must render it in the active locale. Putting `_()` in an adapter would mean core could not translate its own output — or would need two copies of the translation state.

`install()` deliberately does **not** call `gettext.install()`: that injects `_` into `builtins`, which makes the dependency invisible and collides with the interactive interpreter's `_`. Every module imports `_` explicitly.

### 6. Where strings are marked, and where they are not

`_()` at the point of *display*. `N_()` — a no-op that only marks a literal for extraction — wherever the English text must stay the stored/persisted value:

| Marked with `N_()` at definition, `_()` at display | Why |
|---|---|
| `module_runs.reason` (module `NotApplicable` / `Applicability` reasons) | The reason is **persisted and exported** (`privacy_metadata`: `module_runs.reason`, `exported=True`). A German msgid in the database would corrupt the research data set and make cross-institution exports incomparable. English is stored; `grid_model.cell_details` translates on the way to the screen. |
| `privacy_metadata` field/module/artefact `purpose` prose | Same registry feeds `render_report_json()`, which is a machine-readable artefact. JSON stays English; the rendered Markdown statement is translated. |
| Module-level UI constants (`columns.COLUMN_HELP`, `COLUMN_LABELS`, `grid_model.*_DETAIL`, `help_view.SECTION_LABELS`, …) | Evaluated at import time, before any locale is resolved. Marking at definition and translating at use makes the locale switchable at run time. |

Explicitly **not** marked: log messages, docstrings, exception text aimed at developers, metric names, module names, artefact kinds, DB values, status tokens (`ok`/`na`/`error`), SQL, and anything else persisted or exported. A msgid that reaches the database or an export corrupts the data model.

### 7. Metric labels (#16)

Grid headers, the details panel and the help-viewer tree show a friendly label — "Readability (Flesch)", not `flesch_reading_ease` — resolved through `_()` so the German label is a catalog entry like any other string.

The interim source is `COLUMN_LABELS` in `tta/ui/tk/columns.py`, alongside the `COLUMN_HELP` dict that #66 deliberately kept when it removed the grid tooltips. Per [ADR-0012](0012-help-content.md) the **durable** source is each help page's front-matter `title:`; the shipped corpus already carries German titles (`publication_year` → *Veröffentlichungsjahr*), and the `de` catalog's labels are worded to match them. Migrating `COLUMN_LABELS` to the front matter is deferred to #2, which authors the full corpus — 45 columns against 8 existing pages is not a migration yet.

The raw metric name stays discoverable in the details panel, which names it on its own line under the label.

## Translation workflow

```
# 1. mark new strings in the source with _() / N_()
# 2. regenerate the template
python packaging/extract_messages.py
# 3. merge new msgids into each catalog (adds missing, keeps existing translations,
#    comments out msgids the source no longer has)
python packaging/extract_messages.py --update
# 4. translate the empty msgstr entries in tta/locale/de/LC_MESSAGES/tta.po
# 5. recompile
python packaging/compile_catalogs.py
# 6. the gates
PYTHONPATH=$PWD python -m pytest tests/core/test_i18n_catalogs.py -q
```

Steps 2, 3 and 5 are idempotent and their output is byte-stable, so re-running them on an unchanged tree leaves the working tree clean — which is what lets CI run them and diff.

Rules for translators, both enforced by tests:

- **Every msgid in `de` has a non-empty `msgstr`.** A partial German catalog is a UI that mixes languages sentence by sentence; better to fail the build.
- **Placeholders must survive.** `{path}`, `{count}`, `%s` and friends are named/positional format arguments; the test checks that the set of `{...}` fields in a `msgstr` matches its `msgid`.

Non-ASCII belongs **only** in `.po`/`.mo`. Those are data files, explicitly out of scope for ADR-0018 ("User-facing text is expected to later flow through gettext catalogs (#29). Those catalogs are *data*, not source"). A German string in a `*.py` file is a bug the ASCII gate catches.

## Alternatives considered

- **`babel` + `.po` compiled by `pybabel`.** Real CLDR formatting, standard extractor, plural rules for free. Rejected on the dependency budget (see 1) — and its extractor still needs the same "regenerate and compare" gate to be trustworthy, so it buys tooling, not correctness.
- **Compile `.mo` at install/build time, commit only `.po`.** No binary in git. Rejected: silent English fallback on any machine without `msgfmt`, and there is no install step at all for a `git clone` + `pip install -e .` developer run. The drift risk it avoids is cheaper to solve with a byte-compare test than the failure mode it creates.
- **Skip `.mo` entirely, parse `.po` at run time.** Removes the binary and the compile step. Rejected: a hand-rolled `.po` runtime parser is *more* code than the MO writer, it is on the startup path, and it abandons `gettext`'s own well-tested loader for a bespoke one.
- **A plain Python dict of translations instead of gettext.** Tempting for two locales. Rejected: §9.6 commits to gettext, and it throws away the whole tooling ecosystem the moment a third language appears — which is precisely the "first non-English partner institution" trigger in [§12](../SDD.md#12-out-of-mvp-scope).
- **Derive the locale from the OS.** Rejected, at length, in 4.
- **German msgids with English translations.** Would put umlauts in every `*.py` file, i.e. delete ADR-0018. Rejected outright. English msgids also keep the source readable for a contributor who does not speak German.
- **`gettext.install()` into builtins.** One line, `_` available everywhere. Rejected: invisible dependency, and it shadows the REPL's `_`.

## Consequences

- ✅ German-first works from a bare checkout, with no build step and no external tool.
- ✅ Zero new runtime dependencies; the frozen binary grows by the size of one `.mo` (single-digit KB).
- ✅ The catalog cannot silently drift from the source: the `.pot` and every `.mo` are regenerated and byte-compared by the test suite.
- ✅ ADR-0018 is untouched — every translated character lives in a data file.
- ✅ English stays available for free, and is what the test suite runs under (`TTA_LOCALE=en` is set in `tests/conftest.py`), so assertions keep quoting the msgid.
- ⚠️ **No plural forms.** `ngettext` is not wired up, so there is no `1 Arbeit` / `3 Arbeiten` distinction; German strings are worded to read correctly for any count. German and English share the same plural rule (`n != 1`), so this buys little, and supporting it would mean plural parsing in the `.po` reader, `\0`-joined msgstrs in the MO writer, and `Plural-Forms` handling — for eight call sites. Revisit with the first locale whose plural rule differs (Polish, Russian, Arabic).
- ⚠️ **Click's `--help` text resolves at import time.** `@click.option(help=_("..."))` runs when `tta.cli.main` is imported, before `-C/--project` has been parsed and the project's `tta.toml` read. So option help honours `TTA_LOCALE` and the `de` default, but **not** a per-project `[ui] locale`. Command *descriptions* are docstrings and are not translated at all — translating them would mean duplicating every docstring into a `help=` argument. `tta --help` before a project exists has no config to read anyway.
- ⚠️ Two module `NotApplicable` reasons interpolate a value (`unsupported language: {lang}`, `no readability formula for language: {lang}`). What is persisted is the formatted English string, so the display-time `_()` lookup misses and they render in English inside an otherwise German details panel. Fixing it means either persisting a structured reason (a schema change) or a template registry keyed on prefix (fragile). Left as a known gap; see the report on the #29/#28 lane.
- ⚠️ `core/doctor.py` translates only the **actionable** check details ("run `tta db init` first"). Version strings, paths, and `repr`-ed exceptions stay English: they are bug-report material, they are read by whoever receives the report, and `tta doctor --format json` is a scripting contract.
- ⚠️ German runs ~30 % longer than English. Layouts are `pack()`/`grid()`-based (§9.6) and the GUI tests exercise the real window under `de`, but a fixed `width=` or `wraplength=` added later can still clip a German string; that is a review item, not something a test can assert in general.

## Revisit when

- A third UI language appears (§12's "first non-English partner institution"). The mechanism scales as-is; that is the point where `babel`'s dependency cost may finally be justified by real CLDR formatting needs.
- A locale with a non-Germanic plural rule appears — then wire up `ngettext` (see the plural-forms consequence).
- #2 authors the full help corpus, at which point `COLUMN_LABELS` should collapse into the front-matter `title:` fields per ADR-0012.
- RTL is requested. Out of MVP scope (§9.6, §12); layouts are already `pack()`/`grid()`, so the pass is mechanical.
