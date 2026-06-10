# ADR-0011: MVP module catalogue — 10 modules / 26 metrics

**Status:** Accepted (revision 2 — hapax measured as both token-ratio V1/N and type-ratio V1/V so the variants can be compared on real cohorts; 25 → 26 metrics)
**Date:** 2026-06-03 (rev. 2: 2026-06-10)
**Drivers:** Exploration findings on trustworthy metrics (memory: `project_eth_text_analysis_findings`); garbled-extraction finding (memory: `project_eth_text_analysis_findings` caveat); AGPL constraint (no PyMuPDF in distribution); user stories US-RES-CLI, US-PROF-QUALITY, US-RES-LANG.

## Decision

MVP ships exactly the ten modules listed in SDD §7, producing 26 metrics across four artefact kinds (`raw_text`, `language`, `tokens`, `pdf_metadata`). PDF extraction in the first implementation uses **PyMuPDF** (AGPL — development only); alternative extractors are added during the project's library-comparison study.

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

The library-comparison study (SDD §2.1.1) produces a contracted research output: a ranked recommendation per module class. The distributed `.exe` ships the winners.

## AGPL release gate

`mod_extract_pymupdf` MUST be replaced with a non-AGPL alternative before the first `.exe` distribution. CI on the release branch greps `core/` for `import fitz`/`import pymupdf` and fails the build.

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
- ⚠️ AGPL release gate must be visibly enforced in CI; missing it could ship a copyleft-tainted binary.

## Revisit when

- New researcher modules (LM-based, citation analysis) are ready to land.
- Library-comparison study completes and a non-AGPL extractor wins.
- A use case demands an additional metric that doesn't fit the current modules.
