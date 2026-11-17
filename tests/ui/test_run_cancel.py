"""GUI cancel through the real code path (#86): the run on MainWindow's
background thread, cancelled with the window's own Cancel action.

With long-lived workers the run holds idle workers as well as busy ones, so
this checks the end state a user sees and the one they do not: the toolbar is
back, no worker process is left behind, and the database holds exactly what
finished - an abandoned thesis leaves no row and is replanned as missing.

It used to hang in "Planning..." now and then (#89): a cyclic GC pass on the
run thread finalised Tk objects left over from earlier tests' windows, at about
a second each (see ``_finalise_tk_garbage_on_the_main_thread`` in conftest).
The run thread now forces such a pass on every run, and a timeout dumps every
thread's stack, so a recurrence of any hang explains itself.
"""

import gc
import multiprocessing
import sys
import threading
import time
import traceback

import pytest

from tests.core.test_runner_reuse import PidModule, Second
from tests.ui.conftest import display_available
from tta.core.modules.registry import ModuleRegistry
from tta.core.project import Project
from tta.core.runner import Runner

pytestmark = pytest.mark.skipif(not display_available(), reason="no display")


def _state(window) -> str:
    """Everything needed to explain a failure after the fact."""
    thread = window._run_thread
    return (
        f"status={window.status.cget('text')!r} "
        f"theses_done={window._run_theses_done} "
        f"thread_alive={thread is not None and thread.is_alive()} "
        f"children={[p.pid for p in multiprocessing.active_children()]} "
        f"toolbar={sorted(window._toolbar_buttons)}"
    )


def _thread_stacks() -> str:
    """Where every thread is right now - the part a bare timeout cannot say.
    The innermost frames only; the rest is pytest."""
    frames = sys._current_frames()
    return "\n".join(
        f"--- thread {thread.name!r}\n"
        + "".join(traceback.format_stack(frames[thread.ident], limit=12))
        for thread in threading.enumerate()
        if thread.ident in frames
    )


def _pump(window, until, timeout=60.0):
    """Run the window's own event loop until ``until()`` holds.

    mainloop(), as the app does, rather than a loop of update(): only an
    interpreter inside mainloop() serves Tcl calls made from another thread;
    otherwise tkinter waits about a second per call and raises (#89).
    """
    deadline = time.monotonic() + timeout
    outcome: list[BaseException | None] = []

    def check():
        try:
            if until():
                outcome.append(None)
        except BaseException as exc:  # re-raised below, outside the Tk callback
            outcome.append(exc)
        if outcome or time.monotonic() >= deadline:
            window.root.quit()
        else:
            window.root.after(20, check)

    window.root.after(0, check)
    window.root.mainloop()
    if not outcome:
        raise AssertionError(
            f"condition not reached in {timeout} s: {_state(window)}\n{_thread_stacks()}"
        )
    if outcome[0] is not None:
        raise outcome[0]


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

        gc_seconds = []

        def make_runner(repo=None, bus=None, **_):
            # the window's own make_runner call, over fake modules - on the run
            # thread, where a cyclic GC pass may land at any allocation. Force
            # one, so the #89 hazard (Tk garbage finalised off the main thread)
            # is exercised on every run rather than by chance.
            started = time.monotonic()
            gc.collect()
            gc_seconds.append(time.monotonic() - started)
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
            assert gc_seconds[0] < 1.0, f"a GC pass on the run thread took {gc_seconds[0]:.1f} s"
            assert window._run_thread.is_alive(), _state(window)
            assert len(multiprocessing.active_children()) >= 1, _state(window)

            started = time.monotonic()
            window._cancel_run()  # the Cancel button's command
            _pump(window, lambda: not window._run_thread.is_alive())
            _pump(window, lambda: mw.BTN_CANCEL not in window._toolbar_buttons)
            assert time.monotonic() - started < 15, _state(window)  # grace + joins
            assert window.status.cget("text").startswith("Run cancelled"), _state(window)
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
