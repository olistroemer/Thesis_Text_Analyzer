# ADR-0005: Producer swap deferred; comparison via separate runs

**Status:** Accepted (revised — scope tightened)
**Date:** 2026-06-03
**Drivers:** Researcher need to compare alternative implementations (e.g. pdfminer vs pypdf vs PyMuPDF for `raw_text` extraction); user preference for a simple professor experience.

## Decision

In MVP, **exactly one module is registered as the producer for each artefact kind** — the runner picks it from the module registry; no configuration is required. Multiple registered producers for the same kind is a startup error.

Comparison of different libraries is done by **running the analysis twice into separate databases** with different code (e.g. swap `mod_extract_pymupdf` for `mod_extract_pdfminer` in the registry), then comparing the resulting DBs externally. No in-DB pivot is supported in MVP.

**Note (2026-11-17, #22, [ADR-0024](0024-two-text-views.md)).** One module may produce several kinds: `mod_extract_pymupdf` produces both `raw_text` and `prose_text`. "Exactly one producer per kind" still holds; a swapped-in extractor replaces the producer of both views, so it must also write `prose_text` (SDD §7.3).

## Future selection mechanism (deferred)

When this feature is un-deferred (see SDD §12), the design adds a three-layer producer selection: (1) module-declared default, (2) `tta.toml [producers]` table, (3) `--producer KIND=MODULE` CLI override. None of these exist in MVP.

## Context

The earlier design added a `producer_chains` table and multi-value-per-metric storage so that the same DB could carry side-by-side metric values from different producer chains. Pushback from project lead: this complicated the professor's experience for a researcher feature. The simpler comparison-via-separate-runs approach was preferred.

## Alternatives considered

- **Multi-value-per-metric in one DB (the original proposal).** Producer chains tracked via a hash; UI/grid pivots on the chain. Cleaner for in-app comparison but adds substantial schema and UI complexity. Deferred to post-MVP.
- **Hardcode a single library per artefact kind.** Loses flexibility for the library-comparison study, which is now methodological output (SDD §2.1.1). Rejected.

## Consequences

- ✅ Schema and UI stay simple for the professor.
- ✅ Researchers retain library comparison as separate runs (cheap and natural).
- ✅ Multiple modules producing the same kind is supported architecturally; no in-DB conflict.
- ⚠️ Side-by-side comparison in one DB is unavailable in MVP.
- ⚠️ Comparing across runs requires external join logic if both runs are in the same DB.

## Revisit when

After the library-comparison study completes and we want to ship the winner in a researcher-facing comparison view inside the GUI.
