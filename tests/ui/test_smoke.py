"""GUI smoke test — needs a display; skipped headless.

Builds the real MainWindow over a populated project, pumps the Tk event
loop once, exercises mode switch, grid render, and report render.
"""

import os
import tkinter

import pytest

from tta.core.project import Project


def _display_available() -> bool:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        tkinter.Tk().destroy()
        return True
    except tkinter.TclError:
        return False


pytestmark = pytest.mark.skipif(not _display_available(), reason="no display")


@pytest.mark.slow
def test_main_window_builds_and_renders(tmp_path, english_pdf):
    from tta.ui.tk.main_window import MainWindow

    with Project.open(tmp_path / "proj", create=True) as project:
        thesis = project.repo.add_thesis(english_pdf, type="master")
        with project.repo.transaction():
            project.repo.record_run(
                thesis.id, "mod_surface_counts", "0.1.0", "ok", metrics={"word_count": 9000}
            )
            project.repo.record_run(
                thesis.id, "mod_extract_pdf_metadata", "0.1.0", "ok",
                metrics={"creation_year": 2023},
            )

        window = MainWindow(project, first_launch=True)
        try:
            window.root.update_idletasks()
            window.root.update()

            # report button enabled (one ok run exists, ADR-0016)
            assert str(window._toolbar_buttons["📊 Report"]["state"]) == "normal"

            # grid rendered the thesis row
            assert window.grid_view.sheet.get_sheet_data()[0][0] == "english_thesis.pdf"

            # extended mode: more columns appear
            basic_cols = len(window.grid_view.sheet.headers())
            window._extended.set(True)
            window._mode_changed()
            window.root.update_idletasks()
            assert len(window.grid_view.sheet.headers()) > basic_cols

            # report renders without error (matplotlib lazy import)
            window._show_report()
            window.root.update_idletasks()
            assert "1 theses analysed" in window.report_view.cards["text"]
        finally:
            window.root.destroy()
