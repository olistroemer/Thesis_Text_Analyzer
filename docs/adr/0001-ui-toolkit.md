# ADR-0001: UI toolkit — tkinter + tksheet

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** QA-PORT (cross-OS), QA-RES (resource-light), distribution simplicity (smaller PyInstaller bundle), preserve option to switch to Qt later (relies on ADR-0002).

## Decision

Use **tkinter** (Python stdlib) for the main UI shell, with **tksheet** (MIT-licensed) as the data-grid widget. tksheet exists because `ttk.Treeview` does not support per-cell styling, which is required by US-RES-OUTLIERS ("different highlighting schemes").

## Context

The application is sent to non-technical professors as a standalone binary. Smaller bundles and fewer dependencies reduce distribution friction. The UI is genuinely a thin presentation layer over the analysis pipeline; cosmetic polish is less load-bearing than testability and module iteration speed.

## Alternatives considered

- **PySide6 (Qt for Python).** Better polish, native look on macOS, free i18n architecture, per-cell styling built-in. Rejected for MVP because of +50 MB bundle size and a stronger runtime dependency. Re-evaluate if bundle size turns out not to constrain distribution.
- **PyQt6.** GPL — would force the deliverable under GPL. Same trap as PyMuPDF/AGPL. Rejected.
- **tkinter alone (no tksheet).** `ttk.Treeview` cannot do per-cell highlighting natively; we would build a custom Canvas-based grid. Higher risk and more code than adopting tksheet.
- **PyWebView / Eel / Toga / wxPython.** Previously analysed and rejected for portability, maturity, or maintenance reasons.

## Consequences

- ✅ Smaller bundle, stdlib base, simpler distribution.
- ✅ tksheet covers the data-grid feature gap.
- ✅ Faster MVP iteration (fewer concepts to master than Qt).
- ⚠️ Native look on macOS is dated (mitigable with sv-ttk theme; documented as a cosmetic limitation).
- ⚠️ i18n architecture (gettext + flexible layouts + RTL handling) is on us, not free from the framework. See SDD §12.
- ⚠️ tksheet has a smaller community than Qt's; we depend on its continued maintenance. Vendoring is an option if it becomes unmaintained.

## Revisit when

- Bundle size proves not to be a binding constraint, OR
- Professor feedback indicates UI polish is critical to adoption, OR
- tksheet maintenance lapses.

In any of these cases, ADR-0002 (hexagonal boundary) keeps the switch to PySide6 bounded to the `ui/` tree.
