"""Grid hover tooltips (Sec. 9.9) surfaced on the real tksheet widget.

Needs a display; skipped headless. Asserts that the reason/hint/header notes
the grid_model carries actually land on the sheet's cell/header options.
"""

import os
import tkinter

import pytest

from tta.ui.tk import grid_model
from tta.ui.tk.columns import LEAD_COLUMNS, MetricColumn, column_help

LEAD = len(LEAD_COLUMNS)
FILE_COL = LEAD_COLUMNS.index("file")
STATE_COL = LEAD_COLUMNS.index("state")


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
        offset = LEAD  # LEAD_COLUMNS = (excluded, state, file, type)
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

        # garbled row explains itself on the State cell, where the marker now
        # lives (#65) - the file cell carries the bare name and no note
        assert _cell_note(sheet, 0, STATE_COL) == grid_model.GARBLED_TOOLTIP
        assert _cell_note(sheet, 0, FILE_COL) is None

        # column headers explain their metric / lead column
        assert _header_note(sheet, col["yules_k"]) == column_help("yules_k")
        assert _header_note(sheet, FILE_COL) == column_help("file")
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
        assert _cell_note(grid.sheet, 1, LEAD) is not None

        # drop to a single row and re-render; row index 1 must be clear again
        grid.rows = grid.rows[:1]
        grid._render()
        root.update_idletasks()
        assert _cell_note(grid.sheet, 1, LEAD) is None
    finally:
        root.destroy()


def _checkbox_kwargs(sheet, c):
    """Column-level checkbox options tksheet registered for column ``c``."""
    return sheet.MT.col_options.get(c, {}).get("checkbox")


@pytest.mark.slow
def test_state_column_carries_the_marker_and_file_cell_the_bare_name(project, tmp_path):
    """#65: the garbled marker lives in its own State column, so the file cell
    is the bare name and file names no longer shift row to row."""
    names = ("garbled.pdf", "clean.pdf")
    for name in names:
        pdf = tmp_path / name
        pdf.write_bytes(b"%PDF-" + name.encode())
        thesis = project.repo.add_thesis(pdf)
        with project.repo.transaction():
            project.repo.record_run(
                thesis.id, "mod_check_extraction_quality", "0.1.0", "ok",
                metrics={"extraction_quality": "garbled" if name == names[0] else "ok"},
            )

    from tta.ui.tk.grid import STATE_GARBLED, GridView

    root = tkinter.Tk()
    try:
        grid = GridView(root, project.repo, project.store)
        grid.reload([MetricColumn("extraction_quality", "mod_check_extraction_quality")],
                    show_artefacts=False)
        root.update_idletasks()
        data = {row[FILE_COL]: row for row in grid.sheet.get_sheet_data()}
        assert set(data) == set(names)  # bare names, no marker prefix
        assert data["garbled.pdf"][STATE_COL] == STATE_GARBLED
        assert data["clean.pdf"][STATE_COL] == ""
    finally:
        root.destroy()


@pytest.mark.slow
def test_artefact_columns_are_read_only_checkboxes(project, tmp_path, monkeypatch):
    """#65: artefact presence renders as a disabled tksheet checkbox over a bool
    cell value - a click cannot fabricate presence, double-click still opens."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-a")
    thesis = project.repo.add_thesis(pdf)
    artefact = project.store.resolve("artefacts/1/raw_text.txt")
    artefact.parent.mkdir(parents=True, exist_ok=True)
    artefact.write_text("text")
    with project.repo.transaction():
        run_id = project.repo.record_run(thesis.id, "mod_extract_text", "0.1.0", "ok")
        project.repo.record_artefact(thesis.id, "raw_text", "artefacts/1/raw_text.txt", run_id)

    from tta.ui.tk import grid as grid_module
    from tta.ui.tk.columns import ARTEFACT_COLUMNS
    from tta.ui.tk.grid import GridView

    opened = []
    monkeypatch.setattr(grid_module, "open_with_default_app", opened.append)

    root = tkinter.Tk()
    try:
        grid = GridView(root, project.repo, project.store)
        grid.reload([], show_artefacts=True)
        root.update_idletasks()

        raw_text_col = LEAD + list(ARTEFACT_COLUMNS).index("raw_text")
        tokens_col = LEAD + list(ARTEFACT_COLUMNS).index("tokens")
        row = grid.sheet.get_sheet_data()[0]
        assert row[raw_text_col] is True  # bool, not the old "[x]" string
        assert row[tokens_col] is False
        for i in range(len(ARTEFACT_COLUMNS)):
            kwargs = _checkbox_kwargs(grid.sheet, LEAD + i)
            assert kwargs is not None and kwargs["state"] == "disabled"
        # the editable Excluded checkbox is untouched by that
        assert _checkbox_kwargs(grid.sheet, LEAD_COLUMNS.index("excluded"))["state"] == "normal"

        # the handler a real click reaches (MainTable.click_checkbox, via
        # open_cell) must not flip a disabled cell. Sheet.click_checkbox is the
        # programmatic setter and deliberately ignores state, so it is not the
        # path under test here.
        grid.sheet.MT.click_checkbox(r=0, c=raw_text_col)
        assert grid.sheet.get_sheet_data()[0][raw_text_col] is True

        # double-click still opens the cached artefact (US-PROF-DOUBLECLICK)
        grid.sheet.select_cell(0, raw_text_col)
        grid._on_double_click(None)
        assert [str(path) for path in opened] == [str(artefact)]
    finally:
        root.destroy()
