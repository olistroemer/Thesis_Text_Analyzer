# ADR-0013: Runner orchestration — plan/execute split, per-thesis process pool

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-RES-CLI, US-PROF-RERUN, US-PROF-UPDATE, QA-PORT, QA-RES, ADR-0002 (hexagonal boundary), ADR-0006 (append-only history).

## Decision

The runner separates **planning** (deterministic, side-effect-free) from **execution** (stateful, event-emitting). Plans are returned to the caller before execution begins; both CLI and GUI invoke the same API.

Execution uses a `ProcessPoolExecutor` with one worker per concurrent thesis. Modules within a thesis run **serially** in topological order. Workers compute results and serialise them back; the main process commits per-thesis transactions and emits domain events.

Cancellation is **skip-pending**: in-flight theses complete; no new ones are submitted. Module timeouts kill the worker process. Failures within a thesis cascade as `na` to dependents (see [Failure policy](#failure-policy)).

Workers are spawned with the **`spawn`** start method (`multiprocessing.get_context("spawn")`), not the Linux `fork` default: `execute()` runs on a background thread in the GUI, and forking a multi-threaded process risks deadlocks (and warns since Python 3.12). Spawn is thread-safe and matches the macOS/Windows default; per-worker re-import cost (nltk/textstat/langdetect) stays well within the ADR-0015 per-thesis budget (#32).

## Failure policy

Three ways a thesis can end early, all funnelled through **one** cascade path in `Runner`:

| Trigger | Detection |
|---|---|
| **Module timeout** | the in-flight module has been running longer than the per-module timeout |
| **Worker death** | `process.is_alive()` is false and no `thesis_done` arrived (OOM kill, a segfault in the native PDF layer, a dead queue feeder thread) |

Worker death is a distinct outcome, not a variant of the timeout: the timeout guard needs a module *start* stamp, and a worker that dies **between** modules has none — so before this policy such a run had no liveness signal at all and `execute()` polled forever (#55). Detection is therefore explicit, and confirmed over two consecutive polls (the process may exit a few milliseconds before the parent drains its last queued message) before the cascade runs.

Whichever the trigger, the queue is **drained once more before `terminate()`** — a `module_done` written between the previous drain and the kill would otherwise be lost and the module recorded as never having run.

The cascade then classifies every module of the thesis that has not reported:

- **The culprit** — the module in flight (or, if the worker died between modules, the next one in topological order) gets an `error` row: `reason` names the timeout or the worker's exit code. `error` (not `na`) is deliberate: the default plan mode re-runs errored pairs, so the next run retries it.
- **Dependents** — a module whose `consumes` are now unavailable gets an `na` row, `reason` `"upstream failure cascade: ..."`. They are replanned via the normal downstream propagation once the culprit succeeds.
- **Everything else** — a module *independent* of the failure (typically `consumes = ()`) gets **no row**: inventing one would either strand it as a permanently-`na` pair or fake an error it never had. It stays `missing` and the next default run picks it up.

That last group is exactly what leaked adapter progress before this policy: no row **and** no event meant the pair could never be retired, so the determinate bar stopped short of 100 % and the ETA never cleared for the rest of the run (#55, #39). So a fourth `ModuleCompleted` status closes the accounting without inventing history:

- `ModuleCompleted(thesis_id, module_name, status="skipped", duration_ms=None)` — "this planned pair will not run in this run". No DB row corresponds to it. Adapters retire the pair from their remaining set exactly as for `ok`/`na`/`error`; only `ok` pairs feed the ETA rate, so a `skipped` pair cannot distort the estimate.

The invariant adapters may rely on: **every pair in the `RunStarted` plan is followed by exactly one `ModuleCompleted`**, whatever happens to its worker.

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
- `ModuleCompleted(thesis_id, module_name, status, duration_ms)` — `status` is `ok | na | error | skipped`; `skipped` carries `duration_ms=None` and no DB row (see [Failure policy](#failure-policy))
- `ThesisCompleted(thesis_id, summary)`
- `RunCompleted(summary)`
- `RunCancelled(completed, skipped)`

Adapters subscribe and marshal to their event loops (GUI via `root.after`, CLI via direct stderr render). Both adapters expose `cancel()`: the GUI swaps its run buttons for a **Cancel** control while a run is in progress; the CLI installs a SIGINT handler so `Ctrl-C` cancels skip-pending and exits with the partial code (ADR-0003).

## Alternatives considered

- **Per-module thread-pool parallelism within one thesis** (~30 % speedup, much more complexity). Rejected.
- **Single-threaded sequential execution** (simpler but leaves 75 % of CPU idle on a 4-core machine). Rejected.
- **Cooperative cancellation inside modules** (every module would need checkpoints in tight loops; many bottlenecks are in C library calls that don't yield). Rejected for MVP.
- **Workers writing directly to the DB** (SQLite is single-writer; would require connection pooling). Cleaner: main process is sole writer.

## Consequences

- ✅ GUI and CLI share the same Runner API.
- ✅ `--dry-run` is a natural first-class feature.
- ✅ Crashes are isolated per worker / per thesis, and a *hard* crash (no `thesis_done`) is detected rather than hanging the run (#55).
- ✅ DB writes serialised through the main process; no SQLite contention.
- ⚠️ Worst-case cancel lag is one thesis per worker (~30–120 s). Documented.
- ⚠️ Process pool brings pickling overhead per task; amortised away for our work units.

## Revisit when

- Per-thesis runtimes grow large enough that cancel lag becomes a real complaint (then either cooperative cancellation, or worker-kill on user cancel).
- LM-based modules introduce GPU coordination needs (probably forces per-GPU worker, not per-CPU).
