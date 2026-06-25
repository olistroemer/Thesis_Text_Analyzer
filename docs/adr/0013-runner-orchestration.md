# ADR-0013: Runner orchestration — plan/execute split, per-thesis process pool

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-RES-CLI, US-PROF-RERUN, US-PROF-UPDATE, QA-PORT, QA-RES, ADR-0002 (hexagonal boundary), ADR-0006 (append-only history).

## Decision

The runner separates **planning** (deterministic, side-effect-free) from **execution** (stateful, event-emitting). Plans are returned to the caller before execution begins; both CLI and GUI invoke the same API.

Execution uses a `ProcessPoolExecutor` with one worker per concurrent thesis. Modules within a thesis run **serially** in topological order. Workers compute results and serialise them back; the main process commits per-thesis transactions and emits domain events.

Cancellation is **skip-pending**: in-flight theses complete; no new ones are submitted. Module timeouts kill the worker process. Failures within a thesis cascade as `na` to dependents.

Workers are spawned with the **`spawn`** start method (`multiprocessing.get_context("spawn")`), not the Linux `fork` default: `execute()` runs on a background thread in the GUI, and forking a multi-threaded process risks deadlocks (and warns since Python 3.12). Spawn is thread-safe and matches the macOS/Windows default; per-worker re-import cost (nltk/textstat/langdetect) stays well within the ADR-0015 per-thesis budget (#32).

## Two run modes

- **Default** ("Run all"): runs `(thesis × module)` pairs that are missing, stale (`module_version` differs from live), or whose last run was `error`.
- **`--rerun`**: every `(thesis × module)` pair regardless of state.

A `--dry-run` flag prints the plan without executing.

## Public API

```python
class Runner:
    def plan(self, theses=None, modules=None, rerun=False) -> RunPlan: ...
    def execute(self, plan: RunPlan) -> RunSummary: ...
    def cancel(self) -> None: ...
```

## Worker count

Defaults to `max(1, os.cpu_count() - 1)`. Configurable in `tta.toml [runner] workers = N`.

## Event surface

Published from the main process to a small in-process `EventBus`:

- `RunStarted(plan)`
- `ThesisStarted(thesis_id)`
- `ModuleStarted(thesis_id, module_name)`
- `ModuleCompleted(thesis_id, module_name, status, duration_ms)`
- `ThesisCompleted(thesis_id, summary)`
- `RunCompleted(summary)`
- `RunCancelled(completed, skipped)`

Adapters subscribe and marshal to their event loops (GUI via `root.after`, CLI via direct stderr render).

## Alternatives considered

- **Per-module thread-pool parallelism within one thesis** (~30 % speedup, much more complexity). Rejected.
- **Single-threaded sequential execution** (simpler but leaves 75 % of CPU idle on a 4-core machine). Rejected.
- **Cooperative cancellation inside modules** (every module would need checkpoints in tight loops; many bottlenecks are in C library calls that don't yield). Rejected for MVP.
- **Workers writing directly to the DB** (SQLite is single-writer; would require connection pooling). Cleaner: main process is sole writer.

## Consequences

- ✅ GUI and CLI share the same Runner API.
- ✅ `--dry-run` is a natural first-class feature.
- ✅ Crashes are isolated per worker / per thesis.
- ✅ DB writes serialised through the main process; no SQLite contention.
- ⚠️ Worst-case cancel lag is one thesis per worker (~30–120 s). Documented.
- ⚠️ Process pool brings pickling overhead per task; amortised away for our work units.

## Revisit when

- Per-thesis runtimes grow large enough that cancel lag becomes a real complaint (then either cooperative cancellation, or worker-kill on user cancel).
- LM-based modules introduce GPU coordination needs (probably forces per-GPU worker, not per-CPU).
