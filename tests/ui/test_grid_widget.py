"""Grid rendering and interactions on the real tksheet widget (Sec. 9.2/9.9).

Needs a display; skipped headless. Covers the lead-column rendering (#65) and
the details panel that replaced the hover tooltips (#66).
"""

import os
import tkinter

import pytest

from tta.ui.tk import grid_model
from tta.ui.tk.columns import ARTEFACT_COLUMNS, LEAD_COLUMNS, MetricColumn, column_help

LEAD = len(LEAD_COLUMNS)
EXCLUDED_COL = LEAD_COLUMNS.index("excluded")
STATE_COL = LEAD_COLUMNS.index("state")
FILE_COL = LEAD_COLUMNS.index("file")


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


def _seed_four_states(project, tmp_path):
    """One thesis with an ok / na / error / missing cell, flagged garbled."""
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
    return thesis


def _cell_note(sheet, r, c):
    opts = sheet.MT.cell_options.get((r, c))
    return opts["note"]["note"] if opts and "note" in opts else None


def _header_note(sheet, c):
    opts = sheet.CH.cell_options.get(c)
    return opts["note"]["note"] if opts and "note" in opts else None


def _checkbox_kwargs(sheet, c):
    """Column-level checkbox options tksheet registered for column ``c``."""
    return sheet.MT.col_options.get(c, {}).get("checkbox")


def _panel_text(window):
    return window.winfo_children()[0].get("1.0", "end")


def _toplevels(grid):
    # the panel is parented on the GridView frame, so it lands among its children
    return [w for w in grid.winfo_children() if isinstance(w, tkinter.Toplevel)]


def _open_details(grid, r, c):
    """Select a cell, double-click it, and return the Toplevel that opened (or
    None when the cell has nothing to explain)."""
    before = set(_toplevels(grid))
    grid.sheet.select_cell(r, c)
    grid._on_double_click(None)
    opened = [w for w in _toplevels(grid) if w not in before]
    return opened[0] if opened else None


@pytest.mark.slow
def test_grid_has_no_hover_tooltips(project, tmp_path):
    """#66: tksheet's tooltip popup is off and no cell or header note is set -
    the explanations moved to the details panel."""
    _seed_four_states(project, tmp_path)

    from tta.ui.tk.grid import GridView

    root = tkinter.Tk()
    try:
        grid = GridView(root, project.repo, project.store)
        grid.reload(COLUMNS, show_artefacts=True)
        root.update_idletasks()

        sheet = grid.sheet
        assert sheet.ops.tooltips is False
        assert not any("note" in opts for opts in sheet.MT.cell_options.values())
        assert not any("note" in opts for opts in sheet.CH.cell_options.values())
        for c in range(len(grid._column_names())):
            assert _header_note(sheet, c) is None
            assert _cell_note(sheet, 0, c) is None
    finally:
        root.destroy()


@pytest.mark.slow
def test_error_cell_details_panel_carries_the_traceback_in_extended_mode(project, tmp_path):
    """#66 / Sec. 9.9: double-clicking an error cell opens a read-only panel with
    the one-line reason, the column help and - extended mode only - the
    traceback."""
    _seed_four_states(project, tmp_path)

    from tta.ui.tk.grid import GridView

    root = tkinter.Tk()
    try:
        grid = GridView(root, project.repo, project.store)
        grid.reload(COLUMNS, show_artefacts=True)  # extended
        root.update_idletasks()
        err_col = grid._column_names().index("yules_k")

        window = _open_details(grid, 0, err_col)
        assert window is not None
        text = _panel_text(window)
        assert "a.pdf - yules_k" in text  # heading names row and column
        assert column_help("yules_k") in text
        assert "Error: ValueError: boom" in text
        assert "Traceback" in text
        body = window.winfo_children()[0]
        assert str(body["state"]) == "disabled"  # read-only
        window.destroy()

        # basic mode: same panel, reason only, no traceback
        grid.reload(COLUMNS, show_artefacts=False)
        root.update_idletasks()
        err_col = grid._column_names().index("yules_k")
        window = _open_details(grid, 0, err_col)
        text = _panel_text(window)
        assert "Error: ValueError: boom" in text
        assert "Traceback" not in text
    finally:
        root.destroy()


@pytest.mark.slow
def test_na_missing_and_state_cells_explain_themselves_ok_cells_do_not(project, tmp_path):
    """#66: every state that used to have a tooltip has a panel instead - except
    ok cells, which open nothing."""
    _seed_four_states(project, tmp_path)

    from tta.ui.tk.grid import GridView

    root = tkinter.Tk()
    try:
        grid = GridView(root, project.repo, project.store)
        grid.reload(COLUMNS, show_artefacts=False)
        root.update_idletasks()
        names = grid._column_names()

        window = _open_details(grid, 0, names.index("flesch_reading_ease"))
        assert "no formula for language: it" in _panel_text(window)
        window.destroy()

        window = _open_details(grid, 0, names.index("n_images"))
        assert grid_model.NOT_YET_RUN_DETAIL in _panel_text(window)
        window.destroy()

        # the garbled marker in the State column explains the whole row
        window = _open_details(grid, 0, STATE_COL)
        assert grid_model.GARBLED_DETAIL in _panel_text(window)
        window.destroy()

        # an ok cell, the Excluded checkbox and the Type cell open nothing
        assert _open_details(grid, 0, names.index("word_count")) is None
        assert _open_details(grid, 0, EXCLUDED_COL) is None
        assert _open_details(grid, 0, names.index("type")) is None
    finally:
        root.destroy()


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
        assert _checkbox_kwargs(grid.sheet, EXCLUDED_COL)["state"] == "normal"

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
