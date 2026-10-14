"""GUI cancel through the real code path (#86): the run on MainWindow's
background thread, cancelled with the window's own Cancel action.

With long-lived workers the run holds idle workers as well as busy ones, so
this checks the end state a user sees and the one they do not: the toolbar is
back, no worker process is left behind, and the database holds exactly what
finished - an abandoned thesis leaves no row and is replanned as missing.
"""

import multiprocessing
import time

import pytest

from tests.core.test_runner_reuse import PidModule, Second
from tests.ui.conftest import display_available
from tta.core.modules.registry import ModuleRegistry
from tta.core.project import Project
from tta.core.runner import Runner

pytestmark = pytest.mark.skipif(not display_available(), reason="no display")


def _pump(window, until, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window.root.update()
        if until():
            return
        time.sleep(0.02)
    raise AssertionError("condition not reached in time")


def test_gui_cancel_leaves_no_worker_and_a_consistent_db(tmp_path, monkeypatch):
    from tta.ui.tk import main_window as mw
    from tta.ui.tk.main_window import MainWindow

    registry = ModuleRegistry([PidModule(), Second()])
    with Project.open(tmp_path / "proj", create=True) as project:
        names = ["fast0.pdf", "hang1.pdf", "fast2.pdf", "fast3.pdf"]
        ids = []
        for name in names:
            pdf = tmp_path / name
            pdf.write_bytes(b"%PDF-fake " + name.encode())
            ids.append(project.repo.add_thesis(pdf).id)

        def make_runner(repo=None, bus=None, **_):
            # the window's own make_runner call, over fake modules
            return Runner(
                repo or project.repo, project.store, registry, bus=bus,
                workers=3, cancel_grace_s=0.5,
            )

        monkeypatch.setattr(project, "make_runner", make_runner)
        monkeypatch.setattr(mw.MainWindow, "_maybe_offer_report", lambda *a, **k: None)
        window = MainWindow(project)
        try:
            window._run(rerun=False)
            # the three fast theses complete; hang1 holds its worker
            _pump(window, lambda: window._run_theses_done >= 3)
            assert window._run_thread.is_alive()
            assert len(multiprocessing.active_children()) >= 1

            started = time.monotonic()
            window._cancel_run()  # the Cancel button's command
            _pump(window, lambda: not window._run_thread.is_alive())
            _pump(window, lambda: mw.BTN_CANCEL not in window._toolbar_buttons)
            assert time.monotonic() - started < 15  # grace + join timeouts
            assert window.status.cget("text").startswith("Run cancelled")
        finally:
            window.root.destroy()

        assert multiprocessing.active_children() == []

        latest = project.repo.latest_runs()
        done = {tid for tid, _ in latest}
        assert done == {ids[0], ids[2], ids[3]}
        assert all(row["status"] == "ok" for row in latest.values())
        # the abandoned thesis left no row and is picked up again as missing
        replanned = Runner(project.repo, project.store, registry).plan()
        assert [tp.thesis.id for tp in replanned.theses] == [ids[1]]
        assert {pm.plan_reason for pm in replanned.theses[0].modules} == {"missing"}
