"""GUI smoke test - needs a display; skipped headless.

Builds the real MainWindow over a populated project, pumps the Tk event
loop once, exercises mode switch, grid render, report generation, and the
post-run report offer.
"""

import os
import tkinter
import webbrowser
from types import SimpleNamespace

import pytest

from tta.core import events
from tta.core.project import Project
from tta.ui.tk.columns import LEAD_COLUMNS

# The filename lives in the "file" lead column, no longer column 0 (the
# Excluded checkbox is now the first lead column, #11).
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


def _assert_header_binding_installed(grid) -> None:
    """The #12 defect was that a header click never reached a handler at all.

    Asserted structurally rather than by generating a click: the handler is
    resolved from the event's x through `Sheet.identify_column`, so any
    pixel-addressed click depends on the mapped window size and the current
    horizontal scroll - sorting leaves the sheet scrolled to the sorted column.
    That made a real-click assertion fail roughly two runs in three. What
    actually needs guarding is the wiring: a private bindtag ahead of tksheet's
    own (so it fires before tksheet's "break" on a no-change re-click) carrying
    a <Button-1> class binding.
    """
    header = grid.sheet.CH
    tag = f"gridHeaderClick{id(grid)}"
    assert header.bindtags()[0] == tag, "private bindtag must precede tksheet's"
    assert header.bind_class(tag, "<Button-1>"), "no <Button-1> on the private tag"


def _sort_by_column(window, grid, col: int) -> None:
    """Drive the header-click handler for a specific column, deterministically.

    Pixel-addressed clicks cannot do this reliably: the handler resolves the
    column via ``Sheet.identify_column(event)``, which maps an x offset through
    the sheet's layout, and with 31 metric columns the target is normally
    scrolled out of view. Whether any given x hits it depends on the mapped
    window size, so the pixel approach failed about one run in three. The
    binding itself is covered by _real_header_click; here we pin the column and
    exercise the handler's own logic - key resolution, ASC/DESC toggling and
    where the indicator lands."""
    original = grid.sheet.identify_column
    grid.sheet.identify_column = lambda event, allow_end=False: col
    try:
        grid._on_header_click(object())
    finally:
        grid.sheet.identify_column = original
    window.root.update_idletasks()


@pytest.mark.slow
def test_main_window_builds_and_renders(tmp_path, english_pdf, monkeypatch):
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
            # only the second thesis has a detected type, so a sort by the
            # Type lead column has a visible effect on row order (#60)
            project.repo.record_run(
                second_thesis.id, "mod_classify_thesis_type", "0.1.0", "ok",
                metrics={"thesis_type": "master"},
            )

        window = MainWindow(project, first_launch=True)
        try:
            window.root.update_idletasks()
            window.root.update()

            # report button enabled (one ok run exists, ADR-0016)
            assert str(window._toolbar_buttons["Report"]["state"]) == "normal"

            # grid rendered the thesis row
            assert window.grid_view.sheet.get_sheet_data()[0][FILE_COL] == "english_thesis.pdf"

            # extended mode: more columns appear
            basic_cols = len(window.grid_view.sheet.headers())
            window._extended.set(True)
            window._mode_changed()
            window.root.update_idletasks()
            assert len(window.grid_view.sheet.headers()) > basic_cols

            # #51: the Report button writes a stand-alone HTML file and
            # opens it in the browser - there is no Report tab any more.
            opened: list[str] = []
            monkeypatch.setattr(webbrowser, "open", opened.append)
            window._show_report()
            window.root.update_idletasks()
            written = sorted((project.dir / "reports").glob("report-*.html"))
            assert len(written) == 1
            document = written[0].read_text("utf-8")
            assert document.startswith("<!DOCTYPE html>")
            assert "Cohort report" in document
            assert "english_thesis.pdf" not in document  # no PII in a written file
            assert opened == [written[0].as_uri()]
            assert not hasattr(window, "report_view")
            assert not hasattr(window, "notebook")

            # #12: a real header click on the word_count column sorts rows.
            # default order is by filename (english_thesis, shorter_thesis);
            # ascending word_count puts the smaller (shorter_thesis) first.
            grid = window.grid_view
            window.root.update_idletasks()
            headers = grid.sheet.headers()
            col = headers.index("word_count")
            assert grid.sheet.get_sheet_data()[0][FILE_COL] == "english_thesis.pdf"
            _sort_by_column(window, grid, col)
            assert grid._sort_key == "word_count"
            assert grid.sheet.get_sheet_data()[0][FILE_COL] == "shorter_thesis.pdf"
            assert grid.sheet.headers()[col] == "word_count (asc)"

            # #40: a repeat click on the same column flips ASC->DESC, so the
            # larger word_count (english_thesis) returns to the top and the
            # header shows the ASCII descending indicator.
            _sort_by_column(window, grid, col)
            assert grid._sort_reverse is True
            assert grid.sheet.get_sheet_data()[0][FILE_COL] == "english_thesis.pdf"
            assert grid.sheet.headers()[col] == "word_count (desc)"

            # #60: a real click on the Type *lead* column header sorts by the
            # detected type (blank last) and stamps the indicator on that
            # header - it used to silently sort by file name and mark the file
            # header instead.
            type_col = headers.index("type")
            _sort_by_column(window, grid, type_col)
            assert grid._sort_key == "type"
            assert grid._sort_reverse is False
            assert grid.sheet.get_sheet_data()[0][FILE_COL] == "shorter_thesis.pdf"
            assert grid.sheet.headers()[type_col] == "type (asc)"
            assert grid.sheet.headers()[FILE_COL] == "file"  # indicator moved off
            assert grid.sheet.headers()[col] == "word_count"

            # #60: the Excluded lead column sorts too (nothing is excluded here,
            # so the file-name tie-break decides), and a repeat click reverses.
            excluded_col = headers.index("excluded")
            _assert_header_binding_installed(grid)  # the #12 wiring
            for _ in range(2):  # second click reverses (#40)
                _sort_by_column(window, grid, excluded_col)
            assert grid._sort_key == "excluded"
            assert grid._sort_reverse is True
            assert grid.sheet.headers()[excluded_col] == "excluded (desc)"

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

            # #70: a finished run offers the report through a non-modal
            # prompt; "Don't ask again" persists the answer to tta.toml.
            window._maybe_offer_report(events.RunCompleted(SimpleNamespace(ok=3)), False)
            window.root.update_idletasks()
            prompt = window._report_prompt_window
            assert prompt is not None and prompt.winfo_exists()
            assert not prompt.grab_status()  # non-modal
            prompt.destroy()
            window._report_prompt_window = None

            # an all-errored run and a cancelled run stay quiet
            window._maybe_offer_report(events.RunCompleted(SimpleNamespace(ok=0)), False)
            window._maybe_offer_report(events.RunCancelled(1, 2), True)
            assert window._report_prompt_window is None

            # ...and "always" opens it without asking
            window.project.config.open_report_after_run = "always"
            opened.clear()
            window._maybe_offer_report(events.RunCompleted(SimpleNamespace(ok=1)), False)
            assert opened == [written[0].as_uri()]
            assert window._report_prompt_window is None
        finally:
            window.root.destroy()


@pytest.mark.slow
def test_toolbar_add_is_recursive_and_remove_is_wired(tmp_path, english_pdf, monkeypatch):
    """#62: one recursive "Add files" button; the separate "Add folder" is gone.

    #63: "Remove" reaches ``dialogs.remove_thesis_flow``, which shipped with no
    GUI caller at all - only the CLI could forget a mis-added thesis."""
    from tta.ui.tk import dialogs
    from tta.ui.tk.main_window import MainWindow

    with Project.open(tmp_path / "proj", create=True) as project:
        thesis = project.repo.add_thesis(english_pdf)
        calls = []
        monkeypatch.setattr(dialogs, "add_folder_flow", lambda *a: calls.append("folder") or 0)
        monkeypatch.setattr(dialogs, "add_files_flow", lambda *a: calls.append("files") or 0)
        monkeypatch.setattr(
            dialogs,
            "remove_thesis_flow",
            lambda parent, proj, tid: calls.append(("remove", tid)) or False,
        )
        window = MainWindow(project, first_launch=False)
        try:
            window.root.update_idletasks()
            labels = list(window._toolbar_buttons)
            assert "Add files" in labels
            assert "Add folder" not in labels  # collapsed into "Add files"
            assert "Remove" in labels

            # "Add files" must take the recursive folder path, not the file dialog
            window._toolbar_buttons["Add files"].invoke()
            assert calls == ["folder"]

            # Remove acts on the grid selection
            window.grid_view.sheet.select_cell(0, LEAD_COLUMNS.index("file"))
            window._toolbar_buttons["Remove"].invoke()
            assert ("remove", thesis.id) in calls

            # picking individual files survives on the File menu
            window._add_individual_files()
            assert "files" in calls
        finally:
            window.root.destroy()
