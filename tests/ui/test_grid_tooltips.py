"""Grid hover tooltips (Sec. 9.9) surfaced on the real tksheet widget.

Needs a display; skipped headless. Asserts that the reason/hint/header notes
the grid_model carries actually land on the sheet's cell/header options.
"""

import os
import tkinter

import pytest

from tta.ui.tk import grid_model
from tta.ui.tk.columns import MetricColumn, column_help


def _display_available() -> bool:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        tkinter.Tk().destroy()
        return True
    except tkinter.TclError:
        return False


pytestmark = pytest.mark.skipif(not _display_available(), reason="no display")

COLUMNS = [
    MetricColumn("word_count", "mod_surface_counts"),
    MetricColumn("flesch_reading_ease", "mod_readability"),
    MetricColumn("yules_k", "mod_vocabulary"),
    MetricColumn("n_images", "mod_count_images"),  # never ran -> missing
]


def _cell_note(sheet, r, c):
    opts = sheet.MT.cell_options.get((r, c))
    return opts["note"]["note"] if opts and "note" in opts else None


def _header_note(sheet, c):
    opts = sheet.CH.cell_options.get(c)
    return opts["note"]["note"] if opts and "note" in opts else None


@pytest.mark.slow
def test_grid_surfaces_reason_hint_and_header_tooltips(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-a")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        project.repo.record_run(
            thesis.id, "mod_surface_counts", "0.1.0", "ok", metrics={"word_count": 1000}
        )
        project.repo.record_run(
            thesis.id, "mod_readability", "0.1.0", "na", reason="no formula for language: it"
        )
        project.repo.record_run(
            thesis.id, "mod_vocabulary", "0.2.0", "error", reason="ValueError: boom",
            error_traceback="Traceback (most recent call last):\n  ValueError: boom",
        )
        project.repo.record_run(
            thesis.id, "mod_check_extraction_quality", "0.1.0", "ok",
            metrics={"extraction_quality": "garbled"},
        )

    from tta.ui.tk.grid import GridView

    root = tkinter.Tk()
    try:
        grid = GridView(root, project.repo, project.store)
        grid.reload(COLUMNS, show_artefacts=False)
        root.update_idletasks()

        sheet = grid.sheet
        offset = 2  # LEAD_COLUMNS = (file, type)
        col = {c.metric: offset + i for i, c in enumerate(COLUMNS)}

        # na cell surfaces the reason string verbatim
        assert _cell_note(sheet, 0, col["flesch_reading_ease"]) == "no formula for language: it"

        # error cell surfaces the one-line reason AND the folded exception text
        err = _cell_note(sheet, 0, col["yules_k"])
        assert "ValueError: boom" in err and "Traceback" in err

        # not-yet-run cell surfaces the hint
        assert _cell_note(sheet, 0, col["n_images"]) == grid_model.NOT_YET_RUN_HINT

        # ok cell carries no note
        assert _cell_note(sheet, 0, col["word_count"]) is None

        # garbled row explains itself on the leftmost (file) cell
        assert _cell_note(sheet, 0, 0) == grid_model.GARBLED_TOOLTIP

        # column headers explain their metric
        assert _header_note(sheet, col["yules_k"]) == column_help("yules_k")
        assert _header_note(sheet, 0) == column_help("file")
    finally:
        root.destroy()


@pytest.mark.slow
def test_stale_notes_cleared_on_reload(project, tmp_path):
    """A re-render with a shrunk row set must not leave stale hover text."""
    for i in range(2):
        pdf = tmp_path / f"t{i}.pdf"
        pdf.write_bytes(b"%PDF" + str(i).encode())
        thesis = project.repo.add_thesis(pdf)
        with project.repo.transaction():
            project.repo.record_run(
                thesis.id, "mod_readability", "0.1.0", "na", reason=f"reason {i}"
            )

    from tta.ui.tk.grid import GridView

    columns = [MetricColumn("flesch_reading_ease", "mod_readability")]
    root = tkinter.Tk()
    try:
        grid = GridView(root, project.repo, project.store)
        grid.reload(columns, show_artefacts=False)
        root.update_idletasks()
        assert _cell_note(grid.sheet, 1, 2) is not None

        # drop to a single row and re-render; row index 1 must be clear again
        grid.rows = grid.rows[:1]
        grid._render()
        root.update_idletasks()
        assert _cell_note(grid.sheet, 1, 2) is None
    finally:
        root.destroy()
