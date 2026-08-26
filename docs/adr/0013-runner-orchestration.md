# ADR-0013: Runner orchestration — plan/execute split, per-thesis process pool

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-RES-CLI, US-PROF-RERUN, US-PROF-UPDATE, QA-PORT, QA-RES, ADR-0002 (hexagonal boundary), ADR-0006 (append-only history).

## Decision

The runner separates **planning** (deterministic, side-effect-free) from **execution** (stateful, event-emitting). Plans are returned to the caller before execution begins; both CLI and GUI invoke the same API.

Execution uses a `ProcessPoolExecutor` with one worker per concurrent thesis. Modules within a thesis run **serially** in topological order. Workers compute results and serialise them back; the main process commits per-thesis transactions and emits domain events.

Cancellation is **skip-pending with a bounded grace**: no new theses are submitted, and an in-flight thesis is given a short grace to finish before its worker is terminated (see [Cancellation](#cancellation)). Runaway work is bounded by **two** timeouts - per module and per thesis (see [Timeouts](#timeouts)) - both of which kill the worker process. Failures within a thesis cascade as `na` to dependents (see [Failure policy](#failure-policy)).

Workers are spawned with the **`spawn`** start method (`multiprocessing.get_context("spawn")`), not the Linux `fork` default: `execute()` runs on a background thread in the GUI, and forking a multi-threaded process risks deadlocks (and warns since Python 3.12). Spawn is thread-safe and matches the macOS/Windows default; per-worker re-import cost (nltk/textstat/langdetect) stays well within the ADR-0015 per-thesis budget (#32).

## Cancellation

**Revised (#57).** The original decision was purely skip-pending: `cancel()` stopped *scheduling*, and every in-flight thesis ran all its remaining modules to completion. The "Revisit when" trigger below — "per-thesis runtimes grow large enough that cancel lag becomes a real complaint (then either cooperative cancellation, or worker-kill on user cancel)" — has arrived, so this is the planned revision, not a contradiction: **worker-kill on user cancel**, bounded.

`cancel()` records the monotonic time of the request. From then on the poll loop:

1. submits no new theses (unchanged);
2. keeps draining and committing what in-flight workers report, so a thesis that was nearly done still lands (unchanged);
3. once `cancel_grace_s` (default 2 s) has elapsed since the request, **abandons** every remaining worker: `terminate()` → `join` → `kill()` fallback.

Worst-case time from click to control returning is therefore `cancel_grace_s + 2 × join timeout`, ~12 s, in place of one full thesis per worker.

An abandoned worker is deliberately *not* treated as a failure:

- Outcomes already received are committed, exactly as for a normal thesis.
- Modules that never reported get **no row** — no error, no `na`. A cancelled pair must stay `missing`, or ADR-0015's pause/resume property ("close the laptop, continue tomorrow") would resume against a history full of failures the user never caused.
- Each of them gets a `ModuleCompleted(status="skipped")` so progress still reaches a terminal state, per the [failure policy](#failure-policy)'s pair-accounting invariant.

`RunSummary` therefore distinguishes `theses_completed` from `theses_abandoned`, and a run counts as cancelled when either theses were skipped or workers were abandoned — previously `cancelled` required a *pending* thesis, so cancelling the last thesis of a batch reported a clean completion.

The grace exists so that pressing Cancel on a batch that is 95 % through its current thesis does not throw that work away; 2 s is generous next to the ADR-0015 per-module budgets (the largest is 6 s) yet two orders of magnitude below the old worst case. Configurable as `[runner] cancel_grace_s`.

Cooperative cancellation inside modules remains rejected (see [Alternatives](#alternatives-considered)): many of our bottlenecks are C-library calls that never yield to a checkpoint.

## Timeouts

Two nested guards, both enforced by the main process from its poll loop, both killing the worker and running the [failure policy](#failure-policy) cascade:

| Guard | Default | Measured from |
|---|---|---|
| **Per module** | 300 s | the `module_started` message for the module in flight |
| **Per thesis** | 600 s | the worker's spawn |

The per-module guard alone left the ceiling for one document at `module_timeout x modules attempted` — up to ~60 min with the 12-module catalogue, 240× [ADR-0015](0015-performance-budget.md)'s 15 s per-thesis budget (#56). Worse, it is blind to a worker that keeps *finishing* modules while making no progress overall, and to time spent between modules.

The per-thesis default derives from that budget: ADR-0015 budgets ≤ 15 s per thesis on the supported tier and the low-end 2016 dual-core tier runs ≈ 4× slower (≈ 60 s), so **600 s is ~10× the slowest legitimate figure** — generous enough never to fire on honest work on a slow machine, and it sits *above* the per-module timeout deliberately, so for a single stuck module the finer-grained guard reports first and names the culprit. The per-thesis deadline is the belt-and-braces guard for what the module guard cannot see; neither substitutes for [worker-death detection](#failure-policy), which handles the case where nothing is running at all.

Both are settable in `tta.toml`, so a user with 500-page scans need not patch the source to raise them:

```toml
[runner]
workers = 4
module_timeout_s = 300.0
thesis_timeout_s = 600.0
cancel_grace_s = 2.0
```

Omitted keys take the defaults above. `Runner.__init__` keeps them as constructor arguments and `Project.make_runner` passes the configured values through — previously only tests could change them.

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

Defaults to `max(1, os.cpu_count() - 1)`. Configurable in `tta.toml [runner] workers = N`, alongside the [timeouts](#timeouts).

## Event surface

Published from the main process to a small in-process `EventBus`:

- `RunStarted(plan)`
- `ThesisStarted(thesis_id)`
- `ModuleStarted(thesis_id, module_name)`
- `ModuleCompleted(thesis_id, module_name, status, duration_ms)` — `status` is `ok | na | error | skipped`; `skipped` carries `duration_ms=None` and no DB row (see [Failure policy](#failure-policy))
- `ThesisCompleted(thesis_id, summary)`
- `RunCompleted(summary)`
- `RunCancelled(completed, skipped, abandoned)` — `abandoned` counts workers terminated after the cancel grace

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
- ✅ Cancel lag is bounded by `cancel_grace_s` + the join timeouts (~12 s worst case), not by one thesis per worker (~30–120 s) as in the original decision (#57).
- ⚠️ Process pool brings pickling overhead per task; amortised away for our work units.

## Revisit when

- ~~Per-thesis runtimes grow large enough that cancel lag becomes a real complaint (then either cooperative cancellation, or worker-kill on user cancel).~~ **Triggered and acted on (#57):** bounded-grace worker-kill, see [Cancellation](#cancellation).
- LM-based modules introduce GPU coordination needs (probably forces per-GPU worker, not per-CPU).
