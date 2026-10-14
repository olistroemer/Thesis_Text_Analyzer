"""Long-lived, reused workers (ADR-0013 "Worker reuse" / "Recycling", #86).

Fake modules report the pid of the worker that ran them, so reuse and
replacement are visible in the database. Every scenario also checks the
pair-accounting invariant (exactly one ``ModuleCompleted`` per planned pair),
that every worker's queues were closed exactly once, and that no worker
process outlives ``execute()``.
"""

import multiprocessing
import os
import signal
import sqlite3
import time
from pathlib import Path

import pytest

from tta.core import events
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult
from tta.core.modules.registry import ModuleRegistry
from tta.core.runner import Runner, _Slot

# Fake modules at module level: importable in spawned workers. Behaviour is
# keyed on the PDF's file name, so one plan can mix normal and bad theses.


class PidModule(Module):
    """Records the worker pid; sleeps / hangs / dies when the file name says so."""

    spec = ModuleSpec(name="mod_fake_pid", version="1.0.0", produces_metrics=("worker_pid",))

    def run(self, ctx: RunContext) -> RunResult:
        name = Path(ctx.thesis.pdf_path).name
        if "hang" in name:
            time.sleep(60)
        if "die" in name:
            os._exit(7)
        if "slow" in name:
            time.sleep(1.5)
        return RunResult(metrics={"worker_pid": os.getpid()})


class Second(Module):
    """An independent second module, so a kill leaves an unreported pair."""

    spec = ModuleSpec(name="mod_fake_second", version="1.0.0", produces_metrics=("second",))

    def run(self, ctx: RunContext) -> RunResult:
        return RunResult(metrics={"second": 1})


def _add(project, tmp_path, names):
    ids = []
    for name in names:
        pdf = tmp_path / name
        pdf.write_bytes(b"%PDF-fake " + name.encode())
        ids.append(project.repo.add_thesis(pdf).id)
    return ids


class _Harness:
    def __init__(self, project, modules=(PidModule(),), **kwargs):
        self.project = project
        self.events = []
        bus = events.EventBus()
        bus.subscribe_all(self.events.append)
        self.runner = Runner(
            project.repo,
            project.store,
            ModuleRegistry(list(modules)),
            bus=bus,
            workers=kwargs.pop("workers", 1),
            **kwargs,
        )
        self.closed: list[_Slot] = []

    def execute(self, monkeypatch):
        real_close = Runner._close_queues

        def counting_close(slot):
            self.closed.append(slot)
            real_close(slot)

        monkeypatch.setattr(Runner, "_close_queues", staticmethod(counting_close))
        self.plan = self.runner.plan()
        try:
            return self.runner.execute(self.plan)
        finally:
            self.check_no_workers_left()

    def pids(self, thesis_ids):
        by_thesis = {
            r["thesis_id"]: int(r["value_num"])
            for r in self.project.repo.current_metrics()
            if r["metric_name"] == "worker_pid"
        }
        return [by_thesis.get(tid) for tid in thesis_ids]

    def check_pair_accounting(self):
        completed = [e for e in self.events if isinstance(e, events.ModuleCompleted)]
        planned = {(tp.thesis.id, pm.name) for tp in self.plan.theses for pm in tp.modules}
        seen = [(e.thesis_id, e.module_name) for e in completed]
        assert len(seen) == len(set(seen)), "a pair completed twice"
        assert set(seen) == planned, "a planned pair never completed"

    def check_queues_closed(self, summary):
        assert len(self.closed) == summary.workers_spawned
        assert len({id(s) for s in self.closed}) == len(self.closed)

    @staticmethod
    def check_no_workers_left():
        # active_children() joins finished children and lists the live ones
        assert multiprocessing.active_children() == []


def test_one_worker_serves_every_thesis(project, tmp_path, monkeypatch):
    ids = _add(project, tmp_path, [f"t{i}.pdf" for i in range(4)])
    h = _Harness(project, workers=1)
    summary = h.execute(monkeypatch)

    pids = h.pids(ids)
    assert None not in pids and len(set(pids)) == 1
    assert pids[0] != os.getpid()
    assert summary.workers_spawned == 1
    assert summary.ok == 4 and summary.theses_completed == 4
    h.check_pair_accounting()
    h.check_queues_closed(summary)


def test_two_workers_share_the_batch(project, tmp_path, monkeypatch):
    ids = _add(project, tmp_path, [f"t{i}.pdf" for i in range(6)])
    h = _Harness(project, workers=2)
    summary = h.execute(monkeypatch)

    assert summary.workers_spawned == 2
    assert len(set(h.pids(ids))) == 2
    h.check_pair_accounting()
    h.check_queues_closed(summary)


@pytest.mark.parametrize(
    "bad, settings, reason",
    [
        ("hang.pdf", {"module_timeout_s": 1.0}, "timeout"),
        ("hang.pdf", {"thesis_timeout_s": 1.0}, "thesis deadline exceeded"),
        ("die.pdf", {}, "worker died"),
    ],
    ids=["module-timeout", "thesis-deadline", "worker-death"],
)
def test_a_lost_worker_is_replaced_for_the_next_thesis(
    project, tmp_path, monkeypatch, bad, settings, reason
):
    ids = _add(project, tmp_path, ["ok0.pdf", bad, "ok1.pdf", "ok2.pdf"])
    h = _Harness(project, modules=(PidModule(), Second()), workers=1, **settings)
    summary = h.execute(monkeypatch)

    before, failed, after1, after2 = h.pids(ids)
    assert failed is None  # its module never reported
    assert before is not None and after1 is not None
    assert after1 == after2 != before  # one replacement, then reused again
    assert summary.workers_spawned == 2
    row = next(
        v for (tid, name), v in project.repo.latest_runs().items()
        if tid == ids[1] and name == "mod_fake_pid"
    )
    assert row["status"] == "error" and reason in row["reason"]
    h.check_pair_accounting()
    h.check_queues_closed(summary)


def test_thesis_deadline_runs_from_hand_over_not_from_spawn(project, tmp_path, monkeypatch):
    """Three 1.5 s theses on one worker take ~4.5 s plus start-up. A deadline
    measured from the worker's spawn would kill the third; from hand-over each
    thesis has well under its 3.5 s."""
    ids = _add(project, tmp_path, ["slow0.pdf", "slow1.pdf", "slow2.pdf"])
    h = _Harness(project, workers=1, thesis_timeout_s=3.5)
    summary = h.execute(monkeypatch)

    assert summary.error == 0 and summary.ok == 3
    assert len(set(h.pids(ids))) == 1
    h.check_pair_accounting()


def test_a_worker_that_dies_while_idle_is_replaced_silently(project, tmp_path, monkeypatch):
    """Killed between theses it holds no thesis: nothing is recorded against
    any thesis, and the next thesis gets a fresh worker."""
    ids = _add(project, tmp_path, ["t0.pdf", "t1.pdf"])
    h = _Harness(project, workers=1)

    def kill_idle_worker(event):
        if event.thesis_id != ids[0]:
            return
        # ThesisCompleted is published after the worker went back to idle
        (pid,) = h.pids(ids[:1])
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(
            p.pid == pid and p.is_alive() for p in multiprocessing.active_children()
        ):
            time.sleep(0.05)

    h.runner.bus.subscribe(events.ThesisCompleted, kill_idle_worker)
    summary = h.execute(monkeypatch)

    first, second = h.pids(ids)
    assert first != second and second is not None
    assert summary.ok == 2 and summary.error == 0
    assert summary.workers_spawned == 2
    h.check_pair_accounting()
    h.check_queues_closed(summary)


def test_cancel_with_idle_and_in_flight_workers_leaves_no_process(project, tmp_path, monkeypatch):
    """Cancel while one worker idles (its thesis is done) and one holds a
    hanging thesis: the hanging one is abandoned after the grace, pending
    theses are skipped, and both processes are gone afterwards."""
    ids = _add(project, tmp_path, ["fast.pdf", "hang.pdf", "p0.pdf", "p1.pdf"])
    h = _Harness(project, modules=(PidModule(), Second()), workers=2, cancel_grace_s=0.3)
    h.runner.bus.subscribe(
        events.ThesisCompleted,
        lambda e: h.runner.cancel() if e.thesis_id == ids[0] else None,
    )
    started = time.monotonic()
    summary = h.execute(monkeypatch)
    assert time.monotonic() - started < 30

    assert summary.cancelled is True
    assert summary.theses_completed == 1 and summary.theses_abandoned == 1
    assert summary.theses_skipped == 2
    assert summary.workers_spawned == 2
    # the abandoned pair stays missing: no row for the hanging thesis at all
    assert not any(tid == ids[1] for tid, _ in project.repo.latest_runs())
    h.check_queues_closed(summary)


@pytest.mark.parametrize(
    "method, exc_type",
    [
        # a DB failure while committing: one worker idle, one still in flight
        ("_commit_thesis", sqlite3.OperationalError),
        # anything escaping the poll - including a BaseException such as an
        # unhandled Ctrl-C - while both workers hold a thesis
        ("_drain_queue", KeyboardInterrupt),
    ],
    ids=["commit-fails", "poll-interrupted"],
)
def test_an_exception_escaping_execute_leaves_no_process(
    project, tmp_path, monkeypatch, method, exc_type
):
    """No worker process may outlive execute() when it exits through an
    exception (#86): idle ones get the sentinel, in-flight ones are
    terminated, every queue is closed."""
    _add(project, tmp_path, ["t0.pdf", "slow1.pdf", "slow2.pdf", "t3.pdf"])
    h = _Harness(project, workers=2)
    real = getattr(h.runner, method)
    calls = []

    def failing(*args, **kwargs):
        calls.append(args)
        if (method == "_commit_thesis" and len(calls) == 1) or (
            method == "_drain_queue" and len(calls) == 40
        ):
            raise exc_type("injected")
        return real(*args, **kwargs)

    monkeypatch.setattr(h.runner, method, failing)
    with pytest.raises(exc_type, match="injected"):
        h.execute(monkeypatch)  # asserts active_children() == [] on the way out
    assert len(h.closed) == 2  # both workers' queues were closed


def test_recycling_after_n_theses(project, tmp_path, monkeypatch):
    ids = _add(project, tmp_path, [f"t{i}.pdf" for i in range(5)])
    h = _Harness(project, workers=1, recycle_after_theses=2, recycle_above_rss_mb=0)
    summary = h.execute(monkeypatch)

    a, b, c, d, e = h.pids(ids)
    assert a == b != c == d != e and a != e
    assert summary.workers_spawned == 3
    h.check_pair_accounting()
    h.check_queues_closed(summary)


def test_recycling_above_the_rss_limit_uses_the_probe(project, tmp_path, monkeypatch):
    probed = []

    def fat_probe(pid):
        probed.append(pid)
        return 2 * 1024 * 1024 * 1024  # 2 GiB, above the 1024 MiB default

    ids = _add(project, tmp_path, [f"t{i}.pdf" for i in range(3)])
    h = _Harness(project, workers=1, recycle_after_theses=0, rss_probe=fat_probe)
    summary = h.execute(monkeypatch)

    pids = h.pids(ids)
    assert len(set(pids)) == 3 and summary.workers_spawned == 3
    assert probed == pids  # probed once per thesis, on the worker that ran it
    h.check_pair_accounting()
    h.check_queues_closed(summary)


@pytest.mark.parametrize(
    "probe",
    [lambda pid: None, lambda pid: 10 * 1024 * 1024, lambda pid: 1 / 0],
    ids=["unavailable", "below-limit", "raising"],
)
def test_a_quiet_or_broken_probe_keeps_the_worker(project, tmp_path, monkeypatch, probe):
    ids = _add(project, tmp_path, [f"t{i}.pdf" for i in range(3)])
    h = _Harness(project, workers=1, rss_probe=probe)
    summary = h.execute(monkeypatch)

    assert len(set(h.pids(ids))) == 1 and summary.workers_spawned == 1
    assert summary.ok == 3


def test_default_probe_reads_this_process_where_supported():
    """The stdlib probe (Windows ctypes, Linux /proc) reports a plausible
    resident set; elsewhere it reports None rather than failing (#86)."""
    import sys

    from tta.core.procmem import rss_bytes

    value = rss_bytes(os.getpid())
    if sys.platform == "win32" or sys.platform.startswith("linux"):
        assert value is not None and 5 * 1024 * 1024 < value < 8 * 1024**3
    else:
        assert value is None
    assert rss_bytes(-1) is None or sys.platform.startswith("linux")


def test_recycling_settings_come_from_tta_toml(tmp_path):
    from tta.core.config import Config, load_config, save_config
    from tta.core.project import Project
    from tta.core.runner import DEFAULT_RECYCLE_ABOVE_RSS_MB, DEFAULT_RECYCLE_AFTER_THESES

    project_dir = tmp_path / "proj"
    with Project.open(project_dir, create=True) as project:
        runner = project.make_runner()
        assert runner.recycle_after_theses == DEFAULT_RECYCLE_AFTER_THESES == 250
        assert runner.recycle_above_rss_mb == DEFAULT_RECYCLE_ABOVE_RSS_MB == 1024.0

    save_config(project_dir, Config(recycle_after_theses=40, recycle_above_rss_mb=0))
    text = (project_dir / "tta.toml").read_text(encoding="utf-8")
    assert "recycle_after_theses = 40\n" in text  # an integer, not 40.0
    assert load_config(project_dir).recycle_above_rss_mb == 0.0
    with Project.open(project_dir) as project:
        runner = project.make_runner()
        assert runner.recycle_after_theses == 40
        assert runner.recycle_above_rss_mb == 0.0
