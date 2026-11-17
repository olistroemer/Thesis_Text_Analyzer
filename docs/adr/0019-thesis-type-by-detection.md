# ADR-0019: Thesis type by detection — no add-time dialog, override columns dropped

**Status:** Accepted (revision 3 - corpus-grounded markers over the first five pages, classes `magister`, `mas`, `licentiate`, `semester`, `doctoral` added, #82; revision 2 - `diploma` added as a third detected type, #67)
**Date:** 2026-07-22 (rev. 2: 2026-08-26, rev. 3: 2026-11-17)
**Drivers:** US-PROF-ATTRS (group analyses by bachelor/master), US-PROF-COMPARE (bachelor-vs-master side-by-side), US-RES-LOW-FRICTION (five-step contribute loop, no friction on add), ADR-0004 (modules only ever write metrics), ADR-0006 rev. 4 (lazy hashing / instant add), ADR-0011 (module catalogue). Resolves #9. (ADR-0018 is the ASCII-source policy — this is the next free number.)

## Context

US-PROF-ATTRS asked for a bachelor/master attribute on each thesis "when adding them", which the MVP implemented as an add-time **Type mini-dialog** (Bachelor / Master / Unspecified) plus two override columns on `theses` — `type` and `language_hint`. This collides with US-RES-LOW-FRICTION: every dialog on the add path is a step, and a professor batch-adding a folder of PDFs should not be asked to classify each set by hand. In practice `language_hint` was never wired (no CLI flag, no GUI input — language already lives as the detected `language_code` metric), and `type` defaulted to `unspecified` for anyone who dismissed the dialog.

## Decision

**Thesis type is detected, not entered.** A new module `mod_classify_thesis_type` (mirroring `mod_classify_language`) consumes `raw_text` and produces a single `thesis_type` metric ∈ {`bachelor`, `master`, `diploma`, `unspecified`} via a lightweight, case-insensitive, accent/umlaut-tolerant **title-page keyword heuristic** (German: "Bachelorarbeit", "Masterarbeit", "Masterthesis", "Bachelorthesis", "Diplomarbeit", "Diplom-Ingenieur", …; English: "Bachelor's thesis", "Master's thesis", "Diploma thesis", "B.Sc.", "M.Sc.", "Master of Science", …) — not ML. With three named classes the decision is **the marker that appears earliest** in the title-page window (rev. 2: the original pairwise `<` comparison did not generalise). Detection evidence goes in the run's `notes` (local-only); there is **no** separate confidence metric (the `thesis_type` metric alone, consistent with the single-metric style). Garbled or sparse `raw_text` yields `unspecified` — a valid answer, not `na`.

Consequently:

- **The add-time Type mini-dialog is removed.** Adding files → done, no prompt (US-RES-LOW-FRICTION; ADR-0006 rev. 4 instant add).
- **The override columns `theses.type` and `theses.language_hint` are dropped** (pre-release: migration `0001_initial.sql` is edited directly). Type now lives as a metric; language already did.
- **`tta run --type` is removed** — type is detected, not set.
- **Grid and Report group by the detected `thesis_type` metric** instead of `theses.type`. The grid's "Type" lead column reads the metric; the Report's length-by-type box plots and by-type counts read it too.
- The shared **title-page parser** (`core/modules/_titlepage.py`) that this module uses is also consumed by the publication-year module (#17), so both title-page heuristics stay consistent.

## Rev. 2: `diploma` as a third type (#67)

German theses awarded before the Bologna switch name neither "Bachelor" nor "Master": their title page says
*Diplomarbeit*. Those fell to the `unspecified` sentinel — an honest "don't know" that is nevertheless plainly
wrong when the page states the degree. The value set therefore becomes **{`bachelor`, `master`, `diploma`,
`unspecified`}**, and the pairwise tie-break is replaced by an earliest-marker-wins rule over all three classes.

**Keyword scope is deliberately narrow.** The diploma set is `diplomarbeit`, `diplom-arbeit`, `diplomthesis`,
`diploma thesis`, `diplom-ingenieur` (in the normalised form of `_titlepage.normalise`, which case-folds and
folds accents but does **not** strip hyphens, so hyphenated variants are spelled out). Bare **`diplom`** and
**`dipl.`** are **excluded**: German title pages carry supervisor and examiner titles ("Betreuer: Dipl.-Inform.
X", "Prof. Dr.-Ing. Dipl.-Ing. Y") inside the very same leading window the parser scans, so either short form
would mis-classify a Bachelor- or Masterarbeit as a Diplomarbeit. This is the same false-positive reasoning
already applied to bare `"ma"` / `"msc"`.

`diplom-ingenieur` is kept despite the same family of risk, because the spelled-out degree ("zur Erlangung des
akademischen Grades Diplom-Ingenieur") is a strong genuine signal and the abbreviated supervisor form that
actually appears on title pages is `Dipl.-Ing.`, which does not contain it. The residual risk is a supervisor
credited with the unabbreviated title; accepted, and revisitable with the labeled-set validation below.

## Rev. 3: markers grounded in the reference corpus, eight classes (#82)

The #82 exploration (cached `raw_text` of the 3,262-file reference corpus, 268 hand-labelled documents) found the rev. 2 classifier right for only 57 % of the sample (73 % weighted to the corpus). Three causes: on 92 % of ETH files the first page is the repository's download cover, whose type line is the repository's metadata (equal to it in 2,063 of 2,093 files); the HU series reprints state the type in an imprint on page 3-4, outside a one-page window; and the abbreviations in the keyword set (`m.sc`, `b.sc`, ...) are author and supervisor titles. The repository's own type is wrong for about 1 thesis in 7 (the ETH "master" set holds 274 Diplomarbeiten, 24 MAS papers, 4 Lizentiatsarbeiten; the HU "master" set 63 Diplomarbeiten and 52 Magisterarbeiten), so it cannot replace detection either.

**Decision ("type markers v1"; catalogue with corpus evidence per marker: [`titlepage-rules.md`](../titlepage-rules.md) section 3):**

- **Window:** the document's own pages 0-4 (99 % of first true markers), normalised as before plus letter-spaced words collapsed.
- **Markers are spelled-out type/degree phrases only** (Bachelorarbeit, Master's Thesis, "for the degree of Master", Diplomarbeit, Diplom-Ingenieur, Magisterarbeit, Lizentiatsarbeit, Master of Advanced Studies, Nachdiplomarbeit, Semesterarbeit, Studienarbeit, ...). **Never markers:** abbreviations (B.Sc., M.Sc., M.A., Dipl.-X, Dr. sc., Dr. rer./phil., PhD, lic. phil.), bare "Dissertation", "Masterstudiengang", bare "Diplom", bare "Master..." - rev. 2's `m.sc`/`b.sc`/`m.eng`/`b.eng` keywords are dropped. Marker choice is what matters: the broad catalogue with abbreviations gives 93 % on the sample, the strong markers 98 %.
- **The earliest valid marker wins** (251 of 253 labelled documents with a marker). **MAS override:** a "Master of Advanced Studies / MAS-Programm" marker on the same page as a winning master marker gives `mas`. "Nachdiplomarbeit" is not "Diplomarbeit".
- **One exclusion:** the ETH declaration of originality, which lists every paper type. A possessive exclusion ("his doctoral thesis") was tested and changed nothing; it is not adopted.
- **Tier 2:** a bare "Bachelor/Master of <field>" counts only when no tier-1 marker is in the window (net positive in the corpus: ~7 right, 1-3 wrong - the author's previous degree).
- **Repository pages:** markers on a *repository metadata page* (at least two of the generic labels `Publication date:`, `Permanent link:`, `Rights / license:`) do not count; the page is not skipped. No repository-specific rule ships; researchers can load cover-page rules through the CLI ([ADR-0023](0023-researcher-cover-rulesets.md)).
- **Evidence** goes to `diagnostics`: the deciding rule, the winning marker (class, marker id, own page, tier) and every marker hit with its exclusion reason.

**Class set.** {`bachelor`, `master`, `diploma`, `magister`, `mas`, `licentiate`, `semester`, `doctoral`, `unspecified`} (`tta.core.types.THESIS_TYPES`):

| Class | Corpus docs | Why |
|---|---:|---|
| `magister` | 53 | unambiguous markers, precision 1.0 |
| `mas` | 24 | Master of Advanced Studies / Nachdiplom: continuing education, not the consecutive master |
| `licentiate` | 4 | Lizentiatsarbeit, precision 1.0 |
| `semester` | 5 | Semester-/Studienarbeit, Focus Work; reliable as the earliest marker only |
| `doctoral` | 0 | **no corpus evidence** - added because professors supervise doctorates (and ETH has a doctoral collection whose PDFs were never downloaded). Its markers are degree phrases only and produce 0 hits in the corpus, so they cost nothing there |

Baccalaureate is **not** added (topic mentions only). "Not a thesis" is not a class: type markers cannot detect it.

**Reference statistics vs reporting.** Only `bachelor` and `master` enter reference-corpus statistics (`tta.core.types.REFERENCE_THESIS_TYPES`, for #49); the research question is about them and the other classes are too rare to carry a baseline. Every class is **reported** to the user - grid, report (by-type counts, length-by-type) - under a translated label (`THESIS_TYPE_LABELS`), so a professor sees each thesis identified as what it is. The raw value stays the identity in the DB, the export and the CLI.

**Results.** Exploration: 98.1 % on the sample (98.9 % weighted), tuned on that sample. Subset check of the implementation (63 type-labelled documents, see ADR-0023): identical to the exploration rule on 63 of 63; 60 of 63 right on the default path.

## US-PROF-ATTRS ↔ US-RES-LOW-FRICTION resolution

Both stories are honoured: the professor still gets a bachelor/master grouping (US-PROF-ATTRS, US-PROF-COMPARE) — it is simply **computed** rather than entered, so the contribute loop keeps its five friction-free steps (US-RES-LOW-FRICTION). Correcting a mis-detected value is deferred to **editable metrics (#10)**: correction becomes a uniform property of *metrics* rather than a per-column override on `theses`, which is cleaner and gives one correction mechanism for every detected value. `theses.excluded` is unaffected — it is a genuine control field that must be set *before* a run (QA-PRIV), and stays a column (its toggle is #11).

## Interim gap (accepted)

Between this ADR (#9) and editable metrics (#10) there is **no in-app way to correct** a mis-detected or `unspecified` type. This is accepted for the interim: detection is right on the common case (the degree is named on the title page), and `unspecified` is an honest answer rather than a wrong guess.

## Alternatives considered

- **Keep the dialog, make it optional/skippable.** Still a step on the add path, still a column that drifts from reality. Rejected.
- **Detect *and* keep the override column** (metric as default, column as manual override). Two sources of truth for one fact, and reintroduces the per-column correction mechanism that #10 replaces uniformly. Rejected.
- **Add a `thesis_type_confidence` metric** à la `language_confidence`. The heuristic is keyword-presence, not a probabilistic classifier; a confidence number would be spurious precision. Evidence lives in `notes` instead. Rejected.

## Consequences

- ✅ The add path has zero dialogs; batch-adding a folder is instant (with ADR-0006 rev. 4).
- ✅ One correction mechanism for all detected values once #10 lands (editable metrics).
- ✅ `theses` shrinks to genuinely user-owned/control fields; modules keep to the "metrics only" rule (ADR-0004).
- ⚠️ No in-app correction until #10 (see interim gap).
- ✅ Pre-Bologna German theses get their actual degree instead of `unspecified` (rev. 2, #67).
- ⚠️ Detection quality rests on the title page naming the degree; a validation pass (F1 / confusion matrix) against the labeled exploration-harvest dataset is a deferred follow-up (the dataset is not part of this repo).
- ✅ Rev. 3: the type the document states, not the repository's metadata, for the ~1 thesis in 7 where they differ; Magister, MAS, Lizentiat and semester papers no longer pass as master (#82).
- ⚠️ Rev. 3: the `doctoral` markers have no corpus evidence; their precision is unknown until doctoral theses are analysed.

## Revisit when

- Editable metrics (#10) land — the interim correction gap closes.
- The labeled-set validation shows the heuristic needs more keywords/languages or an ML classifier — including whether `diplom-ingenieur` produces supervisor-title false positives in practice (#50 measures F1 / the confusion matrix over the value set as it now stands).
- Doctoral theses enter a corpus: measure the `doctoral` markers.
- Single-document marker forms seen in the exploration ("lavoro di diploma", "Assessorarbeit", "Master Project", "Thesis elective") gain more evidence.
