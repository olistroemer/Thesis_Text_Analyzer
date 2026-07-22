"""Runner tests (ADR-0013): plan modes, execution, cascade, timeout, events."""

import dataclasses
import json
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
from tta.core.runner import Runner

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

    # event sequence
    kinds = [type(e).__name__ for e in seen]
    assert kinds[0] == "RunStarted" and kinds[-1] == "RunCompleted"
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
