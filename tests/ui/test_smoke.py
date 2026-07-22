"""GUI smoke test - needs a display; skipped headless.

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
        thesis = project.repo.add_thesis(english_pdf)
        with project.repo.transaction():
            project.repo.record_run(
                thesis.id, "mod_surface_counts", "0.1.0", "ok", metrics={"word_count": 9000}
            )
            project.repo.record_run(
                thesis.id, "mod_extract_pdf_metadata", "0.1.0", "ok",
                metrics={"creation_year": 2023},
            )
        # a second thesis with a smaller word_count, so a sort by that
        # column has a visible effect on row order (#12)
        second = tmp_path / "shorter_thesis.pdf"
        # distinct bytes so the content-addressed store treats it as a
        # separate thesis (otherwise it dedupes to the first)
        second.write_bytes(english_pdf.read_bytes() + b"\n% second\n")
        second_thesis = project.repo.add_thesis(second)
        with project.repo.transaction():
            project.repo.record_run(
                second_thesis.id, "mod_surface_counts", "0.1.0", "ok",
                metrics={"word_count": 100},
            )

        window = MainWindow(project, first_launch=True)
        try:
            window.root.update_idletasks()
            window.root.update()

            # report button enabled (one ok run exists, ADR-0016)
            assert str(window._toolbar_buttons["Report"]["state"]) == "normal"

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
            assert "2 theses analysed" in window.report_view.cards["text"]

            # #12: a real header click on the word_count column sorts rows.
            # default order is by filename (english_thesis, shorter_thesis);
            # ascending word_count puts the smaller (shorter_thesis) first.
            grid = window.grid_view
            window.notebook.select(grid)
            window.root.update_idletasks()
            headers = grid.sheet.headers()
            col = headers.index("word_count")
            assert grid.sheet.get_sheet_data()[0][0] == "english_thesis.pdf"
            x = grid.sheet.MT.col_positions[col] + 5
            grid.sheet.CH.event_generate("<Button-1>", x=x, y=3)
            grid.sheet.CH.event_generate("<ButtonRelease-1>", x=x, y=3)
            window.root.update_idletasks()
            assert grid._sort_metric == "word_count"
            assert grid.sheet.get_sheet_data()[0][0] == "shorter_thesis.pdf"
            assert grid.sheet.headers()[col] == "word_count (asc)"

            # #40: a repeat click on the same column flips ASC->DESC, so the
            # larger word_count (english_thesis) returns to the top and the
            # header shows the ASCII descending indicator.
            grid.sheet.CH.event_generate("<Button-1>", x=x, y=3)
            grid.sheet.CH.event_generate("<ButtonRelease-1>", x=x, y=3)
            window.root.update_idletasks()
            assert grid._sort_reverse is True
            assert grid.sheet.get_sheet_data()[0][0] == "english_thesis.pdf"
            assert grid.sheet.headers()[col] == "word_count (desc)"

            # #33: while a run is in progress the run buttons are replaced by a
            # single Cancel control; cancelling with no active runner is a
            # no-op, and the normal toolbar returns afterwards.
            window._show_cancel_control()
            window.root.update_idletasks()
            assert "Cancel run" in window._toolbar_buttons
            assert "Run all" not in window._toolbar_buttons
            window._cancel_run()  # _runner is None here: must not raise
            window._render_toolbar()
            window.root.update_idletasks()
            assert "Run all" in window._toolbar_buttons
            assert "Cancel run" not in window._toolbar_buttons
        finally:
            window.root.destroy()
