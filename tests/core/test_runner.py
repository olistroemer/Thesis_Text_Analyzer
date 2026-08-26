"""Runner tests (ADR-0013): plan modes, execution, cascade, timeout, events."""

import dataclasses
import json
import logging
import os
import queue
import shutil
import sys
import time

import pytest

from tta.core import artefact_kinds, events
from tta.core.modules.base import (
    Module,
    ModuleSpec,
    NotApplicable,
    RunContext,
    RunResult,
)
from tta.core.modules.registry import ModuleRegistry, default_registry
from tta.core.runner import Runner, _ActiveWorker, _ModuleOutcome

# Fake modules at module level: picklable / importable in worker processes.


class FakeExtract(Module):
    spec = ModuleSpec(
        name="mod_fake_extract",
        version="1.0.0",
        produces_artefacts=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("text_chars",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        out = ctx.workdir / "raw_text.txt"
        out.write_text("hello world " * 10, encoding="utf-8")
        return RunResult(
            metrics={"text_chars": len(out.read_text(encoding="utf-8"))},
            artefacts={artefact_kinds.RAW_TEXT: out},
        )


class FakeQuality(Module):
    spec = ModuleSpec(
        name="mod_fake_quality",
        version="1.0.0",
        consumes=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("extraction_quality",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        return RunResult(metrics={"extraction_quality": "ok" if text else "sparse"})


class FailingExtract(Module):
    spec = ModuleSpec(
        name="mod_fake_extract",
        version="1.0.0",
        produces_artefacts=(artefact_kinds.RAW_TEXT,),
    )

    def run(self, ctx: RunContext) -> RunResult:
        raise RuntimeError("extraction exploded")


class NotApplicableExtract(Module):
    spec = ModuleSpec(
        name="mod_fake_extract",
        version="1.0.0",
        produces_artefacts=(artefact_kinds.RAW_TEXT,),
    )

    def run(self, ctx: RunContext) -> RunResult:
        raise NotApplicable("synthetic na")


class SleepyExtract(Module):
    spec = ModuleSpec(
        name="mod_fake_extract",
        version="1.0.0",
        produces_artefacts=(artefact_kinds.RAW_TEXT,),
    )

    def run(self, ctx: RunContext) -> RunResult:
        time.sleep(30)
        return RunResult()


class Independent(Module):
    """Consumes nothing, so no failure upstream of it can cascade to it - the
    class of module whose pairs used to leak out of progress accounting (#55)."""

    spec = ModuleSpec(
        name="mod_fake_independent",
        version="1.0.0",
        produces_metrics=("independent_flag",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        return RunResult(metrics={"independent_flag": True})


class SuicidalExtract(Module):
    """Dies hard mid-module (no exception, no ``thesis_done``) - stands in for
    an OOM kill or a segfault in the native PDF layer."""

    spec = ModuleSpec(
        name="mod_fake_extract",
        version="1.0.0",
        produces_artefacts=(artefact_kinds.RAW_TEXT,),
    )

    def run(self, ctx: RunContext) -> RunResult:
        os._exit(9)


class SleepyQuality(Module):
    """A dependent module that hangs, so a cancel has an extractor result
    already committed and one module still in flight."""

    spec = ModuleSpec(
        name="mod_fake_quality",
        version="1.0.0",
        consumes=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("extraction_quality",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        time.sleep(30)
        return RunResult(metrics={"extraction_quality": "ok"})


class ChattyExtract(Module):
    """Prints, writes to stderr and logs - the three channels #68 captures."""

    spec = ModuleSpec(
        name="mod_fake_extract",
        version="1.0.0",
        produces_artefacts=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("text_chars",),
    )

    def run(self, ctx: RunContext) -> RunResult:
        print("hello from stdout")
        print("hello from stderr", file=sys.stderr)
        logging.getLogger("tta.core.modules.fake").info("hello from the log")
        out = ctx.workdir / "raw_text.txt"
        out.write_text("x" * 10, encoding="utf-8")
        return RunResult(
            metrics={"text_chars": 10},
            notes={"own_key": 1},
            artefacts={artefact_kinds.RAW_TEXT: out},
        )


class LoudExtract(Module):
    """A runaway loop - its output must not be stored in full."""

    spec = ModuleSpec(name="mod_fake_extract", version="1.0.0")

    def run(self, ctx: RunContext) -> RunResult:
        for i in range(4000):
            print(f"line {i} " + "y" * 40)
        print("LAST LINE")
        return RunResult()


def make_runner(project, modules, **kwargs):
    bus = events.EventBus()
    seen = []
    bus.subscribe_all(seen.append)
    runner = Runner(
        project.repo,
        project.store,
        ModuleRegistry(modules),
        bus=bus,
        workers=kwargs.pop("workers", 1),
        **kwargs,
    )
    return runner, seen


def add_fake_pdf(project, tmp_path, name="t1.pdf"):
    pdf = tmp_path / name
    pdf.write_bytes(b"%PDF-fake " + name.encode())
    return project.repo.add_thesis(pdf)


def test_plan_fresh_db_is_all_missing(project, tmp_path):
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [FakeExtract(), FakeQuality()])
    plan = runner.plan()
    assert plan.pair_count == 2
    assert all(pm.plan_reason == "missing" for tp in plan.theses for pm in tp.modules)


def test_plan_excludes_excluded_theses(project, tmp_path):
    thesis = add_fake_pdf(project, tmp_path)
    project.repo.set_excluded(thesis.id, True)
    runner, _ = make_runner(project, [FakeExtract()])
    assert runner.plan().theses == []


def test_excluded_before_run_caches_no_artefacts(project, tmp_path):
    """Excluding a thesis before any run means its text is never extracted or
    cached at all - plan() skips it, so execute() writes no rows and no files
    (US-PROF-EXCLUDE, QA-PRIV, #11)."""
    thesis = add_fake_pdf(project, tmp_path)
    project.repo.set_excluded(thesis.id, True)
    runner, _ = make_runner(project, [FakeExtract(), FakeQuality()])
    summary = runner.execute(runner.plan())
    assert summary.theses_total == 0 and summary.ok == 0
    assert project.repo.latest_runs() == {}
    assert project.repo.current_artefacts(thesis.id) == {}
    assert not (project.dir / "artefacts" / str(thesis.id)).exists()


def test_execute_happy_path_persists_everything(project, tmp_path):
    thesis = add_fake_pdf(project, tmp_path)
    runner, seen = make_runner(project, [FakeExtract(), FakeQuality()])
    summary = runner.execute(runner.plan())

    assert summary.ok == 2 and summary.error == 0 and summary.na == 0
    assert summary.theses_completed == 1

    # metrics in v_current_metrics
    values = {
        r["metric_name"]: (r["value_num"], r["value_text"])
        for r in project.repo.current_metrics()
    }
    assert values["text_chars"][0] == 120.0
    assert values["extraction_quality"][1] == "ok"

    # artefact moved into the layout and referenced
    artefacts = project.repo.current_artefacts(thesis.id)
    assert set(artefacts) == {artefact_kinds.RAW_TEXT}
    assert project.store.resolve(artefacts[artefact_kinds.RAW_TEXT]).exists()

    # event sequence: the deferred-hash pass reports first, before the plan
    # is final (a folded duplicate would change its pair count), #59
    kinds = [type(e).__name__ for e in seen]
    assert kinds[0] == "HashingProgress"
    assert kinds[kinds.index("RunStarted") - 1] == "HashingProgress"
    assert "HashingProgress" not in kinds[kinds.index("RunStarted"):]
    assert kinds[-1] == "RunCompleted"
    assert kinds.count("ModuleStarted") == 2 and kinds.count("ModuleCompleted") == 2
    assert "ThesisStarted" in kinds and "ThesisCompleted" in kinds


def test_replan_after_success_is_empty_then_stale_on_version_bump(project, tmp_path):
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [FakeExtract()])
    runner.execute(runner.plan())
    assert runner.plan().pair_count == 0  # nothing missing/stale/errored

    bumped = FakeExtract()
    bumped.spec = dataclasses.replace(FakeExtract.spec, version="1.1.0")
    runner2, _ = make_runner(project, [bumped])
    plan = runner2.plan()
    assert plan.pair_count == 1
    assert plan.theses[0].modules[0].plan_reason == "stale"

    # --rerun: everything regardless of state
    assert runner.plan(rerun=True).pair_count == 1


def test_failure_cascades_na_to_dependents_and_is_replanned(project, tmp_path):
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [FailingExtract(), FakeQuality()])
    summary = runner.execute(runner.plan())
    assert summary.error == 1 and summary.na == 1

    latest = project.repo.latest_runs()
    failed = next(v for (_, name), v in latest.items() if name == "mod_fake_extract")
    cascaded = next(v for (_, name), v in latest.items() if name == "mod_fake_quality")
    assert failed["status"] == "error"
    assert "extraction exploded" in failed["reason"]
    assert cascaded["status"] == "na"
    assert "upstream NA cascade" in cascaded["reason"]

    # errored pairs are picked up again by the default plan; the na
    # dependent is also replanned (its last run carries the old version?
    # no - na rows keep their version, but errored upstream re-runs)
    replan = runner.plan()
    planned_names = {pm.name for tp in replan.theses for pm in tp.modules}
    assert "mod_fake_extract" in planned_names


def test_not_applicable_records_na_with_reason(project, tmp_path):
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [NotApplicableExtract()])
    summary = runner.execute(runner.plan())
    assert summary.na == 1
    latest = project.repo.latest_runs()
    row = next(iter(latest.values()))
    assert row["status"] == "na" and row["reason"] == "synthetic na"


def test_module_timeout_kills_worker_and_cascades(project, tmp_path):
    add_fake_pdf(project, tmp_path)
    runner, seen = make_runner(
        project, [SleepyExtract(), FakeQuality()], module_timeout_s=1.0
    )
    summary = runner.execute(runner.plan())
    assert summary.error == 1 and summary.na == 1

    latest = project.repo.latest_runs()
    timed_out = next(v for (_, name), v in latest.items() if name == "mod_fake_extract")
    assert timed_out["status"] == "error"
    assert "timeout" in timed_out["reason"]
    cascaded = next(v for (_, name), v in latest.items() if name == "mod_fake_quality")
    assert cascaded["status"] == "na"


def test_cancel_is_skip_pending_and_reports_cancelled(project, tmp_path):
    """cancel() stops new theses from starting; the in-flight one finishes
    and the rest are skipped, with a RunCancelled event (ADR-0013)."""
    for i in range(3):
        add_fake_pdf(project, tmp_path, name=f"t{i}.pdf")
    runner, seen = make_runner(project, [FakeExtract()], workers=1)

    # Cancel the moment the first thesis starts: with a single worker no
    # other thesis is in flight, so exactly one completes and two are skipped.
    started: list[int] = []

    def _on_start(evt):
        started.append(evt.thesis_id)
        if len(started) == 1:
            runner.cancel()

    runner.bus.subscribe(events.ThesisStarted, _on_start)

    summary = runner.execute(runner.plan())

    assert summary.cancelled is True
    assert summary.theses_completed == 1
    assert summary.theses_skipped == 2
    assert summary.ok == 1

    kinds = [type(e).__name__ for e in seen]
    assert kinds[-1] == "RunCancelled"
    assert "RunCompleted" not in kinds
    cancelled_evt = seen[-1]
    assert cancelled_evt.completed == 1 and cancelled_evt.skipped == 2

    # skip-pending, not abort: the one thesis that ran persisted its row
    assert len(project.repo.latest_runs()) == 1


def test_multiple_theses_parallel_workers(project, tmp_path):
    for i in range(3):
        add_fake_pdf(project, tmp_path, name=f"t{i}.pdf")
    runner, _ = make_runner(project, [FakeExtract(), FakeQuality()], workers=2)
    summary = runner.execute(runner.plan())
    assert summary.theses_completed == 3
    assert summary.ok == 6


@pytest.mark.slow
def test_full_default_pipeline_end_to_end(project, english_pdf):
    """All catalogue modules over a real PDF, through the real runner."""
    thesis = project.repo.add_thesis(english_pdf)
    runner = Runner(project.repo, project.store, default_registry(), workers=1)
    summary = runner.execute(runner.plan())

    assert summary.error == 0
    latest = project.repo.latest_runs()
    statuses = {name: row["status"] for (_, name), row in latest.items()}
    assert len(statuses) == 12  # ADR-0011 (+mod_classify_thesis_type #9, +mod_determine_publication_year #17)
    assert all(s == "ok" for s in statuses.values()), statuses

    values = {
        r["metric_name"]: (r["value_num"], r["value_text"])
        for r in project.repo.current_metrics()
    }
    assert values["language_code"][1] == "en"
    assert values["extraction_quality"][1] == "ok"
    # english prose, no degree keyword on the "title page" -> unspecified (#9)
    assert values["thesis_type"][1] == "unspecified"
    # publication year fused; source is a PDF-metadata date or none (#17)
    assert values["publication_year_source"][1] in {
        "title_page", "pdf_creation", "pdf_modification", "none"
    }

    # lazy hash was computed and persisted at run time (#38, ADR-0006 rev. 4)
    assert project.repo.get_thesis(thesis.id).pdf_sha256 is not None

    # module diagnostics travel from worker to DB, local-only (Sec. 8.3.1)
    quality_notes = project.conn.execute(
        "SELECT notes FROM module_runs WHERE module_name = 'mod_check_extraction_quality'"
    ).fetchone()["notes"]
    assert json.loads(quality_notes)["stop_word_ratio"] > 0.149
    assert values["word_count"][0] > 300
    assert values["producer_category"][1] == "latex"
    assert 0 < values["flesch_reading_ease"][0] < 121

    # all four artefact kinds cached on disk
    artefacts = project.repo.current_artefacts(thesis.id)
    assert set(artefacts) == artefact_kinds.ALL_KINDS
    for relative in artefacts.values():
        assert project.store.resolve(relative).exists()

    # pause/resume property: a second default run has nothing to do
    assert runner.plan().pair_count == 0


def test_worker_death_fails_the_thesis_instead_of_hanging(project, tmp_path):
    """A worker that dies without reporting has no timeout signal to trip (no
    module start stamp survives it), so before #55 the poll loop spun forever.
    It must now be detected, recorded as an error, and the run must finish."""
    add_fake_pdf(project, tmp_path)
    runner, seen = make_runner(project, [SuicidalExtract(), FakeQuality()])
    started = time.monotonic()
    summary = runner.execute(runner.plan())
    assert time.monotonic() - started < 30  # not hung

    assert summary.error == 1 and summary.na == 1 and summary.ok == 0
    latest = project.repo.latest_runs()
    died = next(v for (_, name), v in latest.items() if name == "mod_fake_extract")
    assert died["status"] == "error"
    assert "worker died" in died["reason"]
    cascaded = next(v for (_, name), v in latest.items() if name == "mod_fake_quality")
    assert cascaded["status"] == "na"

    # an errored pair is replanned by the default mode
    assert "mod_fake_extract" in {pm.name for tp in runner.plan().theses for pm in tp.modules}
    assert [type(e).__name__ for e in seen][-1] == "RunCompleted"


def test_timeout_reports_skipped_pairs_so_progress_can_close(project, tmp_path):
    """After a kill, every planned pair must still get exactly one
    ModuleCompleted - otherwise the determinate bar stops short of 100 % and
    the ETA never clears (#55, #39). The independent module gets no DB row, so
    it stays 'missing' and the next default run picks it up."""
    add_fake_pdf(project, tmp_path)
    runner, seen = make_runner(
        project, [SleepyExtract(), Independent(), FakeQuality()], module_timeout_s=1.0
    )
    plan = runner.plan()
    assert [pm.name for pm in plan.theses[0].modules] == [
        "mod_fake_extract",
        "mod_fake_independent",
        "mod_fake_quality",
    ]
    summary = runner.execute(plan)

    completed = [e for e in seen if isinstance(e, events.ModuleCompleted)]
    assert len(completed) == plan.pair_count == 3
    assert len({(e.thesis_id, e.module_name) for e in completed}) == 3
    by_name = {e.module_name: e for e in completed}
    assert by_name["mod_fake_extract"].status == "error"
    assert by_name["mod_fake_quality"].status == "na"  # dependent: real cascade
    assert by_name["mod_fake_independent"].status == events.MODULE_SKIPPED
    assert by_name["mod_fake_independent"].duration_ms is None

    # the skipped pair invents no history and is replanned as missing
    assert summary.error == 1 and summary.na == 1
    latest = project.repo.latest_runs()
    assert not any(name == "mod_fake_independent" for _, name in latest)
    replanned = {
        pm.name: pm.plan_reason for tp in runner.plan().theses for pm in tp.modules
    }
    assert replanned["mod_fake_independent"] == "missing"


class _StubProcess:
    """Stands in for a worker process so the kill path can be exercised
    deterministically (the real race is a few microseconds wide)."""

    exitcode = None

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def is_alive(self) -> bool:
        return not (self.terminated or self.killed)

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def join(self, timeout=None) -> None:
        pass


def test_late_module_done_is_drained_before_the_kill(project, tmp_path):
    """A module_done written between the poll loop's drain and the terminate()
    used to be lost, recording a module that had in fact succeeded as never
    having run (#55 defect 3). _kill_timed_out drains once more first, sees the
    result, and must then not kill anything."""
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [FakeExtract(), FakeQuality()], module_timeout_s=0.5)
    plan = runner.plan()

    process = _StubProcess()
    pipe = queue.SimpleQueue()  # get_nowait() raises queue.Empty, as mp.Queue does
    worker = _ActiveWorker(process=process, queue=pipe, plan=plan.theses[0])
    worker.current_module = "mod_fake_extract"
    worker.module_started_monotonic = time.monotonic() - 10  # long past the timeout
    pipe.put((
        "module_done",
        _ModuleOutcome(module_name="mod_fake_extract", module_version="1.0.0", status="ok"),
    ))

    assert runner._module_timed_out(worker)
    runner._kill_timed_out(worker)

    assert not process.terminated and not process.killed
    assert [(o.module_name, o.status) for o in worker.outcomes] == [("mod_fake_extract", "ok")]
    assert not worker.done  # still in flight, on its next module


def test_thesis_deadline_kills_what_the_module_guard_cannot_see(project, tmp_path):
    """The per-thesis wall-clock deadline (#56). With a module timeout far above
    the module's own runtime the module guard never fires, so before the
    deadline existed one document could burn timeout x modules attempted."""
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(
        project,
        [SleepyExtract(), FakeQuality()],
        module_timeout_s=300.0,
        thesis_timeout_s=0.5,
    )
    started = time.monotonic()
    summary = runner.execute(runner.plan())
    assert time.monotonic() - started < 30

    assert summary.error == 1 and summary.na == 1
    latest = project.repo.latest_runs()
    killed = next(v for (_, name), v in latest.items() if name == "mod_fake_extract")
    assert killed["status"] == "error"
    assert "thesis deadline exceeded" in killed["reason"]


def test_timeouts_are_configurable_from_tta_toml(tmp_path):
    """Both timeouts must be reachable from the app, not only from tests: the
    300 s was hardcoded because make_runner never passed it and Config had no
    key for it (#56)."""
    from tta.core.config import Config, save_config
    from tta.core.project import Project
    from tta.core.runner import (
        DEFAULT_CANCEL_GRACE_S,
        DEFAULT_MODULE_TIMEOUT_S,
        DEFAULT_THESIS_TIMEOUT_S,
    )

    project_dir = tmp_path / "proj"
    with Project.open(project_dir, create=True) as project:
        runner = project.make_runner()
        assert runner.module_timeout_s == DEFAULT_MODULE_TIMEOUT_S
        assert runner.thesis_timeout_s == DEFAULT_THESIS_TIMEOUT_S
        assert runner.cancel_grace_s == DEFAULT_CANCEL_GRACE_S

    save_config(
        project_dir,
        Config(module_timeout_s=12.5, thesis_timeout_s=99.0, cancel_grace_s=0.25),
    )
    with Project.open(project_dir) as project:
        assert project.config.module_timeout_s == 12.5
        assert project.config.thesis_timeout_s == 99.0
        assert project.config.cancel_grace_s == 0.25
        runner = project.make_runner()
        assert runner.module_timeout_s == 12.5
        assert runner.thesis_timeout_s == 99.0
        assert runner.cancel_grace_s == 0.25


def test_cancel_does_not_wait_for_an_in_flight_thesis(project, tmp_path):
    """Bounded-grace cancel (#57). cancel() used only to stop *scheduling*, so
    the user waited up to a full thesis per worker - here 30 s of module sleep.
    Control must come back within the grace plus the join timeouts instead."""
    for i in range(2):
        add_fake_pdf(project, tmp_path, name=f"t{i}.pdf")
    runner, seen = make_runner(
        project, [SleepyExtract()], workers=1, cancel_grace_s=0.3
    )
    runner.bus.subscribe(events.ThesisStarted, lambda evt: runner.cancel())

    started = time.monotonic()
    summary = runner.execute(runner.plan())
    elapsed = time.monotonic() - started
    assert elapsed < 15, elapsed  # nowhere near the module's 30 s sleep

    assert summary.cancelled is True
    assert summary.theses_abandoned == 1
    assert summary.theses_skipped == 1
    assert summary.theses_completed == 0
    cancelled_evt = seen[-1]
    assert type(cancelled_evt).__name__ == "RunCancelled"
    assert cancelled_evt.abandoned == 1 and cancelled_evt.skipped == 1

    # progress terminates: the abandoned pair is reported, not left dangling
    completed = [e for e in seen if isinstance(e, events.ModuleCompleted)]
    assert [(e.module_name, e.status) for e in completed] == [
        ("mod_fake_extract", events.MODULE_SKIPPED)
    ]

    # ...but nothing was written, so pause/resume picks the work up cleanly
    # (ADR-0015) rather than resuming against invented failures
    assert project.repo.latest_runs() == {}
    replanned = {pm.plan_reason for tp in runner.plan().theses for pm in tp.modules}
    assert replanned == {"missing"}


def test_cancel_commits_what_the_abandoned_worker_already_reported(project, tmp_path):
    """Partial results survive the terminate: the extractor finished and is
    committed, the module still in flight leaves no row at all (#57)."""
    add_fake_pdf(project, tmp_path)
    runner, seen = make_runner(
        project, [FakeExtract(), SleepyQuality()], workers=1, cancel_grace_s=0.5
    )
    runner.bus.subscribe(events.ThesisStarted, lambda evt: runner.cancel())

    summary = runner.execute(runner.plan())

    assert summary.cancelled is True and summary.theses_abandoned == 1
    assert summary.ok == 1
    statuses = {name: row["status"] for (_, name), row in project.repo.latest_runs().items()}
    assert statuses == {"mod_fake_extract": "ok"}
    # the committed module's artefact is in the store, usable by the resumed run
    artefacts = project.repo.current_artefacts(1)
    assert artefact_kinds.RAW_TEXT in artefacts
    assert project.store.resolve(artefacts[artefact_kinds.RAW_TEXT]).exists()

    by_name = {
        e.module_name: e.status for e in seen if isinstance(e, events.ModuleCompleted)
    }
    assert by_name == {"mod_fake_extract": "ok", "mod_fake_quality": events.MODULE_SKIPPED}


def test_batched_hashing_folds_duplicates_and_reports_progress(project, tmp_path):
    """The batched hashing pass (#59) must keep ADR-0006's semantics: two paths
    with byte-identical content fold to one canonical thesis, the surviving
    Thesis carries the freshly computed hash without a get_thesis re-read, and
    the phase reports itself instead of hiding inside "Planning..."."""
    payload = b"%PDF-fake identical bytes"
    for name in ("a.pdf", "b.pdf"):
        path = tmp_path / name
        path.write_bytes(payload)
        project.repo.add_thesis(path)
    runner, seen = make_runner(project, [FakeExtract()])
    plan = runner.plan()
    assert plan.pair_count == 2  # both planned; the fold happens in execute()
    summary = runner.execute(plan)

    assert summary.theses_total == 1  # one folded away
    assert summary.ok == 1
    survivors = project.repo.list_theses()
    assert len(survivors) == 1
    assert survivors[0].pdf_sha256 is not None
    assert survivors[0].pdf_filename == "b.pdf"  # canonical adopts the last path

    # the plan's own Thesis object was updated in place - no get_thesis round-trip
    assert plan.theses[0].thesis.pdf_sha256 == survivors[0].pdf_sha256

    hashing = [e for e in seen if isinstance(e, events.HashingProgress)]
    assert [(e.done, e.total) for e in hashing] == [(0, 2), (1, 2), (2, 2), (2, 2)]


def test_second_run_hashes_nothing(project, tmp_path):
    """Already-hashed theses cost no digest and no event (#59)."""
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [FakeExtract()])
    runner.execute(runner.plan())

    runner2, seen = make_runner(project, [FakeExtract()])
    runner2.execute(runner2.plan(rerun=True))
    assert [e for e in seen if isinstance(e, events.HashingProgress)] == []


def test_plan_queries_artefacts_once_for_the_whole_corpus(project, tmp_path):
    """plan() used to run 1-2 identical per-thesis artefact queries, each
    followed by a resolve()+exists() per row - O(n) round-trips to plan (#59)."""
    for i in range(5):
        add_fake_pdf(project, tmp_path, name=f"t{i}.pdf")
    runner, _ = make_runner(project, [FakeExtract(), FakeQuality()])

    statements: list[str] = []
    project.conn.set_trace_callback(statements.append)
    try:
        plan = runner.plan()
    finally:
        project.conn.set_trace_callback(None)

    assert plan.pair_count == 10
    artefact_queries = [q for q in statements if "artefact_files" in q]
    assert len(artefact_queries) == 1, artefact_queries
    assert "thesis_id = ?" not in artefact_queries[0]


def test_up_to_date_plan_stats_no_artefacts(project, tmp_path):
    """The `if not planned: continue` guard now sits above the artefact work,
    so a fully up-to-date project pays no query and no stat per thesis (#59)."""
    for i in range(3):
        add_fake_pdf(project, tmp_path, name=f"t{i}.pdf")
    runner, _ = make_runner(project, [FakeExtract(), FakeQuality()])
    runner.execute(runner.plan())

    stat_calls: list[dict] = []
    original = runner._existing_artefacts

    def _spy(rows):
        stat_calls.append(rows)
        return original(rows)

    runner._existing_artefacts = _spy
    assert runner.plan().pair_count == 0
    assert stat_calls == []

    # ...but a thesis that does have work still gets its artefact set
    bumped = FakeQuality()
    bumped.spec = dataclasses.replace(FakeQuality.spec, version="1.1.0")
    runner2, _ = make_runner(project, [FakeExtract(), bumped])
    assert runner2.plan().pair_count == 3  # stale quality on 3 theses


def _notes_of(project, module_name: str) -> dict:
    row = project.conn.execute(
        "SELECT notes FROM module_runs WHERE module_name = ?", (module_name,)
    ).fetchone()
    return json.loads(row["notes"])


def test_module_output_is_captured_into_the_run_record(project, tmp_path):
    """print(), stderr and log records all land against that (thesis, module)
    run instead of on the parent's terminal unlabelled - or, in the frozen GUI
    with no console, nowhere at all (#68)."""
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [ChattyExtract()])
    assert runner.execute(runner.plan()).ok == 1

    notes = _notes_of(project, "mod_fake_extract")
    captured = notes["_stdout"]
    assert "hello from stdout" in captured
    assert "hello from stderr" in captured
    assert "hello from the log" in captured  # root logger has no handler otherwise
    assert "INFO tta.core.modules.fake" in captured  # attributed, not bare text
    assert notes["own_key"] == 1  # the module's own diagnostics are untouched


def test_captured_output_is_tail_truncated(project, tmp_path):
    """A runaway loop must not bloat the DB; the tail is what is kept, because
    that is where a traceback or the last thing before a hang lives (#68)."""
    from tta.core.runner import STDOUT_CAPTURE_CHARS

    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [LoudExtract()])
    runner.execute(runner.plan())

    captured = _notes_of(project, "mod_fake_extract")["_stdout"]
    assert "characters truncated" in captured
    assert len(captured) < STDOUT_CAPTURE_CHARS + 200
    assert captured.rstrip().endswith("LAST LINE")
    assert "line 0 " not in captured  # the head went, not the tail


def test_silent_modules_add_no_stdout_key(project, tmp_path):
    """No capture, no key: existing notes payloads are unchanged (#68)."""
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [FakeExtract()])
    runner.execute(runner.plan())
    row = project.conn.execute(
        "SELECT notes FROM module_runs WHERE module_name = 'mod_fake_extract'"
    ).fetchone()
    assert row["notes"] is None


def test_stale_only_skips_never_run_pairs(project, tmp_path):
    """"Update stale" is a distinct third mode (#7): stale + errored +
    upstream-changed, but never a never-run pair."""
    analysed = add_fake_pdf(project, tmp_path, name="old.pdf")
    runner, _ = make_runner(project, [FakeExtract(), FakeQuality()])
    runner.execute(runner.plan())

    add_fake_pdf(project, tmp_path, name="new.pdf")  # never run
    bumped = FakeQuality()
    bumped.spec = dataclasses.replace(FakeQuality.spec, version="1.1.0")
    runner2, _ = make_runner(project, [FakeExtract(), bumped])

    # the default mode takes both: 2 pairs for the new thesis + the stale one
    assert runner2.plan().pair_count == 3

    stale = runner2.plan(stale_only=True)
    assert [tp.thesis.id for tp in stale.theses] == [analysed.id]
    assert [(pm.name, pm.plan_reason) for pm in stale.theses[0].modules] == [
        ("mod_fake_quality", "stale")
    ]
    # and it is genuinely different from --rerun
    assert runner2.plan(rerun=True).pair_count == 4


def test_stale_only_keeps_upstream_changed_and_the_artefact_closure(project, tmp_path):
    """Two properties of *where* the filter sits (#7): a consumer of a
    re-planned producer still comes along, and a producer pulled in because its
    cached artefact is gone still runs - filtering it out would plan the stale
    module only for it to fail as an na upstream cascade."""
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [FakeExtract(), FakeQuality()])
    runner.execute(runner.plan())

    # a stale producer drags its consumer in as upstream-changed
    bumped = FakeExtract()
    bumped.spec = dataclasses.replace(FakeExtract.spec, version="1.1.0")
    runner2, _ = make_runner(project, [bumped, FakeQuality()])
    reasons = {
        pm.name: pm.plan_reason
        for tp in runner2.plan(stale_only=True).theses
        for pm in tp.modules
    }
    assert reasons == {"mod_fake_extract": "stale", "mod_fake_quality": "upstream-changed"}

    # now delete the cached artefact: the producer is 'missing' but required,
    # so the closure must still pull it in under stale_only
    shutil.rmtree(project.dir / "artefacts")
    bumped_quality = FakeQuality()
    bumped_quality.spec = dataclasses.replace(FakeQuality.spec, version="1.1.0")
    runner3, _ = make_runner(project, [FakeExtract(), bumped_quality])
    reasons = {
        pm.name: pm.plan_reason
        for tp in runner3.plan(stale_only=True).theses
        for pm in tp.modules
    }
    assert reasons == {"mod_fake_extract": "missing", "mod_fake_quality": "stale"}
    summary = runner3.execute(runner3.plan(stale_only=True))
    assert summary.ok == 2 and summary.na == 0  # no cascade: the input was rebuilt


def test_rerun_and_stale_only_together_are_rejected(project, tmp_path):
    add_fake_pdf(project, tmp_path)
    runner, _ = make_runner(project, [FakeExtract()])
    with pytest.raises(ValueError):
        runner.plan(rerun=True, stale_only=True)


def test_hashing_folds_into_a_sibling_hashed_by_an_earlier_run(project, tmp_path):
    """The realistic dedup case: the same file re-added under a new name after
    the first run already hashed the original. Nothing to UPDATE, one fold."""
    payload = b"%PDF-fake stable bytes"
    first = tmp_path / "original.pdf"
    first.write_bytes(payload)
    original = project.repo.add_thesis(first)
    runner, _ = make_runner(project, [FakeExtract()])
    runner.execute(runner.plan())
    assert project.repo.get_thesis(original.id).pdf_sha256 is not None

    copy = tmp_path / "renamed.pdf"
    copy.write_bytes(payload)
    duplicate = project.repo.add_thesis(copy)
    runner2, _ = make_runner(project, [FakeExtract()])
    summary = runner2.execute(runner2.plan())

    assert summary.theses_total == 0  # the only planned thesis folded away
    assert [t.id for t in project.repo.list_theses()] == [original.id]
    assert project.repo.get_thesis(original.id).pdf_filename == "renamed.pdf"
    with pytest.raises(KeyError):
        project.repo.get_thesis(duplicate.id)
