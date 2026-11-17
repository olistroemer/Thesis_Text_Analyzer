# Title-page rules: date rules and type markers

The versioned rule catalogue of the two title-page modules (SDD [§7.4](SDD.md#74-notes-on-specific-modules)):

- **Date rules v1** - `mod_determine_publication_year` 0.2.0 (#81, [ADR-0022](adr/0022-publication-date-rules.md)).
- **Type markers v1** - `mod_classify_thesis_type` 0.3.0 (#82, [ADR-0019](adr/0019-thesis-type-by-detection.md) rev. 3).
- **Cover-page hook** - shared by both, no rules by default; researcher rulesets live outside the package ([ADR-0023](adr/0023-researcher-cover-rulesets.md)).

Every rule below comes from the October 2026 exploration of the reference corpus (cached `raw_text` of 3,262 ETH Research Collection and HU edoc files; 212 hand-labelled theses for dates, 268 for types). A rule without corpus evidence says so and gives its reason. Corpus examples name the file (repository handle) and a short snippet; personal names are replaced by `<name>`, and lines are separated by `|`.

**Change policy.** The catalogue and the code change together. Any change to a pattern, an exclusion, a window or a preference bumps the rules version here *and* the module version, so earlier runs are re-planned as stale (QA-REPRO). The labelled exploration samples were also used to tune the rules; their accuracy is therefore optimistic. Validation on a separate holdout is #50.

---

## 1. Shared page model (`_titlepage`)

| Term | Definition |
|---|---|
| page | `raw_text` split at form feeds (`mod_extract_pymupdf` writes one per page); the first 16 pages are read |
| cover page | a leading page matched by a rule of a researcher cover ruleset (ADR-0023). **None by default**: the shipped app never skips a page |
| own pages | the pages after the cover pages (all pages by default) |
| title page | the first own page with at least **30 non-space characters** (blank and near-blank leading pages exist, e.g. `18452_14941`, whose date is on page 5 but only 381 characters in) |
| repository metadata page | a page carrying at least **two** of the generic deposit labels `Publication date:`, `Permanent link:`, `Rights / license:` (after normalisation). Evidence on it is ignored by both modules; the page is **not** skipped and still counts for positions and windows |
| normalisation (types) | case-fold, `ß` -> `ss`, apostrophes dropped, accents/umlauts stripped (NFKD), whitespace collapsed; letter-spaced words of at least five letters are joined ("M A S T E R T H E S I S" -> "masterthesis") |

The repository-metadata-page check is generic: it names no repository and needs no cover marker text. In the reference corpus it fires on the ETH Research Collection cover page (both layouts, 2,093 files), whose type line equals the repository's metadata in 2,093 of 2,093 files and whose `Publication date:` is the deposit date.

---

## 2. Date rules v1

### 2.1 Window and order

1. **Window:** the title page and the 3 pages after it. The true date first appears on the title page in 77 % of the 201 dated sample theses and within the window in 97.5 % (+4 pages: 99 %). The late cases are HU series reprints whose imprint sits on page 3-4 (e.g. `18452_18990`).
2. **Pages in order.** The first page with a valid candidate decides.
3. **Within that page:** a candidate with a submission cue wins; otherwise the most precise one (day = month > semester > year/year range), the earliest on a tie.

### 2.2 Matched forms

Counts are title-page candidates in the corpus that pass the exclusions (exploration `corpus_forms.csv`). "Precision" is the value stored in `publication_date_precision`.

| Form id | Pattern (idea) | Precision | Count | Corpus example |
|---|---|---|---:|---|
| `month_d_y` | Month D, YYYY (also "Month Dth, YYYY", "August, 22, 2006") | day | ~930 | `18452_14670`: "for the degree of \| Master of Arts \| Berlin, March 24, 2005" |
| `d_month_y` | D. Monat YYYY / D Month YYYY / Dth (of) Month, YYYY; weekday prefixes | day | ~500 | `18452_14663`: "eingereicht: 30. März 1998"; `18452_14679`: "eingereicht am 6th February 2005" |
| `num_dmy` | DD.MM.YYYY (spaces allowed) | day | 240 | `18452_14643`: "vorgelegt von \| <name> \| Berlin, 29.3.1995" |
| `num_dmy_slash` | M/D/YYYY or D/M/YYYY (US order when the 2nd number > 12) | day | 14 | `20.500.11850_150636`: "<name> \| 8/15/2008" |
| `iso_ymd` | YYYY-MM-DD | day | 9 | `20.500.11850_149014`: "Project Period: Monday, 2003-05-26 - Friday, 2003-09-2.." |
| `ymd_slash` | YYYY/MM/DD | day | 2 | `20.500.11850_150367`: "Master Thesis \| 2007/10/01 - 2008/03/31" |
| `num_dmy_dash` | DD-MM-YYYY | day | 2 | `20.500.11850_150652`: "Master Thesis \| 02-01-2008 - 08-01-2008" |
| `month_y` | Month YYYY (also "Month, YYYY", abbreviations "Mar", "Sept.") | month | ~700 | `18452_14751`: "Berlin, im August 2007"; `20.500.11850_154287`: "Zurich, Mar 2013" |
| `iso_ym` | YYYY-MM | month | 5 | `20.500.11850_149298`: "Swiss Federal Institute of Technology Zurich (ETH) \| 2006-03" |
| `num_my` | MM/YYYY, MM.YYYY | month | 1 | `20.500.11850_21668`: "Date: 08/2009 Version: 0.5" |
| `semester` | Sommersemester/Wintersemester/Herbstsemester/Frühjahrssemester/Frühlingssemester YYYY(/YY); SS, WS, SoSe, WiSe, HS, FS YYYY(/YY) | semester | 56 + 42 | `18452_14655`: "Wintersemester 1997/98"; `20.500.11850_154583`: "Master Thesis HS 2013"; `18452_21329`: "Einreichung: WS 2013/14" |
| `semester2` | SS/WS/... YY/YY (two-digit years) | semester | 12 | `20.500.11850_146076`: "Diplomarbeit WS 97/98" |
| `season` | Spring/Summer/Fall/Autumn/Winter/Frühjahr/Frühling/Sommer/Herbst (Term/Semester) YYYY | semester | 127 | `18452_20641`: "Semester: Sommer 2018" |
| `acad` | YYYY/YY or YYYY/YYYY (academic year; the end year counts) | year_range | 8 | `18452_26789`: "... im Schuljahr 2020/2021" |
| `year` | YYYY, restricted (2.4) | year | 71 | `18452_14718`: "<name> and <name> \| 2006" |

**Month names:** German, English and Italian, full and abbreviated, with the OCR/LaTeX variants "März", "Maerz", "Marz", "M¨arz", "Mär", "Mrz", "Jänner". Italian has corpus evidence in 4 files (`20.500.11850_146860`: "Co-referente: <name> \| Agosto 2001").

**Years:** 1900 to 2039 are matched; candidates above the run year + 1 are rejected as implausible.

**Not matched (no title-page evidence):** French month names (only in reference lists; "mars" would also hit the planet), Italian semester names (1 file: "Semestre estivo 2006"), and two-digit-year dates such as "27.6.11" (8 title-page occurrences; not part of the evaluated rule set, so left out of v1).

### 2.3 Exclusions

A **negative cue** is looked for on the same line before the candidate (up to 40 characters), or - when nothing precedes the candidate on its own line - on a label line ending in ":" directly above. Negative cues **never cross further lines**: otherwise "geboren am 30. Dezember 1981 in Leipzig" knocks out the real "9th February 2009" on the next line (`18452_14748`), and a surname "Born" knocks out "Zurich, April 11, 2023" (`20.500.11850_607154`).

| Cue (reason id) | Words (case-insensitive) | Corpus | Example |
|---|---|---:|---|
| birth (`birth`) | geboren, geb., Geburtsdatum, Geburtstag, date of birth, born / "Born on/in" (not the surname "Born") | 31 files (28 on the title page) | `18452_14648`: "geboren am <date> in <place>"; `20.500.11850_747678`: "Born on <date>" |
| defence, oral exam, acceptance (`defence`) | mündlichen Prüfung, Disputation, Verteidigung, verteidigt, Prüfungstermin, defence/defense, defended, oral exam, colloquium/Kolloquium, akzeptiert, accepted | 30 files | `18452_14711`: "Tag der mündlichen Prüfung: \| 15. Dezember 2005"; `18452_20685`: "submitted on: 12 May 2012 \| defended on: 14 June 2012"; `20.500.11850_148764`: "akzeptiert: März 2005" |
| copyright (`copyright`) | ©, Copyright, "(c)" (not inside "PhD(c)") | 69 files | `20.500.11850_150721`: "Copyright (c) 2008 Distributed Systems Group" |
| access dates (`access`) | Stand, Zugriff, abgerufen, aufgerufen, Abrufdatum, accessed, retrieved, visited, besucht, geprüft, last checked, last modified, "online;" - whole words ("Understanding" contains "stand") | 19 files | `18452_26298.2`: "zuletzt aufgerufen: 30. Dez. 2022" |
| revisions (`revision`) | überarbeitet, korrigiert, revised, revision, corrected, "version with" | 11 files | `18452_20236`: "Berlin, März 2018 \| [überarbeitet im August 2018]"; `18452_14941`: "Version with minor changes, January 1, 2017" |
| build stamps (`build`) | compiled, kompiliert, generated, printed, "erstellt am", "geändert am" | 1 sample file | `20.500.11850_722911`: "This document was compiled on Tuesday 30th May, 2023" |
| repository label (`repository`) | "publication date" | 2,093 files | ETH cover page: "Publication date: \| 2021-07-19" (`20.500.11850_502040`; the title page itself says "July 19, 2021") |

Further exclusions:

| Reason id | Rule | Corpus | Example |
|---|---|---:|---|
| `citation` | a bare year or academic year inside parentheses/brackets, or followed by ")", "]", ";" or ":" | 1,722 candidates in 347 files | `20.500.11850_150272`: "(Diaconis, 1988; Critchlow, 1985)" |
| `range_start` | the start of a range "X - Y", "X bis Y", "X to Y", "X until Y" (the end of the range stays a candidate) | 434 candidates in 368 files | `20.500.11850_153312`: "September 2011 - March 2012"; `_145542`: "5. März bis 27. Juli 2001" |
| `bare_year_position` | a bare year (or `acad`, `num_my`) that meets none of the conditions of 2.4 | 1,483 candidates in 593 files (years in titles or running text) | `18452_18885`: "... SEIT 1945"; `18452_14669`: "Der Nordek-Prozess 1968-70" |
| `after_title_page` | a day/month/semester date after the title page without a submission cue, a "Place, (den/am/im)" prefix or a line of its own | running text | "Im Juli 2005 gründete ..." |
| `implausible_year` | year < 1900 or > run year + 1 | | drawings: `20.500.11850_149453`: "2038" |
| `repository_metadata_page` | every candidate on a repository metadata page (section 1) | 2,093 files | the ETH cover's "Publication date" and any year in the cover title |

DOIs, handles, ISSNs and student numbers ("10.3929/ethz-b-000502040", "10.18452/21371", "16-917-759") produce no candidates thanks to the digit-run guards of the patterns.

### 2.4 Bare years

A bare year (form `year`, and the forms `acad` and `num_my`) counts only if one of these holds:

- it stands **alone on its line**;
- it is an **imprint / place form** "Place, YYYY", including a hyphenated place broken across lines ("Ber- \| lin, 2011.") and "Berlin 2016" as the whole line;
- it is on the **title page at the end of a line** and not preceded by a preposition or ":" (seit, zwischen, und, bis, von, vom, in, im, um, nach, vor, ab, since, between, and, from, to, of, until, "/", "-", "–"), which excludes "SEIT 1945", "ZWISCHEN 1933 UND 1939", "VON 1997 BIS 2000", "mst. 1:2000";
- it carries a **submission cue** (2.5).

### 2.5 Positive cues

| Cue | Words | Evidence |
|---|---|---|
| submission | eingereicht, submitted, submission, Abgabe, abgegeben, vorgelegt, "letzte Version", "Date:", "Datum:", "handed in", "thesis type and date" (same line or label line above) | 31 of 33 cued sample candidates were the thesis date |
| thesis year | "eingereicht/vorgelegt im Jahr(e)", "aus dem Jahr(e)", "im Jahr(e)" directly before the year **and** "arbeit"/"thesis" within the 250 characters before it - counts as a submission cue | series reprints: "geht zurück auf eine Masterarbeit ... aus dem Jahr 2023"; without the second condition "Titelbild: Foto ... aus dem Jahre 1933" (`20.500.11850_150212`) would match |
| place prefix | "Place, (den/am/im/the)" directly before the date | the strongest single form on HU title pages (411 files) |

After the title page a day/month/semester date counts only with one of these cues or on a line of its own (exclusion `after_title_page`).

### 2.6 Mapping to the reported year

- **Semesters:** summer, spring, FS, HS and autumn -> the stated year (ETH metadata agrees in 129 of 133); **winter** (Wintersemester, WS, WiSe, "Winter (term)") -> the **end year** (29 of 34). "WS 2004/05" -> 2005, "Wintersemester 2004" -> 2005.
- **An explicit date beats a semester** on the same page: "Wintersemester 2004/2005" next to "letzte Version am: 8. November 2004" gives 2004.
- **Academic year** "YYYY/YY" -> the end year.
- **Series reprints get the thesis year**, not the series' publication year (owner decision on #81): "eingereicht im Jahr 2003" wins over the imprint "Berlin, 2005" through the thesis-year cue.

### 2.7 Stored result

- Metrics: `publication_year`, `publication_year_source` (`title_page` / `pdf_creation` / `pdf_modification` / `none`), `publication_date_precision` (`day` / `month` / `semester` / `year` / `year_range`; `year` for a PDF-metadata year; NULL for `none`).
- `diagnostics` (local-only, never exported): the stated date at its own precision (`2014-05-12`, `2014-05`, `2014`), the matched form id, the deciding rule (`submission_cue` / `most_precise_on_page`), the surface text, the page (relative to the title page and absolute), every considered candidate with its rejection reason (first 40), the PDF years, and the cover-rule record of section 4.
- **Fallback** unchanged: no valid candidate -> PDF creation year, then modification year; the source says so.

---

## 3. Type markers v1

### 3.1 Window and decision

1. **Window:** the document's own pages 0-4 (after cover pages, if a researcher ruleset is loaded). The first true marker is on own page 0 in 72 % and within pages 0-4 in 99 % of the labelled docs with a marker; page 3 holds the HU series imprints ("Diese Veröffentlichung geht zurück auf eine Masterarbeit ...").
2. **Earliest valid marker wins.** Among labelled docs with a spelled-out marker the first one is correct in 251 of 253. Tie at the same offset (not observed): magister > licentiate > mas > diploma > bachelor > master > semester > doctoral.
3. **MAS override:** a "Master of Advanced Studies / MAS-Programm / MAS-Thesis / MAS in" marker on the **same page** as a winning master marker gives `mas`.
4. **Tier 2:** a bare "Bachelor/Master of <field>" counts only when no tier-1 marker is in the window (corpus: ~7 correct, 1-3 wrong - the author's previous degree).
5. No valid marker -> `unspecified` (corpus: 175 docs; ~25 without usable text, ~9 posters, ~141 without a type statement in the first 5 pages).

### 3.2 Tier-1 markers

Regexes run on the normalised window. "Docs (p0)": corpus docs with the marker on own pages 0-4 (on own page 0); "wins": docs where it is the decisive marker; precision as the winning marker in the sample.

| Class | Marker id | Regex idea | Docs (p0) | Wins | Precision | Corpus example |
|---|---|---|---:|---:|---:|---|
| bachelor | Bachelorarbeit/-thesis | bachelor(s) (-) arbeit / thesis / abschlussarbeit | 342 (300) | 331 | 1.00 | `18452_14678`: "bachelor-arbeit im rahmen des studiengangs statistik" |
| bachelor | degree of Bachelor | (degree / Grad(es) / requirements for / presented for / Abschlussarbeit) + <= 3 words + bachelor | 99 (99) | 9 | 1.00 | `18452_21636`: "a thesis submitted for the degree of bachelor of science" |
| master | Masterarbeit/-thesis | master(s) (-) arbeit / thesis | 2,278 (1,807) | 2,249 | 0.99 | `18452_14670`: "a master thesis presented by <name>" |
| master | MSc/Master of Science thesis | (m.sc. / msc / master of science) thesis | 36 (17) | 19 | 0.75 | `18452_14718`: "m.sc. thesis in statistics" |
| master | degree of Master | degree phrase + <= 3 words + master (not "of advanced") | 279 (255) | 38 | 1.00 | `18452_14670`: "requirements for the degree of master of arts" |
| diploma | Diplomarbeit/Diploma thesis | diplom(-)arbeit (not after "nach"), diploma (-) thesis, diplomthesis | 298 (264) | 287 | 1.00 | `18452_14648`: "diplomarbeit aufbau einer anlage ..." |
| diploma | Diplom-<degree> (spelled out) | diplom(-)ingenieur / informatiker / kauf... / volkswirt / psycholog... / physiker / biolog... / mathematiker / geograph / okonom / padagog / soziolog / betriebswirt | 34 (33) | 3 | 1.00 | `18452_14664`: "zur erlangung des akademischen grades diplom physiker" |
| diploma | Diplomthema/Diplomand | diplom(-)thema, diplomand(in), diplomsemester (ETH D-ARCH plans) | 52 (47) | 46 | 1.00 | `20.500.11850_149914`: "diplomthema c ... diplomandin" |
| diploma | Hausarbeit zur Diplompruefung | hausarbeit zur diplomprufung | 1 | 1 | 1.00 | `18452_14643` |
| magister | Magisterarbeit | magister(-)arbeit, "magisterarb." | 52 (37) | 50 | 1.00 | `18452_14644`: "magisterarbeit zur erlangung des akademischen grades magister artium" |
| magister | Magister/Magistra Artium | magister / magistra artium | 35 (35) | 3 | 1.00 | same |
| licentiate | Lizentiatsarbeit | lizentiatsarbeit, licentiate thesis | 5 (4) | 4 | 1.00 | `20.500.11850_149450`: "lizentiatsarbeit der philosophischen fakultat der universitat zurich" |
| mas | Master of Advanced Studies / MAS | master of advanced studies, "mas-programm", "mas thesis", "mas in " | 9 (7) | 7 | 1.00 | `20.500.11850_484509`: "mas-programm in raumplanung 2017/19" |
| mas | Nachdiplom / postgraduate studies | nachdiplom..., postgraduate studies | 19 (14) | 16 | 1.00 | `20.500.11850_146844`: "nachdiplomarbeit im rahmen des nachdiplomstudiums" |
| semester | Semesterarbeit/-project | semester(-)arbeit / thesis / project / projekt / paper | 16 (3) | 3 | 1.00 | `20.500.11850_155213`: "semester thesis" |
| semester | Studienarbeit | studien(-)arbeit | 1 | 1 | 1.00 | `18452_29926`: "studienarbeit zur erlangung des bachelor of laws" |
| semester | Focus Work | focus work | 1 | 1 | 1.00 | ETH (1 doc) |
| doctoral | Dissertation zur Erlangung / submitted | dissertation (zur erlangung / submitted / eingereicht / presented) | **0** | 0 | - | **no corpus evidence** (see 3.5) |
| doctoral | Doctor of Sciences / Doktorgrad | doctor of science(s)/philosophy, doktorgrad, (grad(es) / degree) (eines / einer / of) doktor(s)/doctor | **0** | 0 | - | no corpus evidence |
| doctoral | Doctoral thesis / Doktorarbeit | doctoral thesis, doktorarbeit | **0** | 0 | - | no corpus evidence |

"Semester thesis" is mostly *mentioned* (acknowledgements, ETH declaration of originality): as any occurrence its precision is 0.17, as the earliest marker 1.00. "Masterarbeit / master's thesis" also appears in Magister abstracts ("in my master's thesis"), hence 0.96 as any occurrence; earliest-wins resolves it.

### 3.3 Tier-2 markers

| Class | Marker id | Regex idea | Docs (p0) | Wins | Example |
|---|---|---|---:|---:|---|
| bachelor | Bachelor of <field> | bachelor of science / arts / engineering / laws / education | 106 (104) | 2 | `18452_14676`: "abschlussarbeit bachelor of science studiengang statistik" |
| master | Master of <field> | master of (not advanced) science / arts / engineering / economics / statistics / education / laws | 456 (266) | 17 | - |

### 3.4 Never markers and exclusions

**Never markers** (precision as a document-level marker on own page 0 of the sample in brackets): B.Sc./BSc (0.00), M.Sc./MSc on their own, M.A. (0.09), Dipl.-X such as Dipl.-Ing., Dipl.-Inform. (0.40), Dr. sc. (0.00), Dr. rer. nat./phil., PhD (0.00), lic. phil., bare "Dissertation", "Masterstudiengang / master programme", bare "Diplom", bare "Master..." (Masterplan, Mastertabelle). They are author, supervisor and examiner titles, study programmes or topics; using them lowers the sample accuracy from 98 % to 93 %. Corpus contexts on own pages 0-4: abbreviated degree next to a name 633 docs, study programme 299, bare "Master..." words 229, bare "Dissertation(en)" 27 (e.g. "Online-Dissertationen" as a title topic).

**Exclusions** (the marker does not count):

| Exclusion | Rule | Corpus | Example |
|---|---|---:|---|
| declaration of originality | inside "(component of every / Bestandteil jeder) ... (degree paper / Abschlussarbeit / Arbeit)" (<= 160 characters) plus 40 characters | 40 docs; changes the result in 4 | ETH declaration: "... is a component of every semester paper, Bachelor's thesis, Master's thesis and any other degree paper ..." |
| "Nachdiplom..." | "Nachdiplomarbeit" is not "Diplomarbeit" (negative lookbehind) | 15 ETH docs | `20.500.11850_146844` |
| repository metadata page | every marker on a repository metadata page (section 1) | 2,093 files | ETH cover page: "<title> \| Master Thesis \| <name> \| Publication date: ..." - the repository's type, wrong for ~15 % of ETH files (274 Diplomarbeiten, 24 MAS papers, 4 Lizentiatsarbeiten in the ETH "master" set) |

A possessive/third-party exclusion ("his/her doctoral thesis", "in ihrer Dissertation") was tested in the exploration and changed no result in the corpus; it is not part of v1.

### 3.5 Classes

| Class | Corpus docs (rule output) | Note |
|---|---:|---|
| master | 2,322 (71 %) | |
| bachelor | 342 (10.5 %) | |
| diploma | 337 (10.3 %) | ~50 of them ETH architecture plans/posters ("Diplomthema", "Diplomand") |
| magister | 53 (1.6 %) | added by v1 |
| mas | 24 | added by v1: Master of Advanced Studies / Nachdiplom - continuing education, not the consecutive master |
| licentiate | 4 | added by v1 |
| semester | 5 | added by v1: Semester-/Studienarbeit, Focus Work |
| doctoral | 0 | added by v1 **without corpus evidence**: professors supervise doctorates, and ETH has a doctoral collection (its PDFs were never downloaded for the reference corpus). The markers are degree phrases only and produce 0 hits on own pages 0-4 of the corpus, so they add no false positives there |
| unspecified | 175 (5.4 %) | |

Baccalaureate is **not** a class: the corpus holds only topic mentions ("vocational/international baccalaureate"). "Not a thesis" cannot be detected from type markers; such documents stay `unspecified`.

Only `bachelor` and `master` enter reference-corpus statistics (`tta.core.types.REFERENCE_THESIS_TYPES`, #49); every class is reported to the user.

### 3.6 Stored result

- Metric: `thesis_type`.
- `diagnostics` (local-only): the deciding rule (`earliest_marker`, `earliest_marker_tier2`, either with `+mas_override`), the winning marker (class, marker id, own page, tier), every marker hit in the window with its exclusion reason (first 40), and the cover-rule record of section 4.

---

## 4. Cover-page hook

Rule-agnostic, empty by default ([ADR-0023](adr/0023-researcher-cover-rulesets.md)). A researcher ruleset (TOML, `tta run --cover-rules FILE`) lists rules; a rule matches a page when every `all_of` string and (if given) one `any_of` string occurs in the normalised page. Leading pages are skipped while they match, at most `max_pages` (default 3). Both modules record in `diagnostics`:

- `cover_rules`: `null` on the default path, else `{id, version, fingerprint, rules, source}`;
- `cover_pages`: `[{page, rule}]` for every skipped page.

With a ruleset both module versions carry `+covers.<id>.<hash>`, so the planner re-runs them when the choice changes.

The one ruleset kept in the repository is `research/cover_rules/eth_research_collection.toml` (rule `eth-rc-download-cover`: the sentence "This page was generated automatically upon download from the ETH Zurich Research Collection"; 2,093 of 2,283 ETH files, 4 with two stacked covers: `20.500.11850_156350` in the older layout, `_590186`, `_697973`, `_784413`).
