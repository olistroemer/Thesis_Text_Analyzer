"""Runner: deterministic plan phase + stateful execute phase (ADR-0013).

- ``plan()`` is side-effect-free and returns a ``RunPlan``.
- ``execute()`` spawns one worker process per concurrent thesis; modules
  within a thesis run serially in topological order inside the worker.
- Workers compute in isolation and stream results over a queue; the main
  process is the sole DB writer (one transaction per thesis) and the sole
  event publisher.
- Per-module timeout kills the stuck worker; failures cascade as ``na``
  to dependents; cancellation is skip-pending.
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

from pds.core import events
from pds.core.artefacts import ArtefactStore
from pds.core.db.repository import Repository
from pds.core.modules.base import Module, NotApplicable, RunContext, RunResult
from pds.core.modules.registry import ModuleRegistry
from pds.core.types import Thesis

logger = logging.getLogger(__name__)

DEFAULT_MODULE_TIMEOUT_S = 300.0

# Plan reasons per run mode (SDD §5.5): default = missing + stale + errored.
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
        workdir = Path(tempfile.mkdtemp(prefix=f"pds-{thesis.id}-{spec.name}-"))
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

    No DB access, no event publishing (ADR-0013) — results stream back
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
    outcomes: list[_ModuleOutcome] = field(default_factory=list)
    current_module: str | None = None
    module_started_monotonic: float | None = None
    done: bool = False


class Runner:
    def __init__(
        self,
        repo: Repository,
        store: ArtefactStore,
        registry: ModuleRegistry,
        bus: events.EventBus | None = None,
        workers: int | None = None,
        module_timeout_s: float = DEFAULT_MODULE_TIMEOUT_S,
    ):
        self.repo = repo
        self.store = store
        self.registry = registry
        self.bus = bus or events.EventBus()
        self.workers = workers or max(1, (multiprocessing.cpu_count() or 2) - 1)
        self.module_timeout_s = module_timeout_s
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
        disk (e.g. deleted artefacts/ directory) — they count as missing."""
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

    def execute(self, plan: RunPlan) -> RunSummary:
        t0 = time.monotonic()
        self._cancelled = False
        summary = RunSummary(theses_total=len(plan.theses))
        self.bus.publish(events.RunStarted(plan))

        ctx = multiprocessing.get_context()
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
                if not worker.done and self._module_timed_out(worker):
                    self._kill_timed_out(worker)
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

    def _module_timed_out(self, worker: _ActiveWorker) -> bool:
        return (
            worker.module_started_monotonic is not None
            and time.monotonic() - worker.module_started_monotonic > self.module_timeout_s
        )

    def _kill_timed_out(self, worker: _ActiveWorker) -> None:
        timed_out = worker.current_module
        logger.warning(
            "module %s on thesis %s exceeded %.0f s — killing worker",
            timed_out,
            worker.plan.thesis.id,
            self.module_timeout_s,
        )
        worker.process.terminate()
        worker.process.join(timeout=5)
        done_names = {o.module_name for o in worker.outcomes}
        spec = self.registry.get(timed_out).spec
        worker.outcomes.append(
            _ModuleOutcome(
                module_name=timed_out,
                module_version=spec.version,
                status="error",
                reason=f"timeout after {self.module_timeout_s:.0f} s",
                started_at=_utc_now_iso(),
                duration_ms=int(self.module_timeout_s * 1000),
            )
        )
        # remaining modules: dependents of the dead worker's pipeline get an
        # na row; independent ones get no row and stay 'missing' for the
        # next run (SDD §5.5: failures cascade as na to dependents)
        unavailable = set(spec.produces_artefacts)
        for pm in worker.plan.modules:
            if pm.name in done_names or pm.name == timed_out:
                continue
            consumed_missing = [
                k
                for k in pm.module.spec.consumes
                if k in unavailable
                or (k not in worker.plan.artefacts and k not in self._produced_kinds(worker, pm))
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
                self.bus.publish(events.ModuleCompleted(worker.plan.thesis.id, pm.name, "na", 0))
        self.bus.publish(
            events.ModuleCompleted(
                worker.plan.thesis.id, timed_out, "error", int(self.module_timeout_s * 1000)
            )
        )
        worker.done = True

    def _produced_kinds(self, worker: _ActiveWorker, until_pm: PlannedModule) -> set[str]:
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
