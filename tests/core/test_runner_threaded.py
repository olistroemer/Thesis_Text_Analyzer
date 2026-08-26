"""Regression for #27: a run on a background thread must use its own
sqlite3 connection (connections are thread-affine), so executing on a
worker thread against a per-thread Repository completes and writes rows."""

import threading

from tta.core import artefact_kinds
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult
from tta.core.modules.registry import ModuleRegistry
from tta.core.project import Project
from tta.core.runner import Runner


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


def test_execute_on_worker_thread_with_thread_local_connection(tmp_path):
    registry = ModuleRegistry([FakeExtract()])
    with Project.open(tmp_path / "proj", create=True) as project:
        pdf = tmp_path / "t1.pdf"
        pdf.write_bytes(b"%PDF-fake t1")
        thesis = project.repo.add_thesis(pdf)

        errors: list[BaseException] = []

        def worker() -> None:
            # mirrors MainWindow._run_worker: fresh connection on this thread
            repo = project.connect()
            try:
                runner = Runner(repo, project.store, registry, workers=1)
                runner.execute(runner.plan())
            except BaseException as exc:  # noqa: BLE001 - surface to assertion
                errors.append(exc)
            finally:
                repo.conn.close()

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=60)

        assert not thread.is_alive()
        assert errors == [], errors

        # rows were written; visible through the main-thread connection
        values = {
            row["metric_name"]: row["value_num"] for row in project.repo.current_metrics()
        }
        assert values["text_chars"] == 120.0
        artefacts = project.repo.current_artefacts(thesis.id)
        assert artefact_kinds.RAW_TEXT in artefacts


def test_project_connections_are_in_wal_mode(tmp_path):
    """WAL is what makes the two-connection story cheap (ADR-0006, #59):
    it takes the rollback-journal fsync out of every commit, and lets this
    background-thread connection read while the main one writes."""
    with Project.open(tmp_path / "proj", create=True) as project:
        assert project.repo.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert project.repo.conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
        repo = project.connect()
        try:
            assert repo.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        finally:
            repo.conn.close()
