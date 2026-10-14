# ADR-0013: Runner orchestration — plan/execute split, per-thesis process pool

**Status:** Accepted (revision 3 — workers are **long-lived and reused across theses**, one per slot, replaced lazily after any kill and recycled as a safeguard; the per-thesis deadline is measured from the thesis's **hand-over** to its worker (#86, see [Worker reuse](#worker-reuse)). Revision 2 — cancellation revised from pure skip-pending to **bounded-grace worker-kill** (#57, the ADR's own "Revisit when" trigger); a second, **per-thesis** timeout beside the per-module one, both configurable (#56); **worker death** named as a distinct failure trigger and `ModuleCompleted(status="skipped")` added so no planned pair leaves without an event (#55); module stdout/stderr captured into `module_runs.diagnostics` (#68); a third run mode, stale-only (#7). See below.)
**Date:** 2026-06-03 (rev. 2: 2026-08-26; rev. 3: 2026-10-14)
**Drivers:** US-RES-CLI, US-PROF-RERUN, US-PROF-UPDATE, QA-PORT, QA-RES, ADR-0002 (hexagonal boundary), ADR-0006 (append-only history).

## Decision

The runner separates **planning** (deterministic, side-effect-free) from **execution** (stateful, event-emitting). Plans are returned to the caller before execution begins; both CLI and GUI invoke the same API.

Execution runs each thesis in a worker **process**, at most `workers` theses at a time, spawned directly - `multiprocessing.get_context("spawn")` plus `ctx.Process` and `ctx.Queue`, with a hand-rolled scheduling loop in `Runner.execute` - not a `ProcessPoolExecutor` (this ADR said otherwise until #73; the pool was the original design and never the implementation). Since rev. 3 a worker is **long-lived**: it takes one thesis after another from its own task queue, so the libraries load once per worker instead of once per thesis, and it is replaced only when it had to be killed or is recycled (see [Worker reuse](#worker-reuse), #86). The loop is what makes the per-module timeout, the per-thesis deadline, the bounded-grace cancel (#57) and the dead-worker detection (#55) possible at all: each needs to terminate one identified process and account for the pairs it never reported, which a pool's opaque worker reuse does not expose - the runner's own reuse keeps exactly one thesis per worker in flight, so that property holds. Modules within a thesis run **serially** in topological order. Workers compute results and serialise them back; the main process commits per-thesis transactions and emits domain events.

Cancellation is **skip-pending with a bounded grace**: no new theses are submitted, and an in-flight thesis is given a short grace to finish before its worker is terminated (see [Cancellation](#cancellation)). Runaway work is bounded by **two** timeouts - per module and per thesis (see [Timeouts](#timeouts)) - both of which kill the worker process. Failures within a thesis cascade as `na` to dependents (see [Failure policy](#failure-policy)).

Workers are spawned with the **`spawn`** start method (`multiprocessing.get_context("spawn")`), not the Linux `fork` default: `execute()` runs on a background thread in the GUI, and forking a multi-threaded process risks deadlocks (and warns since Python 3.12). Spawn is thread-safe and matches the macOS/Windows default (#32). Its price is that every worker re-imports the libraries (nltk/textstat/langdetect/PyMuPDF); until rev. 3 that was paid once per *thesis* and was most of the per-thesis cost (#86), now it is paid once per *worker*.

## Worker reuse

**Rev. 3 (2026-10-14, #86).** With one fresh process per thesis, library start-up dominated the run: the exp-86 trial (200 theses, native Windows, i7-13700H) measured a median **3.0 s per thesis with a fresh worker against 1.1 s in a reused one**; `mod_tokenize`, `mod_readability` and `mod_classify_language` lose over 90 % of their time, and the time outside the module timers falls from ~450 ms to ~30 ms. Wall clock fell **2.27x at 1 worker and 1.74x at 19**, with all 6,178 metric values and all 2,600 statuses identical. The one-off start-up of a worker is ~2.6 s.

**Mechanism.** A *slot* is one spawned process plus its own task queue and result queue. The worker loops: it takes a `ThesisPlan` from its task queue, runs it exactly as before, and waits for the next one, until it receives the `None` sentinel. The scheduling loop in `execute` is unchanged in shape:

- A pending thesis is **handed over** to an idle slot whose process is still alive; if there is none, a new worker is spawned for it. Replacement is therefore **lazy**: a slot lost to a kill is re-created only when a thesis needs it.
- A thesis that ends with `thesis_done` returns its live worker to the idle set (unless it is [recycled](#recycling)).
- A worker that had to be **terminated** - module timeout, thesis deadline, cancel - or that **died** is dropped and its queues are closed. Every guard keeps working on the one identified process of the one thesis in flight on it; a worker never holds more than one thesis.
- A worker found dead **while idle** carries no thesis, so nothing is recorded; it is dropped at the next hand-over. One that dies after the hand-over is a worker death of that thesis, exactly as before.
- **Shutdown.** Idle workers get the sentinel as soon as nothing is pending (or the run is cancelled), so a long tail does not hold every worker's memory. When `execute` leaves its loop - normally, on cancel, or through an **exception** - a `finally` sends the sentinel to every idle worker, joins it, and terminates (then kills) whatever is still alive, in-flight workers included. No worker outlives `execute()`.
- **Signals and orphans.** Workers **ignore SIGINT**: a terminal delivers Ctrl-C to every process in its foreground group (on Windows: on its console), workers included, but whether and how to cancel is the main process's decision ([Cancellation](#cancellation)) - a worker interrupted by it would otherwise die mid-module and be recorded as a worker death. An idle worker waits on its task queue with a 1 s timeout and exits when its parent process is gone, so a hard-killed main process leaves no idle worker behind.

**State that survives between theses.** Module instances are unpickled fresh with every `ThesisPlan`, and the `tta/core/modules` keep no module-level state, so only *library* state persists. The trial audited it: langdetect reseeds per detection, the MuPDF store, pypdf and nltk stay flat, and the runner's output capture restores the root logger in a `finally`. Two consequences are accepted and documented:

- **Library caches** must not grow with the corpus. textstat's per-text `lru_cache`s and pyphen's unbounded per-word hyphenation cache did (+2.4 MB per thesis, linearly); `mod_readability` clears both after each run, which made a worker plateau at ~330-350 MB with identical results (SDD Sec. 7.4).
- **Python warnings print once per process.** A library's import-time warning (e.g. PyMuPDF's `fitz` deprecation notice) is therefore captured into `_stdout` ([Module output capture](#module-output-capture)) only for each worker's first thesis.

### Recycling

Recycling is a **safeguard**, not a fix: after a thesis, a worker is retired (sentinel; its successor is spawned lazily) when either limit is reached:

| `[runner]` key | Default | Rule |
|---|---|---|
| `recycle_after_theses` | 250 | the worker has served this many theses |
| `recycle_above_rss_mb` | 1024 | its resident set, read after the thesis, exceeds this many MiB |

`0` disables a limit. With the readability fix no growth remains to be caught; the limits bound one that a future library version or module could bring back. **250 theses** costs one start-up per 250 theses (~10 ms per thesis amortised), and a worker leaking at the rate the trial found would reach ~950 MB by then. **1024 MiB** is [ADR-0015](0015-performance-budget.md)'s per-worker memory budget: a worker that stays above it *after* a thesis is over budget at rest. The value is read after the thesis, not as a peak, so a large PDF whose transient peak is returned (the trial's largest sample PDF: 743 MB on a reused worker against 505 MB on a fresh one) does not trigger it.

The resident-set probe uses the **standard library only** (psutil is not a dependency): `GetProcessMemoryInfo` (`WorkingSetSize`) via `ctypes` on Windows and `/proc/<pid>/statm` on Linux. macOS offers no standard-library way to read another process's resident set, so there - and wherever the probe fails - it reports nothing and only the thesis count applies.

### Effect on the ETA

The cost of a run is now a **one-off start-up per worker plus a per-thesis cost**, not a per-thesis cost that contains the start-up. The estimator models it that way (SDD Sec. 5.5): workers start in parallel, so their start-up (~2.6 s, `WORKER_STARTUP_MS`) shifts the whole run once and counts down with the run's elapsed time; the per-module priors are re-seeded from the trial's warm-worker medians (~1.1 s per thesis in sum); and the in-run fit ignores each worker's first thesis, which carries the start-up. Replacements after a kill or a recycle pay the start-up again; they are rare and not modelled.

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
| **Per thesis** | 600 s | the thesis's hand-over to its worker (rev. 3; until then the worker's spawn, which was the same moment) |

The per-module guard alone left the ceiling for one document at `module_timeout x modules attempted` — up to ~60 min with the 12-module catalogue, 240× [ADR-0015](0015-performance-budget.md)'s 15 s per-thesis budget (#56). Worse, it is blind to a worker that keeps *finishing* modules while making no progress overall, and to time spent between modules.

The per-thesis default derives from that budget: ADR-0015 budgets ≤ 15 s per thesis on the supported tier and the low-end 2016 dual-core tier runs ≈ 4× slower (≈ 60 s), so **600 s is ~10× the slowest legitimate figure** — generous enough never to fire on honest work on a slow machine, and it sits *above* the per-module timeout deliberately, so for a single stuck module the finer-grained guard reports first and names the culprit. The per-thesis deadline is the belt-and-braces guard for what the module guard cannot see; neither substitutes for [worker-death detection](#failure-policy), which handles the case where nothing is running at all.

**A timed-out document also floors its own future ETA** (#56). The row a timeout records (`status=error`, `reason="timeout after N s"`, `duration_ms=N*1000`) is excluded from the cost fit, which uses successful runs only - so without a floor the next run would under-estimate the same document just as badly. `Repository.thesis_cost_floors` reads those rows back and `progress.estimate` floors that thesis's remaining bucket at the longest timeout recorded against it. Scoped **per thesis, never per module**: a hang is a property of the one document that hung, and re-pricing the module globally would let a single bad PDF distort every estimate in the database.

Both are settable in `tta.toml`, so a user with 500-page scans need not patch the source to raise them:

```toml
[runner]
workers = 4
module_timeout_s = 300.0
thesis_timeout_s = 600.0
cancel_grace_s = 2.0
recycle_after_theses = 250      # rev. 3, see Recycling; 0 disables
recycle_above_rss_mb = 1024.0   # rev. 3, see Recycling; 0 disables
```

Omitted keys take the defaults above. `Runner.__init__` keeps them as constructor arguments and `Project.make_runner` passes the configured values through — previously only tests could change them.

## Failure policy

Three ways a thesis can end in a *failure*, all funnelled through **one** cascade path in `Runner` (`_fail_worker` -> `_cascade`):

| Trigger | Detection |
|---|---|
| **Module timeout** | the in-flight module has been running longer than the per-module timeout ([Timeouts](#timeouts)) |
| **Thesis deadline** | the thesis has been with its worker longer than the per-thesis timeout, whatever it is doing ([Timeouts](#timeouts)) |
| **Worker death** | `process.is_alive()` is false and no `thesis_done` arrived (OOM kill, a segfault in the native PDF layer, a dead queue feeder thread) |

A fourth early ending, an **abandoned** worker after the cancel grace, shares the pair-accounting half of this policy but not the failure half: it records no `error` and no `na` at all (see [Cancellation](#cancellation)).

Worker death is a distinct outcome, not a variant of the timeout: the timeout guard needs a module *start* stamp, and a worker that dies **between** modules has none — so before this policy such a run had no liveness signal at all and `execute()` polled forever (#55). Detection is therefore explicit, and confirmed over two consecutive polls (the process may exit a few milliseconds before the parent drains its last queued message) before the cascade runs.

Whichever the trigger, the queue is **drained once more before `terminate()`** — a `module_done` written between the previous drain and the kill would otherwise be lost and the module recorded as never having run.

The cascade then classifies every module of the thesis that has not reported:

- **The culprit** — the module in flight (or, if the worker died between modules, the next one in topological order) gets an `error` row: `reason` names the timeout or the worker's exit code. `error` (not `na`) is deliberate: the default plan mode re-runs errored pairs, so the next run retries it.
- **Dependents** — a module whose `consumes` are now unavailable gets an `na` row, `reason` `"upstream failure cascade: ..."`. They are replanned via the normal downstream propagation once the culprit succeeds.
- **Everything else** — a module *independent* of the failure (typically `consumes = ()`) gets **no row**: inventing one would either strand it as a permanently-`na` pair or fake an error it never had. It stays `missing` and the next default run picks it up.

That last group is exactly what leaked adapter progress before this policy: no row **and** no event meant the pair could never be retired, so the determinate bar stopped short of 100 % and the ETA never cleared for the rest of the run (#55, #39). So a fourth `ModuleCompleted` status closes the accounting without inventing history:

- `ModuleCompleted(thesis_id, module_name, status="skipped", duration_ms=None)` — "this planned pair will not run in this run". No DB row corresponds to it. Adapters retire the pair from their remaining set exactly as for `ok`/`na`/`error`; only `ok` pairs feed the ETA rate, so a `skipped` pair cannot distort the estimate.

The invariant adapters may rely on: **every pair in the `RunStarted` plan is followed by exactly one `ModuleCompleted`**, whatever happens to its worker.

## Three run modes

- **Default** ("Run all"): runs `(thesis × module)` pairs that are missing, stale (`module_version` differs from live), or whose last run was `error`.
- **`--rerun`** ("Re-run all"): every `(thesis × module)` pair regardless of state.
- **`--stale-only`** ("Update stale", added #7): the default set **minus** never-run pairs — stale, errored and upstream-changed only.

A `--dry-run` flag prints the plan without executing.

### Why a third mode (#7)

The extended toolbar has always offered both "Re-run all" and "Update stale" (SDD §9.3), but "Update stale" was wired to the *same* call as the default run, so two of the three buttons were identical. The alternative was to delete the button; a third mode is chosen instead because it is the literal reading of **US-PROF-UPDATE** — "update only the analyses whose modules or upstream metrics have changed, **without re-running everything**" — and because the distinction is real for the professor persona: after adding 200 new PDFs *and* upgrading the app, "recompute what my version bump invalidated" and "also extract 200 new documents" are different amounts of an afternoon.

It is a filter, not a new planning path: `plan(stale_only=True)` drops `plan_reason == "missing"` pairs from the initial per-module selection. Two properties follow deliberately from *where* the filter sits — after `_needs_run`, before downstream propagation and before the artefact closure:

- **Upstream-changed pairs survive.** A consumer of a re-planned producer is still added (reason `upstream-changed`), which is the "upstream metrics have changed" half of the story.
- **The artefact closure is not filtered.** A producer pulled in because its artefact is missing from disk keeps its `missing` reason and still runs — otherwise the stale module that needs it would be planned only to fail with an `na` upstream cascade. "Stale-only" constrains *which theses/modules are worth updating*, never *whether the update can be computed*.

`rerun=True` with `stale_only=True` is a contradiction (everything vs. not-everything) and raises `ValueError` rather than picking a winner silently.

The mode exists and is tested on `Runner.plan`; wiring it to a CLI option and to the toolbar button is listed under [Pending in the adapters](#pending-in-the-adapters).

## Pending in the adapters

The core half of this revision is implemented and tested. Everything below is a
consequence of it that lives in `tta/cli/main.py`, `tta/ui/tk/main_window.py` or
`tta/core/progress.py`, and is deliberately left to the lanes that own those
files rather than being reached across a module boundary. Until each lands, the
adapters are behind this ADR — that is a known state, not a discrepancy to
rediscover.

| What | Where | Why it is owed |
|---|---|---|
| Render `HashingProgress` instead of the flat `"Planning..."` status | `ui/tk/main_window.py` (`_run`, `_drain_events`), the CLI's progress render | The event is published but has **no consumer**, so the slow phase is still a silent, mislabelled window for the user — the visible half of #59 |
| Cap each remaining pair's ETA contribution at `module_timeout_s`, and treat a timeout as a *minimum* duration for a failed document | `core/progress.py` (`estimate`), `Repository.module_duration_stats` | #56 scope item 3: with a per-thesis deadline in place the estimate should be bounded by construction; a killed module records `status="error"`, which the `ok`-only rate query filters out, so a timed-out document teaches the estimator nothing |
| Surface `notes["_stdout"]` in the per-thesis detail dialog / error panel | `ui/tk` detail dialog (#46) | #68's "visible in the detail view": capture, truncation and storage are done, the *view* is not |
| Correct three cancel strings that now overstate the wait | `ui/tk/main_window.py` ("Cancelling - finishing in-flight theses..."), `cli/main.py` ("cancelling - finishing in-flight theses..."), [ADR-0003](0003-cli-first-class.md) ("in-flight ones finish") | [Cancellation](#cancellation) no longer waits for in-flight theses; it grants them `cancel_grace_s` and then terminates them |
| Add the `--stale-only` option and point "Update stale" at it | `cli/main.py` `run`, `ui/tk/main_window.py` toolbar | [Three run modes](#three-run-modes): without it two of the three extended-toolbar run buttons remain identical, which is #7's second acceptance criterion |
| Bump ADR-0006's Status/Date to a revision 6 | [ADR-0006](0006-schema.md) header | Its First-run-time bullet is rewritten here (#59) but the header lines are shared with the instant-add work; whoever lands last owns the bump |

## Public API

```python
class Runner:
    def plan(self, theses=None, modules=None, rerun=False, stale_only=False) -> RunPlan: ...
    def execute(self, plan: RunPlan) -> RunSummary: ...
    def cancel(self) -> None: ...
```

## Worker count

Defaults to `max(1, os.cpu_count() - 1)`. Configurable in `tta.toml [runner] workers = N`, alongside the [timeouts](#timeouts).

## Module output capture

A module's `print()` and its log records used to be thrown away, or worse: the spawned child inherits the parent's fd 1/2, so the text landed **unlabelled** (no thesis id, no module name), interleaved across parallel workers, mixed into the CLI's progress render — and lost entirely in the frozen GUI, which has no console at all (`console=False`). Logging fared no worse only because nothing calls `basicConfig`: in the child the root logger has no handler, so `log.info(...)` vanished and `log.warning(...)` and above escaped through logging's `lastResort` (#68).

Two structured channels already existed for diagnostics — `module_runs.diagnostics` (JSON) and `error_traceback`. What was missing is the *unstructured* output a developer actually prints while debugging. So the worker captures it, per module, and it travels home on the existing channel:

- `_run_one_module` runs the module inside `redirect_stdout`/`redirect_stderr` over one `StringIO`, with a `StreamHandler` on that same buffer attached to the root logger (and the root level lowered to `INFO` if it was higher) for the duration. One buffer per module invocation, so output is **attributed to exactly one `(thesis, module)` pair and cannot interleave** with another worker's.
- The text is **tail-truncated to 16 384 characters** — the tail, because that is where a traceback or the last thing before a hang lives — with a `[... N characters truncated ...]` marker, so a runaway loop cannot bloat the database.
- `_commit_thesis` folds it into that run's `diagnostics` JSON under the reserved key **`_stdout`**. No schema migration: `diagnostics` is already documented as JSON diagnostics (SDD §8.1) and is already stripped from exports (SDD §8.3.1, [ADR-0007](0007-export-format.md)), registered `CONTENT` / not-exported in the privacy registry — which is exactly the right classification, because captured output is content-derived free text and can contain fragments of thesis text. It stays on the machine.

Keys under `diagnostics` beginning with `_` are reserved for the runner; a module's own diagnostics keys are untouched.

## Event surface

Published from the main process to a small in-process `EventBus`:

- `HashingProgress(done, total)` — emitted **before** `RunStarted`, while the batch's deferred SHA-256 hashes are computed ([ADR-0006](0006-schema.md), #59). That phase is real work on a large corpus and used to display as a silent, mislabelled "Planning...", because `plan()` itself neither hashes nor reads a file (#59). `total` is the number of theses needing a hash; an adapter that ignores the event loses nothing but the display.
- `RunStarted(plan)` — the plan **after** the hashing fold, so a thesis folded into a byte-identical sibling is already absent from its pair count
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
- **A pool with `maxtasksperchild`** for the reuse of rev. 3 (#86). Rejected for the reason the pool was never implemented: the guards need to kill one identified worker and know which thesis it held. The runner's own slots give reuse without giving that up.
- **Recycling after every N theses as the fix for growing workers** (#86). Rejected as the fix: the growth had one identifiable cause (textstat/pyphen caches), which is cleared at the source; recycling stays only as the [safeguard](#recycling).

## Consequences

- ✅ GUI and CLI share the same Runner API.
- ✅ `--dry-run` is a natural first-class feature.
- ✅ Crashes are isolated per worker / per thesis, and a *hard* crash (no `thesis_done`) is detected rather than hanging the run (#55).
- ✅ DB writes serialised through the main process; no SQLite contention.
- ✅ Cancel lag is bounded by `cancel_grace_s` + the join timeouts (~12 s worst case), not by one thesis per worker (~30–120 s) as in the original decision (#57).
- ✅ Libraries load once per worker, not once per thesis (#86): 2.27x faster at 1 worker, 1.74x at 19 in the trial, with identical metrics.
- ⚠️ Process pool brings pickling overhead per task; amortised away for our work units.
- ⚠️ A long-lived worker carries library state from one thesis to the next. Guarded by clearing the one cache found to grow (`mod_readability`) and by [recycling](#recycling); a large PDF's heap peak now sits on the worker's ~330 MB base instead of a fresh ~200 MB process.
- ⚠️ A warning a library prints once per process reaches `_stdout` only for each worker's first thesis (#86).

## Revisit when

- ~~Per-thesis runtimes grow large enough that cancel lag becomes a real complaint (then either cooperative cancellation, or worker-kill on user cancel).~~ **Triggered and acted on (#57):** bounded-grace worker-kill, see [Cancellation](#cancellation).
- LM-based modules introduce GPU coordination needs (probably forces per-GPU worker, not per-CPU).
