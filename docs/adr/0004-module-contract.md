# ADR-0004: Module contract — `ModuleSpec` + ABC, tag-based artefact kinds

**Status:** Accepted — **load-bearing public API**
**Date:** 2026-06-03
**Drivers:** US-RES-CLI (iterate on modules from CLI), QA-TEST (unit-testable in isolation); lightweight, no enforced types; support multiple producers of the same artefact.

## Decision

Modules are subclasses of an ABC carrying a frozen `ModuleSpec` dataclass. Artefact kinds and metric names are bare strings, documented but not type-enforced. Module API is:

```python
class Module(ABC):
    spec: ModuleSpec
    def applicable(self, thesis: Thesis) -> Applicability: ...
    @abstractmethod
    def run(self, ctx: RunContext) -> RunResult: ...
```

`ModuleSpec` carries `name`, `version`, `consumes` (artefact kinds), `produces_artefacts` (artefact kinds), and `produces_metrics` (metric names).

## Context

External researchers contribute modules (LM-based signals, citation analysis). The module contract is therefore a **public interface**, not an internal abstraction. It must be stable enough that external contributors can build against it without reading the entire codebase. For MVP the git commit hash is the de-facto contract version; an explicit `CONTRACT_VERSION` constant is deferred (SDD §12).

## Alternatives considered

- **Strict typed artefacts (Pydantic / Protocol per kind):** rejected for ceremony and weight; user explicitly wanted lightweight.
- **Decorator-registered functions (no ABC):** rejected for weaker introspection; ABC gives clean help and CLI listing.
- **No declared dependencies (dynamic discovery):** rejected; explicit `consumes`/`produces` makes dependency resolution and the swap mechanism work.

## Consequences

- ✅ Modules trivially unit-testable: instantiate, call `run()` with a fake `RunContext`, assert on result.
- ✅ CLI can list modules, show specs, invoke individually.
- ✅ Convention-driven artefacts; format errors fail loud at the consumer, no silent corruption.
- ⚠️ Convention-based formats need disciplined documentation (`core/artefact_kinds.py` is the source of truth).
- ⚠️ Module developer must remember to bump `version` on behavior changes; content-hash side channel deferred to post-MVP.

## Revisit when

Promoting to "stable public API" before external contributions land. After that, breaking contract changes require a deprecation window and a `CONTRACT_VERSION` bump.
