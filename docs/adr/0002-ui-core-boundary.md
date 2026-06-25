# ADR-0002: UI/core boundary — hexagonal architecture

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-RES-CLI (researcher iterates via CLI), QA-TEST (modules unit-testable in isolation), QA-PORT, future UI swap (defer to v2 of `ui/`).

## Decision

Hexagonal architecture. `core/*` is toolkit-agnostic. Two primary adapters ship in MVP: `ui/tk/` (the GUI) and `cli/` (the command-line tool). Both are peers over the same core.

## Invariants

1. `core/*` must not import from `ui/*` or `cli/*`. (CI-enforced via grep on the import graph.)
2. Cross-boundary types are plain dataclasses; no widget references, no Click contexts, no Qt objects.
3. Long-running operations expose progress via domain events; adapters marshal to their own event loops.
4. Help content lives in `core/help/*.md`; both GUI and CLI render it (Tk text widget vs terminal markdown rendering).
5. Strings produced by core are unlabelled; adapters wrap for i18n in their own framework.
6. Every module is unit-testable without instantiating any adapter.

## Context

A standalone analyzer that targets a multi-year lifecycle, will be distributed to multiple institutions, and may need different presentations over time. Strong UI/core separation pays for itself in testability and future-proofing even before we contemplate a UI rewrite.

## Alternatives considered

- **Single integrated UI + business logic.** Faster to write a first prototype; significantly higher cost to add a CLI or swap toolkits later. Rejected.
- **MVC-only inside the UI layer.** Helps within the UI but doesn't isolate the core. Half-measure.

## Consequences

- ✅ GUI and CLI evolve independently; researcher CLI workflow is unblocked from any GUI work.
- ✅ Module developers can iterate via `tta run --module M --input fixture.pdf` without launching the GUI.
- ✅ A future UI swap (Tk → Qt) is bounded to `ui/`.
- ⚠️ Discipline must be enforced (import-graph CI check).
- ⚠️ Trivial-looking features that span "data plus UI" require slightly more ceremony.

## Revisit when

Never; structural commitment.
