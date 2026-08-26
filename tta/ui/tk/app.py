"""GUI entry point: auto-open the last project (US-PROF-AUTO-OPEN,
ADR-0014) and keep every write inside it (US-PROF-NO-TRACES).

Which project that is, and what happens when it cannot be opened, is
core's decision - see ``tta.core.project.open_startup_project`` and SDD
Sec. 5.6.1.
"""

from __future__ import annotations

from tta.core.project import open_startup_project
from tta.ui.tk.main_window import MainWindow


def main() -> None:
    # The runner spawns workers (multiprocessing 'spawn', #32); in a frozen
    # --onefile build spawn re-executes this binary, so freeze_support must
    # intercept the worker/tracker sub-process before the GUI starts. No-op
    # when not frozen / not a spawned child (ADR-0014).
    import multiprocessing

    multiprocessing.freeze_support()
    project, first_launch, notice = open_startup_project()
    with project:
        MainWindow(project, first_launch=first_launch, notice=notice).run()


if __name__ == "__main__":
    main()
