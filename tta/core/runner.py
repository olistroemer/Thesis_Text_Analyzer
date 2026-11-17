"""Runner: deterministic plan phase + stateful execute phase (ADR-0013).

- ``plan()`` is side-effect-free and returns a ``RunPlan``.
- ``execute()`` runs up to ``workers`` theses concurrently, each in a
  long-lived worker process that takes one thesis after another (ADR-0013
  "Worker reuse", #86); modules within a thesis run serially in topological
  order inside the worker. A worker that had to be killed or died is replaced
  lazily; one that has served long enough is recycled.
- Workers compute in isolation and stream results over a queue; the main
  process is the sole DB writer (one transaction per thesis) and the sole
  event publisher.
- Per-module timeout kills the stuck worker; a worker that dies without
  reporting is detected and fails its thesis the same way; failures cascade
  as ``na`` to dependents and unreachable pairs are reported as ``skipped``
  so adapter progress closes; cancellation is skip-pending with a bounded
  grace, after which in-flight workers are terminated.
"""

from __future__ import annotations

import contextlib
import io
import logging
import multiprocessing
import queue as queue_mod
import shutil
import signal
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tta.core import events, procmem
from tta.core.artefacts import ArtefactStore
from tta.core.db.repository import TIMEOUT_REASON_PREFIX, Repository
from tta.core.modules.base import Module, NotApplicable, RunContext, RunResult
from tta.core.modules.registry import ModuleRegistry
from tta.core.types import Thesis

logger = logging.getLogger(__name__)

DEFAULT_MODULE_TIMEOUT_S = 300.0

#: Wall-clock ceiling for one thesis, measured from its hand-over to a worker
#: (ADR-0013 "Timeouts", #56; from the worker's spawn until workers became
#: long-lived, #86). The per-module timeout alone left one document
#: able to burn ``module_timeout x modules attempted`` - up to ~60 min with the
#: 12-module catalogue - and is blind to time spent *between* modules. Derived
#: from ADR-0015: <= 15 s per thesis on the supported tier, ~4x slower on the
#: 2016 dual-core tier (~60 s), so this is ~10x the slowest legitimate figure.
#: Deliberately above DEFAULT_MODULE_TIMEOUT_S so that for a single stuck
#: module the finer-grained guard fires first and names the culprit.
DEFAULT_THESIS_TIMEOUT_S = 600.0

#: How long an in-flight thesis may keep running after the user cancels before
#: its worker is terminated (ADR-0013 "Cancellation", #57). Long enough that
#: cancelling a batch 95 % through its current thesis does not throw that work
#: away - the largest ADR-0015 per-module budget is 6 s - and two orders of
#: magnitude below the old worst case of one full thesis per worker.
DEFAULT_CANCEL_GRACE_S = 2.0

#: Characters of a module's captured stdout/stderr/log output kept in its run
#: record (ADR-0013 "Module output capture", #68). The **tail** is kept - that
#: is where a traceback or the last thing before a hang lives - so a runaway
#: loop cannot bloat the database.
STDOUT_CAPTURE_CHARS = 16 * 1024

#: Reserved key under ``module_runs.diagnostics`` carrying that capture. Keys
#: beginning with ``_`` belong to the runner; a module's own keys are untouched.
STDOUT_DIAGNOSTICS_KEY = "_stdout"

#: How long a worker must be observed dead (``is_alive()`` false) with no
#: ``thesis_done`` before its thesis is failed. A process can exit a few
#: milliseconds before the parent drains the last message its queue feeder
#: flushed, so death is confirmed over consecutive polls rather than on the
#: first sighting (ADR-0013 failure policy, #55).
DEAD_WORKER_GRACE_S = 0.25

#: Seconds to wait for a terminated worker to actually exit before escalating
#: ``terminate()`` (SIGTERM) to ``kill()`` (SIGKILL).
JOIN_TIMEOUT_S = 5.0

#: Theses one long-lived worker serves before it is retired and a fresh one
#: takes its slot (ADR-0013 "Recycling", #86). A safeguard, not a fix: with
#: mod_readability's cache sweep a worker plateaus at ~330-350 MB, and this
#: bounds a growth a future library could bring back. One start-up (~2.6 s)
#: per 250 theses is ~10 ms per thesis. ``0`` disables it.
DEFAULT_RECYCLE_AFTER_THESES = 250

#: Resident set (MiB) above which a worker is retired after its thesis (#86):
#: ADR-0015's per-worker memory budget. Read *after* the thesis, so a large
#: PDF's transient peak that is given back does not trigger it. ``0`` disables
#: it; where no stdlib probe exists (macOS) only the thesis count applies.
DEFAULT_RECYCLE_ABOVE_RSS_MB = 1024.0

#: How often an idle worker checks that the process that spawned it is still
#: alive, so a hard-killed main process cannot leave workers waiting forever.
WORKER_IDLE_POLL_S = 1.0

# Plan reasons per run mode (SDD Sec. 5.5): default = missing + stale +
# errored; --rerun = everything; --stale-only = the default set minus missing.
REASON_MISSING = "missing"
REASON_STALE = "stale"
REASON_ERRORED = "errored"
REASON_RERUN = "rerun"
REASON_UPSTREAM = "upstream-changed"


@dataclass(frozen=True)
class PlannedModule:
    module: Module
    plan_reason: str

    @property
    def name(self) -> str:
        return self.module.spec.name


@dataclass
class ThesisPlan:
    thesis: Thesis
    modules: list[PlannedModule]
    # preexisting artefacts (kind -> absolute path) for consumed kinds
    # whose producer is not part of this plan
    artefacts: dict[str, str]


@dataclass
class RunPlan:
    theses: list[ThesisPlan]
    rerun: bool = False

    @property
    def pair_count(self) -> int:
        return sum(len(tp.modules) for tp in self.theses)

    def describe(self) -> list[str]:
        """Human-readable plan lines (CLI --dry-run)."""
        lines = []
        for tp in self.theses:
            for pm in tp.modules:
                lines.append(f"{tp.thesis.pdf_filename}: {pm.name} ({pm.plan_reason})")
        return lines


@dataclass
class RunSummary:
    theses_total: int = 0
    theses_completed: int = 0
    theses_skipped: int = 0  # never started (cancelled before their turn)
    theses_abandoned: int = 0  # in flight when the cancel grace ran out (#57)
    ok: int = 0
    na: int = 0
    error: int = 0
    cancelled: bool = False
    duration_s: float = 0.0
    #: worker processes started by this run - one per slot plus replacements
    #: and recycles (ADR-0013 "Worker reuse", #86)
    workers_spawned: int = 0


@dataclass
class _ModuleOutcome:
    """One module result as serialised back from a worker."""

    module_name: str
    module_version: str
    status: str  # ok | na | error
    reason: str | None = None
    error_traceback: str | None = None
    started_at: str = ""
    duration_ms: int = 0
    metrics: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    artefacts: dict[str, str] = field(default_factory=dict)  # kind -> tmp path
    workdir: str | None = None
    #: captured stdout/stderr/log records, tail-truncated (#68)
    stdout: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextlib.contextmanager
def _capture_output(buffer: io.StringIO):
    """Route everything a module writes into ``buffer`` (ADR-0013 "Module
    output capture", #68).

    Covers ``print()`` (stdout *and* stderr, merged in write order) and log
    records: the root logger has no handler in a spawned worker, so ``log.info``
    would vanish and warnings would escape through logging's ``lastResort`` onto
    the parent's terminal, unlabelled. A handler on the same buffer fixes both;
    the root level is lowered to INFO for the duration if it was higher.

    Runs only inside the worker process, one buffer per module invocation - so
    output can never interleave with another worker's, and is attributed to
    exactly one ``(thesis, module)`` pair.
    """
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    if previous_level > logging.INFO:
        root.setLevel(logging.INFO)
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            yield
    finally:
        root.setLevel(previous_level)
        root.removeHandler(handler)
        handler.close()


def _tail(text: str, limit: int = STDOUT_CAPTURE_CHARS) -> str | None:
    """The last ``limit`` characters, marked if anything was dropped."""
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"[... {len(text) - limit} characters truncated ...]\n" + text[-limit:]


def _run_one_module(pm: PlannedModule, thesis: Thesis, available: dict[str, str]) -> _ModuleOutcome:
    spec = pm.module.spec
    outcome = _ModuleOutcome(module_name=spec.name, module_version=spec.version, status="ok")
    outcome.started_at = _utc_now_iso()
    t0 = time.perf_counter()
    buffer = io.StringIO()
    try:
        with _capture_output(buffer):
            applicability = pm.module.applicable(thesis)
            if not applicability.ok:
                outcome.status = "na"
                outcome.reason = applicability.reason
                return outcome
            missing = [k for k in spec.consumes if k not in available]
            if missing:
                outcome.status = "na"
                outcome.reason = f"upstream NA cascade: no {', '.join(missing)} available"
                return outcome
            workdir = Path(tempfile.mkdtemp(prefix=f"tta-{thesis.id}-{spec.name}-"))
            outcome.workdir = str(workdir)
            ctx = RunContext(
                thesis=thesis,
                artefacts={k: Path(p) for k, p in available.items() if k in spec.consumes},
                workdir=workdir,
            )
            result: RunResult = pm.module.run(ctx)
            outcome.metrics = result.metrics
            outcome.diagnostics = result.diagnostics
            outcome.artefacts = {k: str(p) for k, p in result.artefacts.items()}
    except NotApplicable as exc:
        outcome.status = "na"
        outcome.reason = str(exc)
    except Exception as exc:
        outcome.status = "error"
        outcome.reason = f"{type(exc).__name__}: {exc}".splitlines()[0]
        outcome.error_traceback = traceback.format_exc()
    finally:
        outcome.duration_ms = int((time.perf_counter() - t0) * 1000)
        outcome.stdout = _tail(buffer.getvalue())
    return outcome


def _worker_main(thesis_plan: ThesisPlan, queue) -> None:
    """Worker process: run the thesis's modules serially in topo order.

    No DB access, no event publishing (ADR-0013) - results stream back
    over the queue as ('module_started' | 'module_done' | 'thesis_done').
    """
    available = dict(thesis_plan.artefacts)
    for pm in thesis_plan.modules:
        queue.put(("module_started", pm.name))
        outcome = _run_one_module(pm, thesis_plan.thesis, available)
        if outcome.status == "ok":
            available.update(outcome.artefacts)
        queue.put(("module_done", outcome))
    queue.put(("thesis_done", None))


def _worker_loop(tasks, results) -> None:
    """Long-lived worker process (ADR-0013 "Worker reuse", #86).

    Takes one ``ThesisPlan`` after another from its own task queue and runs
    each through ``_worker_main``, so the libraries a module imports stay
    loaded for the next thesis. Exits on the ``None`` sentinel, on a broken
    queue, or when its parent process is gone.

    SIGINT is ignored: a terminal delivers Ctrl-C to every process in its
    foreground group (on Windows: on its console), but cancelling is the main
    process's decision (ADR-0013 "Cancellation"). A worker killed by it would
    be recorded as a worker death, and a cancelled pair must stay ``missing``.
    """
    with contextlib.suppress(ValueError, OSError, AttributeError):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    parent = multiprocessing.parent_process()
    while True:
        try:
            thesis_plan = tasks.get(timeout=WORKER_IDLE_POLL_S)
        except queue_mod.Empty:
            if parent is not None and not parent.is_alive():
                return  # orphaned: nobody will ever hand over a thesis again
            continue
        except (EOFError, OSError):
            return
        if thesis_plan is None:
            return
        _worker_main(thesis_plan, results)


@dataclass(eq=False)
class _Slot:
    """One long-lived worker process with its own task and result queues.

    Each worker gets its *own* result queue, so a message can always be
    attributed to the one thesis in flight on that worker - the property every
    liveness guard relies on (#86)."""

    process: multiprocessing.Process
    tasks: object
    results: object
    #: theses handed over to this worker so far (recycling, #86)
    served: int = 0
    #: monotonic stamp of the retirement sentinel, None while in service
    retired_monotonic: float | None = None


@dataclass
class _ActiveWorker:
    process: multiprocessing.Process
    queue: object
    plan: ThesisPlan
    #: monotonic stamp taken at hand-over, for the per-thesis deadline (#56, #86)
    started_monotonic: float = field(default_factory=time.monotonic)
    outcomes: list[_ModuleOutcome] = field(default_factory=list)
    current_module: str | None = None
    module_started_monotonic: float | None = None
    done: bool = False
    #: first poll at which the process was seen dead without a ``thesis_done``
    dead_since: float | None = None
    #: terminated by a cancel rather than finishing or failing (#57)
    abandoned: bool = False
    #: the long-lived worker this thesis was handed to (#86)
    slot: _Slot | None = None
    #: the runner terminated the process; it must never take another thesis
    terminated: bool = False


class Runner:
    def __init__(
        self,
        repo: Repository,
        store: ArtefactStore,
        registry: ModuleRegistry,
        bus: events.EventBus | None = None,
        workers: int | None = None,
        module_timeout_s: float | None = None,
        thesis_timeout_s: float | None = None,
        cancel_grace_s: float | None = None,
        recycle_after_theses: int | None = None,
        recycle_above_rss_mb: float | None = None,
        rss_probe: Callable[[int], int | None] | None = None,
    ):
        self.repo = repo
        self.store = store
        self.registry = registry
        self.bus = bus or events.EventBus()
        self.workers = workers or max(1, (multiprocessing.cpu_count() or 2) - 1)
        # ADR-0013 "Timeouts": two nested guards, both settable from tta.toml.
        self.module_timeout_s = (
            DEFAULT_MODULE_TIMEOUT_S if module_timeout_s is None else module_timeout_s
        )
        self.thesis_timeout_s = (
            DEFAULT_THESIS_TIMEOUT_S if thesis_timeout_s is None else thesis_timeout_s
        )
        self.cancel_grace_s = (
            DEFAULT_CANCEL_GRACE_S if cancel_grace_s is None else cancel_grace_s
        )
        # ADR-0013 "Recycling" (#86): two safeguards, 0 disables either.
        self.recycle_after_theses = int(
            DEFAULT_RECYCLE_AFTER_THESES if recycle_after_theses is None else recycle_after_theses
        )
        self.recycle_above_rss_mb = float(
            DEFAULT_RECYCLE_ABOVE_RSS_MB if recycle_above_rss_mb is None else recycle_above_rss_mb
        )
        #: pid -> resident bytes or None; injectable so tests need no real leak
        self.rss_probe = rss_probe or procmem.rss_bytes
        self._cancelled = False
        self._cancel_requested_monotonic: float | None = None

    # -- plan phase (deterministic, side-effect-free) ----------------------

    def plan(
        self,
        theses: list[Thesis] | None = None,
        modules: list[str] | None = None,
        rerun: bool = False,
        stale_only: bool = False,
    ) -> RunPlan:
        """The three MVP run modes (ADR-0013).

        ``rerun`` plans every pair; ``stale_only`` plans the default set
        *minus* never-run pairs ("Update stale", US-PROF-UPDATE, #7). The two
        are contradictory, so passing both raises.
        """
        if rerun and stale_only:
            raise ValueError("rerun and stale_only are contradictory run modes")
        if theses is None:
            theses = self.repo.list_theses(local_only=True, include_excluded=False)
        else:
            theses = [t for t in theses if not t.excluded]
        selected = self.registry.in_topological_order(modules)
        latest = self.repo.latest_runs()
        # one corpus-wide query instead of 1-2 per thesis (#59)
        artefact_rows = self.repo.artefacts_by_thesis()

        thesis_plans = []
        for thesis in theses:
            planned: dict[str, PlannedModule] = {}
            for module in selected:
                reason = self._needs_run(latest.get((thesis.id, module.spec.name)), module, rerun)
                if reason:
                    if stale_only and reason == REASON_MISSING:
                        continue  # "Update stale": never-run pairs stay pending
                    planned[module.spec.name] = PlannedModule(module, reason)
            # downstream propagation (US-PROF-UPDATE): a planned producer
            # changes the inputs of its consumers, so they re-run too
            refreshed_kinds = {
                kind for pm in planned.values() for kind in pm.module.spec.produces_artefacts
            }
            for module in selected:
                if module.spec.name in planned:
                    continue
                if any(kind in refreshed_kinds for kind in module.spec.consumes):
                    planned[module.spec.name] = PlannedModule(module, REASON_UPSTREAM)
                    refreshed_kinds.update(module.spec.produces_artefacts)
            # Guard before the artefact work, not after (#59): the closure
            # cannot add to an empty plan, so a fully up-to-date thesis used to
            # pay a query and a stat per artefact to plan nothing.
            if not planned:
                continue
            on_disk = self._existing_artefacts(artefact_rows.get(thesis.id, {}))
            self._close_over_artefacts(planned, on_disk)
            produced_here = {
                kind for pm in planned.values() for kind in pm.module.spec.produces_artefacts
            }
            available = {k: v for k, v in on_disk.items() if k not in produced_here}
            ordered = [
                PlannedModule(m, planned[m.spec.name].plan_reason)
                for m in self.registry.in_topological_order(planned.keys())
            ]
            thesis_plans.append(ThesisPlan(thesis=thesis, modules=ordered, artefacts=available))
        return RunPlan(theses=thesis_plans, rerun=rerun)

    def _needs_run(self, last, module: Module, rerun: bool) -> str | None:
        if rerun:
            return REASON_RERUN
        if last is None:
            return REASON_MISSING
        if last["module_version"] != module.spec.version:
            return REASON_STALE
        if last["status"] == "error":
            return REASON_ERRORED
        return None

    def _close_over_artefacts(
        self, planned: dict[str, PlannedModule], on_disk: dict[str, str]
    ) -> None:
        """Pull in producers of consumed kinds whose artefact is not on
        disk (e.g. deleted artefacts/ directory) - they count as missing."""
        changed = True
        while changed:
            changed = False
            produced_here = {
                kind for pm in planned.values() for kind in pm.module.spec.produces_artefacts
            }
            for pm in list(planned.values()):
                for kind in pm.module.spec.consumes:
                    if kind in produced_here or kind in on_disk:
                        continue
                    producer = self.registry.producer_of(kind)
                    if producer.spec.name not in planned:
                        planned[producer.spec.name] = PlannedModule(producer, REASON_MISSING)
                        changed = True

    def _existing_artefacts(self, rows: dict[str, str]) -> dict[str, str]:
        """Resolve one thesis's artefact references to the ones actually on
        disk. Stats each file once per plan (#59); the caller subtracts the
        kinds this run will re-produce."""
        available = {}
        for kind, relative in rows.items():
            path = self.store.resolve(relative)
            if path.exists():
                available[kind] = str(path)
        return available

    # -- execute phase (stateful: events + DB writes) -----------------------

    def cancel(self) -> None:
        """Skip-pending with a bounded grace (ADR-0013 "Cancellation", #57).

        No new theses start, and in-flight ones get ``cancel_grace_s`` to
        finish on their own - long enough not to throw away a thesis that is
        nearly done - after which the poll loop terminates their workers. Safe
        to call from another thread (the GUI's Cancel button): it only writes
        two fields that the loop reads.
        """
        self._cancelled = True
        if self._cancel_requested_monotonic is None:
            self._cancel_requested_monotonic = time.monotonic()

    def _apply_lazy_hashing(self, plan: RunPlan) -> None:
        """Compute + persist ``pdf_sha256`` for the planned theses whose hash is
        still NULL (deferred from add time, ADR-0006 rev. 4, #38; batched, #59).

        One batched call: one query for the rows, the digests in a small thread
        pool, the content-dedup fold, one commit, and the hashes written back
        onto the plan's ``Thesis`` objects - no per-thesis commit and no
        ``get_thesis`` re-read. Runs in the main process, the sole DB writer
        (ADR-0013); the hash is not needed by workers (modules read
        ``pdf_path``). A thesis folded into a byte-identical sibling is dropped
        from the plan; a file that cannot be read is left un-hashed and still
        runs (its extractor records the per-thesis error).

        ``HashingProgress`` is published throughout, because on a large corpus
        this phase is slow enough that an adapter showing nothing looks hung
        (#59) - and it happens before ``RunStarted``, so the run's own progress
        bar cannot cover it.
        """
        pending = [tp for tp in plan.theses if tp.thesis.pdf_sha256 is None]
        if not pending:
            return
        total = len(pending)
        done = 0
        self.bus.publish(events.HashingProgress(done, total))

        def _tick(_thesis_id: int) -> None:
            nonlocal done
            done += 1
            self.bus.publish(events.HashingProgress(done, total))

        canonical = self.repo.assign_content_hashes(
            [tp.thesis for tp in pending], on_hashed=_tick
        )
        kept: list[ThesisPlan] = []
        for tp in plan.theses:
            target = canonical.get(tp.thesis.id, tp.thesis.id)
            if target != tp.thesis.id:
                logger.info(
                    "thesis %s has content identical to %s - folded (ADR-0006 rev. 4)",
                    tp.thesis.id,
                    target,
                )
                continue
            if tp.thesis.pdf_sha256 is None:
                logger.warning(
                    "thesis %s (%s) could not be hashed - deferring",
                    tp.thesis.id,
                    tp.thesis.pdf_path,
                )
            kept.append(tp)
        plan.theses = kept
        self.bus.publish(events.HashingProgress(total, total))

    def execute(self, plan: RunPlan) -> RunSummary:
        t0 = time.monotonic()
        self._cancelled = False
        self._cancel_requested_monotonic = None
        self._apply_lazy_hashing(plan)
        summary = RunSummary(theses_total=len(plan.theses))
        self.bus.publish(events.RunStarted(plan))

        # 'spawn' start method (#32): the GUI calls execute() on a background
        # thread, and forking a multi-threaded process risks deadlocks (and
        # emits a DeprecationWarning on Linux). spawn is thread-safe and
        # matches the macOS/Windows default. _worker_loop is module-level and
        # its ThesisPlans (frozen ModuleSpec instances) pickle cleanly.
        ctx = multiprocessing.get_context("spawn")
        pending = list(plan.theses)
        active: list[_ActiveWorker] = []
        # Long-lived workers (ADR-0013 "Worker reuse", #86). ``slots`` is every
        # worker this run started that has not been reaped yet, whatever its
        # state - the ``finally`` below needs all of them; ``idle`` holds live
        # workers waiting for a thesis; ``retiring`` those sent the sentinel.
        slots: list[_Slot] = []
        idle: list[_Slot] = []
        retiring: list[_Slot] = []

        try:
            while pending or active:
                while pending and len(active) < self.workers and not self._cancelled:
                    tp = pending.pop(0)
                    slot = self._take_idle(idle, slots)
                    if slot is None:
                        slot = self._spawn_slot(ctx, slots, summary)
                    slot.tasks.put(tp)
                    slot.served += 1
                    logger.debug(
                        "thesis %s -> worker pid %s (thesis no. %d on it)",
                        tp.thesis.id, slot.process.pid, slot.served,
                    )
                    active.append(
                        _ActiveWorker(
                            process=slot.process, queue=slot.results, plan=tp, slot=slot
                        )
                    )
                    self.bus.publish(events.ThesisStarted(tp.thesis.id))
                if idle and (not pending or self._cancelled):
                    # Nothing left to hand over: let idle workers go now
                    # rather than hold their memory through the run's tail.
                    while idle:
                        self._retire(idle.pop(), retiring)
                self._reap_retiring(retiring, slots)
                if self._cancelled and not active:
                    break

                for worker in active:
                    self._drain_queue(worker)
                    if worker.done:
                        continue
                    if self._cancel_grace_elapsed():
                        self._abandon_worker(worker)
                    elif self._module_timed_out(worker):
                        self._kill_timed_out(worker)
                    elif self._thesis_timed_out(worker):
                        self._kill_over_deadline(worker)
                    elif self._worker_died(worker):
                        self._reap_dead_worker(worker)
                finished = [w for w in active if w.done]
                active = [w for w in active if not w.done]
                # Every finished worker is placed (idle / retiring / dropped)
                # before any commit, so a commit that raises cannot strand a
                # process outside the bookkeeping the ``finally`` relies on.
                for worker in finished:
                    self._release(worker, idle, retiring, slots)
                for worker in finished:
                    self._commit_thesis(worker, summary)
                if active:
                    time.sleep(0.02)
        finally:
            self._shutdown_slots(slots, idle, retiring)

        summary.theses_skipped = len(pending)
        # A cancel that caught the last thesis of a batch in flight skips
        # nothing, but is still a cancel (#57).
        summary.cancelled = self._cancelled and (
            summary.theses_skipped > 0 or summary.theses_abandoned > 0
        )
        summary.duration_s = time.monotonic() - t0
        if summary.cancelled:
            self.bus.publish(
                events.RunCancelled(
                    completed=summary.theses_completed,
                    skipped=summary.theses_skipped,
                    abandoned=summary.theses_abandoned,
                )
            )
        else:
            self.bus.publish(events.RunCompleted(summary))
        return summary

    # -- worker slots (ADR-0013 "Worker reuse", #86) --------------------------

    def _spawn_slot(self, ctx, slots: list[_Slot], summary: RunSummary) -> _Slot:
        tasks, results = ctx.Queue(), ctx.Queue()
        process = ctx.Process(target=_worker_loop, args=(tasks, results), daemon=True)
        slot = _Slot(process=process, tasks=tasks, results=results)
        slots.append(slot)  # tracked before start(), so the finally sees it
        process.start()
        summary.workers_spawned += 1
        logger.debug("spawned worker pid %s", process.pid)
        return slot

    def _take_idle(self, idle: list[_Slot], slots: list[_Slot]) -> _Slot | None:
        """A live idle worker for the next thesis, or None. A worker that died
        while idle held no thesis, so it is dropped without any record."""
        while idle:
            slot = idle.pop()
            if slot.process.is_alive():
                return slot
            logger.warning(
                "idle worker pid %s died (exitcode=%s) - replacing it",
                slot.process.pid,
                slot.process.exitcode,
            )
            self._drop_slot(slot, slots)
        return None

    def _release(
        self,
        worker: _ActiveWorker,
        idle: list[_Slot],
        retiring: list[_Slot],
        slots: list[_Slot],
    ) -> None:
        """Place a finished thesis's worker: back to ``idle`` if it may take
        another thesis, to ``retiring`` if it is due for recycling, dropped if
        it was terminated or died (a replacement is spawned lazily)."""
        slot = worker.slot
        if slot is None:  # not one of ours (unit tests drive guards directly)
            return
        if worker.terminated or not slot.process.is_alive():
            self._drop_slot(slot, slots)
        elif self._due_for_recycling(slot):
            self._retire(slot, retiring)
        else:
            idle.append(slot)

    def _due_for_recycling(self, slot: _Slot) -> bool:
        """ADR-0013 "Recycling": a safeguard against growth, read after each
        thesis. The probe may report None (macOS, an exited process); then
        only the thesis count applies."""
        if self.recycle_after_theses > 0 and slot.served >= self.recycle_after_theses:
            logger.info(
                "recycling worker pid %s after %d theses", slot.process.pid, slot.served
            )
            return True
        if self.recycle_above_rss_mb > 0:
            try:
                rss = self.rss_probe(slot.process.pid)
            except Exception:  # noqa: BLE001 - a probe must never fail the run
                rss = None
            if rss is not None and rss > self.recycle_above_rss_mb * 1024 * 1024:
                logger.info(
                    "recycling worker pid %s: resident set %.0f MiB above %.0f MiB",
                    slot.process.pid,
                    rss / (1024 * 1024),
                    self.recycle_above_rss_mb,
                )
                return True
        return False

    def _retire(self, slot: _Slot, retiring: list[_Slot]) -> None:
        """Ask an idle worker to exit (sentinel); it is reaped once gone."""
        with contextlib.suppress(Exception):
            slot.tasks.put(None)
        slot.retired_monotonic = time.monotonic()
        retiring.append(slot)

    def _reap_retiring(self, retiring: list[_Slot], slots: list[_Slot]) -> None:
        """Drop retired workers that have exited; stop one that ignores the
        sentinel for longer than the join timeout. Does not block otherwise."""
        for slot in list(retiring):
            overdue = (
                slot.retired_monotonic is not None
                and time.monotonic() - slot.retired_monotonic > JOIN_TIMEOUT_S
            )
            if slot.process.is_alive():
                if not overdue:
                    continue
                logger.warning(
                    "retired worker pid %s ignored its sentinel - stopping it",
                    slot.process.pid,
                )
                self._stop_process(slot.process)
            retiring.remove(slot)
            self._drop_slot(slot, slots)

    def _drop_slot(self, slot: _Slot, slots: list[_Slot]) -> None:
        """Forget a worker that has exited: reap it and close both of its
        queues. One that somehow still runs stays tracked for the finally."""
        slot.process.join(timeout=0 if not slot.process.is_alive() else JOIN_TIMEOUT_S)
        if slot.process.is_alive():
            return
        self._close_queues(slot)
        if slot in slots:
            slots.remove(slot)

    @staticmethod
    def _close_queues(slot: _Slot) -> None:
        for q in (slot.tasks, slot.results):
            with contextlib.suppress(Exception):
                # The reader may be dead with data still buffered; never let
                # the feeder thread block the interpreter's exit on it.
                q.cancel_join_thread()
            with contextlib.suppress(Exception):
                q.close()

    def _shutdown_slots(
        self, slots: list[_Slot], idle: list[_Slot], retiring: list[_Slot]
    ) -> None:
        """No worker outlives ``execute()`` - on a normal end, on cancel, and
        when an exception escapes the loop (#86).

        Idle and retiring workers get the sentinel and a bounded join; any
        other live worker can only be one still holding a thesis (an exception
        escaped mid-run), and is terminated at once. Whatever has not exited
        by the deadline is terminated, then killed."""
        resting = set(map(id, idle)) | set(map(id, retiring))
        for slot in slots:
            with contextlib.suppress(Exception):
                if not slot.process.is_alive():
                    continue
                if id(slot) not in resting:
                    slot.process.terminate()
                elif slot.retired_monotonic is None:
                    slot.tasks.put(None)
        deadline = time.monotonic() + JOIN_TIMEOUT_S
        for slot in slots:
            with contextlib.suppress(Exception):
                slot.process.join(timeout=max(0.0, deadline - time.monotonic()))
        for slot in slots:
            with contextlib.suppress(Exception):
                if slot.process.is_alive():
                    logger.warning(
                        "worker pid %s did not exit at shutdown - stopping it",
                        slot.process.pid,
                    )
                    self._stop_process(slot.process)
            self._close_queues(slot)
        slots.clear()
        idle.clear()
        retiring.clear()

    @staticmethod
    def _stop_process(process) -> None:
        """SIGTERM, then SIGKILL if it will not go. Bounded by construction."""
        process.terminate()
        process.join(timeout=JOIN_TIMEOUT_S)
        if process.is_alive():
            process.kill()
            process.join(timeout=JOIN_TIMEOUT_S)

    # -- execute internals --------------------------------------------------

    def _drain_queue(self, worker: _ActiveWorker) -> None:
        while True:
            try:
                kind, payload = worker.queue.get_nowait()
            except queue_mod.Empty:
                return
            if kind == "module_started":
                worker.current_module = payload
                worker.module_started_monotonic = time.monotonic()
                self.bus.publish(events.ModuleStarted(worker.plan.thesis.id, payload))
            elif kind == "module_done":
                worker.outcomes.append(payload)
                worker.current_module = None
                worker.module_started_monotonic = None
                self.bus.publish(
                    events.ModuleCompleted(
                        worker.plan.thesis.id, payload.module_name, payload.status, payload.duration_ms
                    )
                )
            elif kind == "thesis_done":
                worker.done = True

    # -- liveness guards and the single failure-cascade path ----------------
    #
    # Three triggers end a thesis early - a module timeout, a worker that dies
    # without reporting, and (on cancel) an abandoned worker - and all of them
    # funnel through ``_fail_worker`` / ``_cascade`` so that no path can leak a
    # planned pair out of the adapters' progress accounting (ADR-0013 failure
    # policy, #55).

    def _module_timed_out(self, worker: _ActiveWorker) -> bool:
        return (
            worker.module_started_monotonic is not None
            and time.monotonic() - worker.module_started_monotonic > self.module_timeout_s
        )

    def _cancel_grace_elapsed(self) -> bool:
        """True once the user's cancel has gone unanswered for the grace."""
        return (
            self._cancel_requested_monotonic is not None
            and time.monotonic() - self._cancel_requested_monotonic >= self.cancel_grace_s
        )

    def _abandon_worker(self, worker: _ActiveWorker) -> None:
        """Terminate a worker still in flight when the cancel grace ran out.

        Deliberately *not* a failure: outcomes already received are committed,
        but modules that never reported get **no row** - no error, no ``na``.
        A cancelled pair must stay ``missing``, or ADR-0015's pause/resume
        ("close the laptop, continue tomorrow") would resume against a history
        full of failures the user never caused. They do get ``skipped`` events,
        so progress still reaches a terminal state.
        """
        self._drain_queue(worker)
        if worker.done:
            return  # finished inside the grace after all
        logger.info(
            "cancel: abandoning thesis %s after %.1f s grace (%d of %d modules committed)",
            worker.plan.thesis.id,
            self.cancel_grace_s,
            len(worker.outcomes),
            len(worker.plan.modules),
        )
        self._terminate(worker)
        for pm in self._unreported(worker):
            self.bus.publish(
                events.ModuleCompleted(
                    worker.plan.thesis.id, pm.name, events.MODULE_SKIPPED, None
                )
            )
        worker.abandoned = True
        worker.done = True

    def _thesis_timed_out(self, worker: _ActiveWorker) -> bool:
        """The per-thesis wall-clock deadline (#56): the belt-and-braces guard
        for what the per-module timeout cannot see - time spent *between*
        modules, and a worker that keeps finishing modules while making no
        progress overall."""
        return time.monotonic() - worker.started_monotonic > self.thesis_timeout_s

    def _kill_over_deadline(self, worker: _ActiveWorker) -> None:
        elapsed = time.monotonic() - worker.started_monotonic
        logger.warning(
            "thesis %s exceeded its %.0f s deadline (%.0f s elapsed) - killing worker",
            worker.plan.thesis.id,
            self.thesis_timeout_s,
            elapsed,
        )
        self._drain_queue(worker)
        if worker.done:
            return
        self._terminate(worker)
        self._fail_worker(
            worker,
            worker.current_module,
            reason=f"thesis deadline exceeded after {elapsed:.0f} s",
            duration_ms=int(elapsed * 1000),
        )

    def _worker_died(self, worker: _ActiveWorker) -> bool:
        """True once the process has been seen dead, with no ``thesis_done``,
        for ``DEAD_WORKER_GRACE_S``.

        This is the only liveness signal for a worker that dies *between*
        modules (OOM kill, a segfault in the native PDF layer, a dead queue
        feeder thread): ``module_started_monotonic`` is ``None`` there, so the
        timeout guard can never fire and the poll loop would otherwise sleep
        forever (#55). The grace absorbs the race in which the process has
        exited but its last flushed messages have not been read yet - each poll
        re-drains the queue before getting here, so a ``thesis_done`` still in
        the pipe wins.
        """
        if worker.process.is_alive():
            worker.dead_since = None
            return False
        now = time.monotonic()
        if worker.dead_since is None:
            worker.dead_since = now
            return False
        return now - worker.dead_since >= DEAD_WORKER_GRACE_S

    def _reap_dead_worker(self, worker: _ActiveWorker) -> None:
        exitcode = worker.process.exitcode
        logger.error(
            "worker for thesis %s died without reporting (exitcode=%s) - failing the thesis",
            worker.plan.thesis.id,
            exitcode,
        )
        elapsed_ms = 0
        if worker.module_started_monotonic is not None:
            elapsed_ms = int((time.monotonic() - worker.module_started_monotonic) * 1000)
        self._fail_worker(
            worker,
            worker.current_module,
            reason=f"worker died before reporting (exitcode={exitcode})",
            duration_ms=elapsed_ms,
        )

    def _kill_timed_out(self, worker: _ActiveWorker) -> None:
        # Drain once more first: a ``module_done`` written between the previous
        # drain and the terminate() below would be lost, and that module would
        # be recorded as never having run (#55).
        self._drain_queue(worker)
        if worker.done or not self._module_timed_out(worker):
            return  # finished under the wire
        timed_out = worker.current_module
        logger.warning(
            "module %s on thesis %s exceeded %.0f s - killing worker",
            timed_out,
            worker.plan.thesis.id,
            self.module_timeout_s,
        )
        self._terminate(worker)
        self._fail_worker(
            worker,
            timed_out,
            reason=f"{TIMEOUT_REASON_PREFIX}{self.module_timeout_s:.0f} s",
            duration_ms=int(self.module_timeout_s * 1000),
        )

    def _terminate(self, worker: _ActiveWorker) -> None:
        """SIGTERM, then SIGKILL if it will not go. Bounded by construction.
        A terminated worker is never handed another thesis (#86)."""
        worker.terminated = True
        worker.process.terminate()
        worker.process.join(timeout=JOIN_TIMEOUT_S)
        if worker.process.is_alive():
            logger.warning(
                "worker for thesis %s ignored terminate() - killing", worker.plan.thesis.id
            )
            worker.process.kill()
            worker.process.join(timeout=JOIN_TIMEOUT_S)

    def _unreported(self, worker: _ActiveWorker) -> list[PlannedModule]:
        """Planned modules of this thesis that have not sent an outcome yet,
        in plan (topological) order."""
        reported = {o.module_name for o in worker.outcomes}
        return [pm for pm in worker.plan.modules if pm.name not in reported]

    def _fail_worker(
        self, worker: _ActiveWorker, failed: str | None, reason: str, duration_ms: int
    ) -> None:
        """End a thesis on a terminal worker failure: one ``error`` row for the
        culprit, then the cascade over everything else it never reported.

        ``failed`` is the module in flight; when the worker died between modules
        it is ``None`` and the next module in topological order - the one that
        was about to run - takes the error. ``error`` rather than ``na`` is
        deliberate: the default plan mode re-runs errored pairs, so the next run
        retries it (ADR-0013 failure policy).
        """
        thesis_id = worker.plan.thesis.id
        unreported = self._unreported(worker)
        if failed is None:
            failed = unreported[0].name if unreported else None
        if failed is None:
            worker.done = True  # died after the last module_done; nothing lost
            return
        spec = self.registry.get(failed).spec
        worker.outcomes.append(
            _ModuleOutcome(
                module_name=failed,
                module_version=spec.version,
                status="error",
                reason=reason,
                started_at=_utc_now_iso(),
                duration_ms=duration_ms,
            )
        )
        self.bus.publish(events.ModuleCompleted(thesis_id, failed, "error", duration_ms))
        self._cascade(worker, unavailable=set(spec.produces_artefacts))
        worker.done = True

    def _cascade(self, worker: _ActiveWorker, unavailable: set[str]) -> None:
        """Classify every still-unreported module of a failed thesis.

        Dependents of the failure (their ``consumes`` are no longer obtainable)
        get an ``na`` row and event. Modules *independent* of the failure get
        **no row** - inventing one would either strand them as permanently-``na``
        pairs or fake an error they never had, so they stay ``missing`` for the
        next run - but they do get a ``skipped`` event, which is what closes the
        adapters' pair accounting (#55, #39).
        """
        thesis_id = worker.plan.thesis.id
        produced = self._produced_kinds(worker)
        for pm in self._unreported(worker):
            consumed_missing = [
                k
                for k in pm.module.spec.consumes
                if k in unavailable
                or (k not in worker.plan.artefacts and k not in produced)
            ]
            if consumed_missing:
                unavailable.update(pm.module.spec.produces_artefacts)
                worker.outcomes.append(
                    _ModuleOutcome(
                        module_name=pm.name,
                        module_version=pm.module.spec.version,
                        status="na",
                        reason=f"upstream failure cascade: no {', '.join(consumed_missing)} available",
                        started_at=_utc_now_iso(),
                        duration_ms=0,
                    )
                )
                self.bus.publish(events.ModuleCompleted(thesis_id, pm.name, "na", 0))
            else:
                self.bus.publish(
                    events.ModuleCompleted(thesis_id, pm.name, events.MODULE_SKIPPED, None)
                )

    def _produced_kinds(self, worker: _ActiveWorker) -> set[str]:
        produced = set()
        for outcome in worker.outcomes:
            if outcome.status == "ok":
                produced.update(outcome.artefacts.keys())
        return produced

    def _commit_thesis(self, worker: _ActiveWorker, summary: RunSummary) -> None:
        """One transaction per thesis: run rows, metric values, artefact
        moves + references (ADR-0013: main process is the sole writer)."""
        thesis_id = worker.plan.thesis.id
        status_counts = {"ok": 0, "na": 0, "error": 0}
        with self.repo.transaction():
            for outcome in worker.outcomes:
                diagnostics = outcome.diagnostics
                if outcome.stdout:
                    # local-only: diagnostics is registered CONTENT and stripped from
                    # every export (SDD Sec. 8.3.1, ADR-0007), which is what
                    # captured output needs - it can quote thesis text (#68)
                    diagnostics = dict(diagnostics)
                    diagnostics[STDOUT_DIAGNOSTICS_KEY] = outcome.stdout
                run_id = self.repo.record_run(
                    thesis_id,
                    outcome.module_name,
                    outcome.module_version,
                    outcome.status,
                    reason=outcome.reason,
                    error_traceback=outcome.error_traceback,
                    started_at=outcome.started_at,
                    duration_ms=outcome.duration_ms,
                    metrics=outcome.metrics,
                    diagnostics=diagnostics,
                )
                for kind, tmp_path in outcome.artefacts.items():
                    relative = self.store.store(thesis_id, run_id, kind, Path(tmp_path))
                    self.repo.record_artefact(thesis_id, kind, relative, run_id)
                status_counts[outcome.status] += 1
        for outcome in worker.outcomes:
            if outcome.workdir:
                shutil.rmtree(outcome.workdir, ignore_errors=True)
        summary.ok += status_counts["ok"]
        summary.na += status_counts["na"]
        summary.error += status_counts["error"]
        if worker.abandoned:
            summary.theses_abandoned += 1
        else:
            summary.theses_completed += 1
        self.bus.publish(events.ThesisCompleted(thesis_id, status_counts))
