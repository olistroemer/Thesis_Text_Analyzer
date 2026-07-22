# ADR-0011: MVP module catalogue — 12 modules / 29 metrics

**Status:** Accepted (revision 3 — two title-page modules added: `mod_classify_thesis_type` (#9, +1 metric `thesis_type`) and `mod_determine_publication_year` (#17, +2 metrics `publication_year`, `publication_year_source`); the `theses.type`/`theses.language_hint` override columns are dropped in favour of the detected `thesis_type` metric and the existing `language_code` metric — see [ADR-0019](0019-thesis-type-by-detection.md). 10 → 12 modules, 26 → 29 metrics). Rev. 2 measured hapax as both token-ratio V1/N and type-ratio V1/V (25 → 26 metrics). The **AGPL release gate** below is **partially superseded by [ADR-0017](0017-license.md)** (the project adopts copyleft; PyMuPDF may ship).
**Date:** 2026-06-03 (rev. 2: 2026-06-10; rev. 3: 2026-07-22)
**Drivers:** Exploration findings on trustworthy metrics (memory: `project_eth_text_analysis_findings`); garbled-extraction finding (memory: `project_eth_text_analysis_findings` caveat); AGPL constraint (no PyMuPDF in distribution); primary research goal (SDD §2.1 — length over publication date, #17); US-PROF-ATTRS / US-PROF-COMPARE (#9); user stories US-RES-CLI, US-PROF-QUALITY, US-RES-LANG.

## Decision

MVP ships exactly the twelve modules listed in SDD §7, producing 29 metrics across four artefact kinds (`raw_text`, `language`, `tokens`, `pdf_metadata`). PDF extraction in the first implementation uses **PyMuPDF** (AGPL — development only); alternative extractors are added during the project's library-comparison study.

Two modules parse the **title page** of `raw_text` via a shared parser (`core/modules/_titlepage.py`):

- `mod_classify_thesis_type` (#9, [ADR-0019](0019-thesis-type-by-detection.md)) — produces the `thesis_type` metric ∈ {`bachelor`, `master`, `unspecified`} by a keyword heuristic; replaces the dropped `theses.type` column and the add-time type dialog.
- `mod_determine_publication_year` (#17) — produces the best-estimate `publication_year` (numeric) and `publication_year_source` (text) by fusing the in-text title-page year (primary) with the PDF-metadata `creation_year`/`modification_year` (fallback). `publication_year` — not `creation_year` — is the x-axis of the primary research goal (SDD §2.1, §9.8). Filesystem dates (#18) are out of scope. `mod_extract_pdf_metadata` still produces `creation_year`/`modification_year` as raw PDF signals.

Module-name convention bakes the library into the identifier when the choice is provisional (`mod_extract_pymupdf`) so the producer-swap mechanism remains visible in the schema, privacy registry, and export.

Flesch reading ease is **language-aware**: Flesch's formula for English [@flesch1948], Amstad's German adaptation [@amstad1978]. Other languages are N/A. Garbled-extraction detection flags but does not block downstream modules.

## Library-choice policy

| Module | Initial library | Why initial | Comparison candidates |
|---|---|---|---|
| `mod_extract_pymupdf` | PyMuPDF | what worked in exploration | pdfminer.six, pypdf, pdfplumber, poppler `pdftotext` |
| `mod_count_images` | pypdf | non-AGPL, simple API | pikepdf, pdfminer.six |
| `mod_extract_pdf_metadata` | pypdf | non-AGPL, basic Info dict access | pikepdf, pdfplumber |
| `mod_classify_language` | langdetect | lightweight, no model file needed | fasttext, lingua, polyglot |
| `mod_tokenize` | NLTK punkt_tab | language-aware sentence + word tokenisation | spaCy, stanza |
| `mod_readability` | textstat | implements Flesch + Amstad out of the box | custom implementation |

The library-comparison study (SDD §2.1.1) produces a contracted research output: a ranked recommendation per module class. The distributed `.exe` ships the winners on extraction quality — no longer constrained to non-AGPL candidates (see below).

## AGPL release gate

> **Superseded by [ADR-0017](0017-license.md).** This gate assumed the deliverable must avoid copyleft. ADR-0017 instead adopts a copyleft licence for the whole project, so PyMuPDF may ship as-is and the gate is retired. The text below is kept as the historical rationale.

~~`mod_extract_pymupdf` MUST be replaced with a non-AGPL alternative before the first `.exe` distribution. CI on the release branch greps `core/` for `import fitz`/`import pymupdf` and fails the build.~~

## What we deferred and why

- **Zipf alpha / R²** — small effect in Kaggle baseline, defer to v2.
- **Word entropy** — redundant with `yules_k` (|r| ≈ 0.92).
- **Six PDF-technical metrics** (`pdf_version`, `is_encrypted`, `is_linearized`, `xmp_present`, `has_acroform`, `has_xfa`) — low research signal, easy to add later when a use case emerges. The MVP keeps the six research-relevant ones (`page_count_meta`, `producer_category`, `creator_category`, `creation_year`, `modification_year`, `has_outline`).
- **LM-based signals** (perplexity, embedding burstiness) — separate researcher's modules.
- **Citation/quotation validity** — separate researcher's modules.
- **Word-list-based vocabulary metrics** — word-list licensing unresolved.
- **Multivariate outlier detection** — extended-mode v2.
- **Smarter figure module** — `mod_count_images` is the POC; full figure analysis is post-MVP.

## Consequences

- ✅ Catalogue small enough that every module gets a help page, fixtures, and privacy entries by MVP ship.
- ✅ Four artefact kinds keep the kind vocabulary minimal.
- ✅ Theses in unsupported languages gracefully degrade via N/A rather than failing.
- ✅ Garbled-thesis case is flagged but doesn't break the pipeline.
- ⚠️ SDD §2 must explicitly state that the MVP measures metric trends, NOT presence of AI authorship.
- ⚠️ ~~AGPL release gate must be visibly enforced in CI; missing it could ship a copyleft-tainted binary.~~ Retired by [ADR-0017](0017-license.md): a copyleft binary is now the intended posture, not a hazard.

## Revisit when

- New researcher modules (LM-based, citation analysis) are ready to land.
- Library-comparison study completes and a non-AGPL extractor wins.
- A use case demands an additional metric that doesn't fit the current modules.
