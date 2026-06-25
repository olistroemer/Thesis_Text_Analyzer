# ADR-0018: ASCII-only Python source

**Status:** Accepted
**Date:** 2026-06-25
**Drivers:** #26 (the Tk GUI renders missing-glyph boxes for non-ASCII characters baked into UI labels, status strings, and grid cells), #30 (a standing ASCII-only-source policy), QA-PORT (the tool ships as a portable binary that must render identically across machines and fonts), QA-REPRO.

## Decision

Every tracked `*.py` file in the repository contains **only ASCII bytes** (code points `0x00`-`0x7F`). This is enforceable with `grep -rlP '[^\x00-\x7F]' $(git ls-files '*.py')` returning nothing, and is intended to become a CI check.

Two cases are handled differently:

1. **Decorative / typographic non-ASCII** in comments, docstrings, UI labels, log/status strings, and CLI help is rewritten to readable ASCII. Examples applied in this change: em-/en-dash -> `-`; the section sign -> `Sec.`; middle dot -> `|`; right arrow -> `->`; `<=` / `>=` for the inequality glyphs; toolbar/menu/grid emoji dropped in favour of plain text labels (`Add files`, `Run all`, `Report`, `Export`, the close button `X`, the garbled-row marker `[!]`, the artefact-present marker `[x]`, the error cell `err`); and the Yule/Guiraud math in `tta/core/modules/vocabulary.py` rewritten as ASCII pseudo-notation (`K = 1e4 * (sum_i i^2 * V_i - N) / N^2`, `V/sqrt(N)`, `V1`).
2. **Semantic string content that must keep its exact characters** -- most importantly the German-language test fixtures and the German stopword list / word regex in `tta/core/modules/check_extraction_quality.py` -- is encoded with Python `\uXXXX` escapes. The file bytes are pure ASCII; the runtime string value is byte-for-byte unchanged. These characters are NOT deleted or anglicised: the German language-detection, readability, and tokenisation tests require those exact code points, and the passing test suite after escaping is the proof the escapes are correct.

`.sql` migration comments are held to the same ASCII rule (case 1: decorative -> ASCII).

## Context

#26 surfaced as boxes in the Tk GUI: emoji and typographic glyphs embedded directly in widget labels and grid cells have no glyph in the bundled fonts, so they render as missing-character boxes. The root cause is that user-facing text was carried as literal non-ASCII inside source. #30 independently asked for an ASCII-only-source policy. The two are the same fix: make source ASCII, which both repairs the rendering and gives a single, greppable invariant.

The status quo allowed declared-UTF-8 source (the Python default). That is convenient but invites exactly the #26 class of bug -- a non-ASCII glyph can be added to a label at any time and silently break rendering on a machine whose fonts lack it. Strict ASCII removes the failure mode at the source.

## Alternatives considered

- **Allow declared-UTF-8 source (status quo).** No escaping ceremony, comments can use real typography. Rejected: it is precisely what let #26 happen, and it offers no mechanical guard against reintroducing unrenderable glyphs into user-facing strings.
- **Strict ASCII (chosen).** Slightly less readable raw bytes for the handful of semantic German strings (they appear as `\uXXXX`), but a single CI-checkable invariant that closes #26 permanently and keeps source portable.

## Consequences

- Non-ASCII string **content** that must survive at runtime is written with `\uXXXX` escapes (German fixtures, the `check_extraction_quality` stopwords/regex). The escapes are verified by the German-language tests continuing to pass.
- Decorative characters in comments/docstrings/labels use ASCII equivalents; there is a small, well-defined substitution vocabulary (dashes, section sign, arrows, inequalities, math symbols, dropped emoji).
- User-facing text is expected to later flow through **gettext catalogs (#29)**. Those catalogs are *data*, not source, so localized strings with arbitrary Unicode live there and are out of scope for this ASCII rule -- the rule governs `*.py` source bytes only.
- The GUI-rendered help/privacy **markdown** under `tta/core/help/*.md` is OUT of scope: how that prose is authored and rendered is a separate doc-rendering decision, not governed here. (Likewise `docs/**/*.md` prose is untouched.)
- A `grep`-based ASCII gate can be added to CI alongside the existing boundary checks.
