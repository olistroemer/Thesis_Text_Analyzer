# ADR-0022: Publication date from the title page - defined rules and a stored precision

**Status:** Accepted
**Date:** 2026-11-17
**Drivers:** SDD §2.1 (primary research goal: thesis length over publication date), QA-REPRO, QA-PRIV, #81 (this decision), #17 (the detector it replaces), #20 (cover pages), #50 (validation). Rule catalogue: [`titlepage-rules.md`](../titlepage-rules.md) section 2 ("date rules v1").

## Context

`mod_determine_publication_year` 0.1.0 (#17) took the **largest** plausible four-digit year in the first 3,000 characters of `raw_text` and fell back to the PDF creation/modification year. The #81 exploration (cached `raw_text` of the 3,262-file reference corpus, 212 hand-labelled theses) showed why that is not good enough:

- On ETH files the window is the repository's download cover page, so the detector echoes the repository's *deposit* year (equal to the metadata year in 2,271 of 2,283 files).
- Birth dates, defence dates, copyright lines, access dates, revision notes, citations, the start of a work period and years inside titles all sit in the same window. "Take the first date-like string" is right in only 68-85 % of theses, "take the largest" picks revision and defence dates.
- HU series reprints carry the thesis type and date in an imprint on page 3-4, outside a 3,000-character window.
- Only the year was kept, although the page usually states a day or a month.

Correct: 178 of 201 dated sample theses (88.6 %).

## Decision

**1. The date is read under explicit, versioned rules.** "Date rules v1" (catalogue with a corpus example per entry: [`titlepage-rules.md`](../titlepage-rules.md) section 2), ported unchanged from the exploration except where noted below:

- **Window:** the title page (the first page with >= 30 non-space characters) and the 3 pages after it - 97.5 % of the true dates first appear there.
- **Matched forms:** only forms with title-page evidence in the corpus: day dates (D. Monat YYYY, Month D, YYYY, DD.MM.YYYY, M/D/YYYY, ISO), month dates, semesters and seasons (long German names, SS/WS/SoSe/WiSe/HS/FS, two-digit "WS 97/98"), academic years and - restricted - bare years. Month names in German, English and Italian with their OCR/LaTeX variants.
- **Exclusions:** negative cues on the same line before the date or on a label line ending in ":" directly above (birth, defence/oral exam/acceptance, copyright, access, revision, build stamp); negative cues never cross further lines. Also: citations, range starts, implausible years.
- **Bare years** count only alone on their line, as an imprint "Place, YYYY", at the end of a title-page line not after a preposition, or with a submission cue.
- **After the title page** a date counts only with a submission cue, a "Place, (den/am/im)" prefix, or on a line of its own.
- **Preference:** pages in order; within a page a submission-cued date, then the most precise (day/month > semester > year), the earliest on a tie.
- **Semesters:** summer/spring/FS/HS -> the stated year, winter -> the end year; an explicit date beats a semester.
- **Series reprints get the thesis year**, not the series' publication year (owner decision on #81): the thesis-year cue ("eingereicht im Jahr", "aus dem Jahr" with "arbeit/thesis" nearby) counts as a submission cue.
- **Fallback unchanged:** no valid date -> PDF creation year, then modification year, flagged in `publication_year_source`.

**2. A new metric `publication_date_precision`** stores what the winning statement supports: `day`, `month`, `semester`, `year`, `year_range` (an academic year; the end year counts), `year` for a PDF-metadata year, NULL when there is no year. The precision is stored, not padded: a page that says only "2009" is not turned into 2009-01-01. The module now produces three metrics (catalogue: 13 modules, 32 metrics, [ADR-0011](0011-mvp-module-catalogue.md) rev. 6).

**3. Day and month are not metrics.** They stay in the local-only `diagnostics` (the stated date at its own precision, the matched form, the deciding rule, the surface text, the page, every rejected candidate with its reason). A day-precise submission date next to the other exported metrics would add identifying detail for no research benefit - the research axis is the year (SDD §2.1). This is the same posture as `mod_extract_pdf_metadata`, which keeps PDF dates to year precision.

**4. No repository-specific rule on the default path.** Every rule above is a date form, a linguistic cue or a positional restriction tied to no repository or institution. Rules derived from one repository's layout - skipping its download cover, ignoring its metadata page, its "Publication date" label - are researcher data, applied only with `tta run --cover-rules FILE` ([ADR-0023](0023-researcher-cover-rulesets.md)); a ruleset may add negative date cues and mark pages as not evidence. Without one the thesis text is read unmodified: a repository cover page in front of the title page *is* the title page, and its labelled deposit date counts like any other submission-cued date.

**5. Deviations from the exploration rule set** (each small, each recorded):

- French month names are dropped (no title-page evidence; "mars" would match the planet).
- The exploration skipped the ETH cover page; that rule (and the "Publication date" label cue) is researcher data now, not part of the default rules (ADR-0023).
- The standalone test locates the date by position on its line rather than by searching its surface text (same intent; the text search could hit an earlier identical string).

## Results

Exploration (rules tuned on the same 212 theses, so optimistic): 196 of 201 dated theses (97.5 %), 99.5 % precision when it answers; the corpus agrees with ETH metadata at year level in 2,123 of 2,153 files (98.6 %).

Subset check of the implementation (2026-11-17; **not** a corpus run, and not a validation: a 63-thesis slice of the same labelled sample, chosen as described in [ADR-0023](0023-researcher-cover-rulesets.md)): with the ETH researcher ruleset the module reproduces the exploration rule exactly (63 of 63 identical; 56 of 57 dated theses right, 100 % precision). On the default path (no ruleset) every one of the 25 ETH files with a cover page is dated from the cover's labelled deposit date: right at year level in all 22 dated ones of this subset, but at the deposit date's precision (level right in 4 of 22, against 21 of 22 with the ruleset), and 3 undated theses get the deposit year as well (see ADR-0023).

## Consequences

- ✅ The year on the report's time axis is the date the thesis states, not the repository's deposit year or a birth/defence/revision date.
- ✅ The precision of every year is visible and stored; analyses can restrict themselves to day/month-precise dates.
- ✅ Every decision is traceable in `diagnostics` (form, rule, page, rejected candidates).
- ⚠️ No answer from the text for ~6 % of the corpus (no text layer, no date in the window, only excluded candidates) - these fall back to the PDF years, as before.
- ⚠️ On the default path, a repository cover page in front of the title page supplies the repository's deposit date (often the right year, rarely the right precision; ADR-0023).
- ⚠️ The rules were tuned on the sample they were measured on; #50 validates them on a holdout.

## Revisit when

- #50 measures the rules on a holdout, or a new corpus brings date forms or exclusion cues the catalogue lacks (each addition needs corpus evidence and bumps the rules and the module version).
- A use for month-precise dates appears in the report; then decide whether a month metric is worth its privacy cost.
