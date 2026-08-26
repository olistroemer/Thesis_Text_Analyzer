"""Runner: deterministic plan phase + stateful execute phase (ADR-0013).

- ``plan()`` is side-effect-free and returns a ``RunPlan``.
- ``execute()`` spawns one worker process per concurrent thesis; modules
  within a thesis run serially in topological order inside the worker.
- Workers compute in isolation and stream results over a queue; the main
  process is the sole DB writer (one transaction per thesis) and the sole
  event publisher.
- Per-module timeout kills the stuck worker; a worker that dies without
  reporting is detected and fails its thesis the same way; failures cascade
  as ``na`` to dependents and unreachable pairs are reported as ``skipped``
  so adapter progress closes; cancellation is skip-pending.
"""

from __future__ import annotations

import logging
import multiprocessing
import queue as queue_mod
import shutil
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tta.core import events
from tta.core.artefacts import ArtefactStore
from tta.core.db.repository import Repository
from tta.core.modules.base import Module, NotApplicable, RunContext, RunResult
from tta.core.modules.registry import ModuleRegistry
from tta.core.types import Thesis

logger = logging.getLogger(__name__)

DEFAULT_MODULE_TIMEOUT_S = 300.0

#: Wall-clock ceiling for one thesis, measured from its worker's spawn
#: (ADR-0013 "Timeouts", #56). The per-module timeout alone left one document
#: able to burn ``module_timeout x modules attempted`` - up to ~60 min with the
#: 12-module catalogue - and is blind to time spent *between* modules. Derived
#: from ADR-0015: <= 15 s per thesis on the supported tier, ~4x slower on the
#: 2016 dual-core tier (~60 s), so this is ~10x the slowest legitimate figure.
#: Deliberately above DEFAULT_MODULE_TIMEOUT_S so that for a single stuck
#: module the finer-grained guard fires first and names the culprit.
DEFAULT_THESIS_TIMEOUT_S = 600.0

#: How long a worker must be observed dead (``is_alive()`` false) with no
#: ``thesis_done`` before its thesis is failed. A process can exit a few
#: milliseconds before the parent drains the last message its queue feeder
#: flushed, so death is confirmed over consecutive polls rather than on the
#: first sighting (ADR-0013 failure policy, #55).
DEAD_WORKER_GRACE_S = 0.25

#: Seconds to wait for a terminated worker to actually exit before escalating
#: ``terminate()`` (SIGTERM) to ``kill()`` (SIGKILL).
JOIN_TIMEOUT_S = 5.0

# Plan reasons per run mode (SDD Sec. 5.5): default = missing + stale + errored.
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
    theses_skipped: int = 0
    ok: int = 0
    na: int = 0
    error: int = 0
    cancelled: bool = False
    duration_s: float = 0.0


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
    notes: dict = field(default_factory=dict)
    artefacts: dict[str, str] = field(default_factory=dict)  # kind -> tmp path
    workdir: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_one_module(pm: PlannedModule, thesis: Thesis, available: dict[str, str]) -> _ModuleOutcome:
    spec = pm.module.spec
    outcome = _ModuleOutcome(module_name=spec.name, module_version=spec.version, status="ok")
    outcome.started_at = _utc_now_iso()
    t0 = time.perf_counter()
    try:
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
        outcome.notes = result.notes
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


@dataclass
class _ActiveWorker:
    process: multiprocessing.Process
    queue: object
    plan: ThesisPlan
    #: monotonic stamp taken at spawn, for the per-thesis deadline (#56)
    started_monotonic: float = field(default_factory=time.monotonic)
    outcomes: list[_ModuleOutcome] = field(default_factory=list)
    current_module: str | None = None
    module_started_monotonic: float | None = None
    done: bool = False
    #: first poll at which the process was seen dead without a ``thesis_done``
    dead_since: float | None = None


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
        self._cancelled = False

    # -- plan phase (deterministic, side-effect-free) ----------------------

    def plan(
        self,
        theses: list[Thesis] | None = None,
        modules: list[str] | None = None,
        rerun: bool = False,
    ) -> RunPlan:
        if theses is None:
            theses = self.repo.list_theses(local_only=True, include_excluded=False)
        else:
            theses = [t for t in theses if not t.excluded]
        selected = self.registry.in_topological_order(modules)
        latest = self.repo.latest_runs()

        thesis_plans = []
        for thesis in theses:
            planned: dict[str, PlannedModule] = {}
            for module in selected:
                reason = self._needs_run(latest.get((thesis.id, module.spec.name)), module, rerun)
                if reason:
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
            self._close_over_artefacts(thesis, planned)
            if not planned:
                continue
            available = self._preexisting_artefacts(thesis, planned)
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

    def _close_over_artefacts(self, thesis: Thesis, planned: dict[str, PlannedModule]) -> None:
        """Pull in producers of consumed kinds whose artefact is not on
        disk (e.g. deleted artefacts/ directory) - they count as missing."""
        on_disk = self._preexisting_artefacts(thesis, planned={})
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

    def _preexisting_artefacts(self, thesis: Thesis, planned: dict) -> dict[str, str]:
        produced_here = {
            kind for pm in planned.values() for kind in pm.module.spec.produces_artefacts
        }
        available = {}
        for kind, relative in self.repo.current_artefacts(thesis.id).items():
            if kind in produced_here:
                continue  # will be (re)produced fresh in this run
            path = self.store.resolve(relative)
            if path.exists():
                available[kind] = str(path)
        return available

    # -- execute phase (stateful: events + DB writes) -----------------------

    def cancel(self) -> None:
        """Skip-pending: in-flight theses complete; no new ones start."""
        self._cancelled = True

    def _apply_lazy_hashing(self, plan: RunPlan) -> None:
        """Compute + persist ``pdf_sha256`` for each planned thesis whose hash
        is still NULL (deferred from add time, ADR-0006 rev. 4, #38), applying
        content-dedup. Runs in the main process - the sole DB writer (ADR-0013);
        the hash is not needed by workers (modules read ``pdf_path``). A thesis
        folded into a byte-identical sibling is dropped from the plan; a file
        that cannot be read is left un-hashed and still runs (its extractor
        records the per-thesis error)."""
        kept: list[ThesisPlan] = []
        for tp in plan.theses:
            try:
                canonical_id = self.repo.assign_content_hash(tp.thesis)
            except OSError:
                logger.warning(
                    "could not hash thesis %s (%s) - deferring", tp.thesis.id, tp.thesis.pdf_path
                )
                kept.append(tp)
                continue
            if canonical_id == tp.thesis.id:
                tp.thesis = self.repo.get_thesis(canonical_id)  # carry the new hash/path
                kept.append(tp)
            else:
                logger.info(
                    "thesis %s has content identical to %s - folded (ADR-0006 rev. 4)",
                    tp.thesis.id,
                    canonical_id,
                )
        plan.theses = kept

    def execute(self, plan: RunPlan) -> RunSummary:
        t0 = time.monotonic()
        self._cancelled = False
        self._apply_lazy_hashing(plan)
        summary = RunSummary(theses_total=len(plan.theses))
        self.bus.publish(events.RunStarted(plan))

        # 'spawn' start method (#32): the GUI calls execute() on a background
        # thread, and forking a multi-threaded process risks deadlocks (and
        # emits a DeprecationWarning on Linux). spawn is thread-safe and
        # matches the macOS/Windows default. _worker_main is module-level and
        # its args (ThesisPlan with frozen ModuleSpec instances) pickle cleanly.
        ctx = multiprocessing.get_context("spawn")
        pending = list(plan.theses)
        active: list[_ActiveWorker] = []

        while pending or active:
            while pending and len(active) < self.workers and not self._cancelled:
                tp = pending.pop(0)
                queue = ctx.Queue()
                process = ctx.Process(target=_worker_main, args=(tp, queue), daemon=True)
                process.start()
                active.append(_ActiveWorker(process=process, queue=queue, plan=tp))
                self.bus.publish(events.ThesisStarted(tp.thesis.id))
            if self._cancelled and not active:
                break

            for worker in active:
                self._drain_queue(worker)
                if worker.done:
                    continue
                if self._module_timed_out(worker):
                    self._kill_timed_out(worker)
                elif self._thesis_timed_out(worker):
                    self._kill_over_deadline(worker)
                elif self._worker_died(worker):
                    self._reap_dead_worker(worker)
            finished = [w for w in active if w.done]
            active = [w for w in active if not w.done]
            for worker in finished:
                worker.process.join(timeout=5)
                self._commit_thesis(worker, summary)
            if active:
                time.sleep(0.02)

        summary.theses_skipped = len(pending)
        summary.cancelled = self._cancelled and summary.theses_skipped > 0
        summary.duration_s = time.monotonic() - t0
        if summary.cancelled:
            self.bus.publish(
                events.RunCancelled(completed=summary.theses_completed, skipped=summary.theses_skipped)
            )
        else:
            self.bus.publish(events.RunCompleted(summary))
        return summary

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
            reason=f"timeout after {self.module_timeout_s:.0f} s",
            duration_ms=int(self.module_timeout_s * 1000),
        )

    def _terminate(self, worker: _ActiveWorker) -> None:
        """SIGTERM, then SIGKILL if it will not go. Bounded by construction."""
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
                    notes=outcome.notes,
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
        summary.theses_completed += 1
        self.bus.publish(events.ThesisCompleted(thesis_id, status_counts))
