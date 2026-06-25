"""GUI entry point: auto-open the last project (US-PROF-AUTO-OPEN,
ADR-0014), create the default one on first launch."""

from __future__ import annotations

from tta.core.project import Project
from tta.ui.tk.main_window import MainWindow
from tta.ui.tk.recent import remember_project, resolve_startup_project


def main() -> None:
    project_dir, first_launch = resolve_startup_project()
    with Project.open(project_dir, create=True) as project:
        remember_project(project_dir)
        MainWindow(project, first_launch=first_launch).run()


if __name__ == "__main__":
    main()
