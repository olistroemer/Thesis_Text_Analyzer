"""Grid model tests - UI data layer without any Tk (ADR-0002 invariant 6)."""

from tta.ui.tk import grid_model
from tta.ui.tk.columns import (
    ARTEFACT_COLUMNS,
    BASIC_METRICS,
    LEAD_COLUMNS,
    MetricColumn,
    column_help,
    metric_columns,
)
from tta.core.modules.registry import default_registry
from tta.core.types import Thesis


def seed(project, tmp_path):
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
        project.repo.record_run(thesis.id, "mod_vocabulary", "0.2.0", "error", reason="boom")
        project.repo.record_run(
            thesis.id, "mod_check_extraction_quality", "0.1.0", "ok",
            metrics={"extraction_quality": "garbled"},
        )
    return thesis


COLUMNS = [
    MetricColumn("word_count", "mod_surface_counts"),
    MetricColumn("flesch_reading_ease", "mod_readability"),
    MetricColumn("yules_k", "mod_vocabulary"),
    MetricColumn("extraction_quality", "mod_check_extraction_quality"),
    MetricColumn("n_images", "mod_count_images"),  # never ran
]


def test_cell_states_cover_the_four_render_states(project, tmp_path):
    seed(project, tmp_path)
    row = grid_model.load_rows(project.repo, COLUMNS)[0]
    assert row.cells["word_count"].status == "ok"
    assert row.cells["word_count"].display() == "1000"
    assert row.cells["flesch_reading_ease"].status == "na"
    assert row.cells["flesch_reading_ease"].reason == "no formula for language: it"
    assert row.cells["flesch_reading_ease"].display() == ""
    assert row.cells["yules_k"].status == "error"
    assert row.cells["yules_k"].display() == "err"
    assert row.cells["n_images"].status == "missing"
    assert row.garbled is True  # US-PROF-QUALITY row flag


def test_error_cell_carries_reason_and_traceback(project, tmp_path):
    """Sec. 9.9 details panel: the cell keeps the one-line reason and the
    exception text, and cell_details surfaces the traceback in extended mode
    only (#66)."""
    pdf = tmp_path / "e.pdf"
    pdf.write_bytes(b"%PDF-e")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        project.repo.record_run(
            thesis.id, "mod_vocabulary", "0.2.0", "error",
            reason="ValueError: boom",
            error_traceback="Traceback (most recent call last):\n  ValueError: boom",
        )
    columns = [MetricColumn("yules_k", "mod_vocabulary")]
    cell = grid_model.load_rows(project.repo, columns)[0].cells["yules_k"]
    assert cell.status == "error"
    assert cell.reason == "ValueError: boom"
    assert cell.detail is not None and "Traceback" in cell.detail
    extended = grid_model.cell_details(cell, extended=True)
    assert "ValueError: boom" in extended  # one-line reason
    assert "Traceback" in extended  # plus the traceback, extended mode only
    basic = grid_model.cell_details(cell, extended=False)
    assert "ValueError: boom" in basic
    assert "Traceback" not in basic


def test_row_carries_detected_thesis_type(project, tmp_path):
    """The 'type' lead column reads the detected thesis_type metric, not a
    theses column (ADR-0019, #9); blank until the module has run."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-a")
    thesis = project.repo.add_thesis(pdf)
    assert grid_model.load_rows(project.repo, [])[0].thesis_type == ""
    with project.repo.transaction():
        project.repo.record_run(
            thesis.id, "mod_classify_thesis_type", "0.1.0", "ok",
            metrics={"thesis_type": "bachelor"},
        )
    assert grid_model.load_rows(project.repo, [])[0].thesis_type == "bachelor"


def test_cell_details_per_render_state():
    """Sec. 9.9 details-panel body per render state (#66). An 'ok' cell has
    nothing to explain, so double-clicking it opens no panel."""
    Cell = grid_model.Cell
    details = grid_model.cell_details
    assert details(Cell(status="ok", value=1.0), extended=True) is None
    assert details(Cell(status="na", reason="no formula: it"), extended=False) == "no formula: it"
    assert details(Cell(status="na"), extended=False) == "Not applicable for this thesis."
    assert details(Cell(status="missing"), extended=False) == grid_model.NOT_YET_RUN_DETAIL
    assert details(Cell(status="error", reason="boom"), extended=True) == "Error: boom"
    assert details(Cell(status="error"), extended=True) == "Error: module raised an exception"


def test_outlier_bounds_iqr(project, tmp_path):
    rows = []
    for i, value in enumerate([10.0, 11.0, 12.0, 13.0, 100.0]):
        pdf = tmp_path / f"t{i}.pdf"
        pdf.write_bytes(b"%PDF" + str(i).encode())
        thesis = project.repo.add_thesis(pdf)
        with project.repo.transaction():
            project.repo.record_run(
                thesis.id, "mod_surface_counts", "0.1.0", "ok", metrics={"word_count": value}
            )
    columns = [MetricColumn("word_count", "mod_surface_counts")]
    rows = grid_model.load_rows(project.repo, columns)
    bounds = grid_model.outlier_bounds(rows, columns)
    flagged = [
        row.thesis.pdf_filename
        for row in rows
        if grid_model.is_outlier(row.cells["word_count"], bounds.get("word_count"))
    ]
    assert flagged == ["t4.pdf"]  # only the 100.0


def test_sort_rows_numeric_missing_last(project, tmp_path):
    for i, value in enumerate([30.0, None, 10.0]):
        pdf = tmp_path / f"t{i}.pdf"
        pdf.write_bytes(b"%PDF" + str(i).encode())
        thesis = project.repo.add_thesis(pdf)
        if value is not None:
            with project.repo.transaction():
                project.repo.record_run(
                    thesis.id, "mod_surface_counts", "0.1.0", "ok", metrics={"word_count": value}
                )
    columns = [MetricColumn("word_count", "mod_surface_counts")]
    rows = grid_model.sort_rows(grid_model.load_rows(project.repo, columns), "word_count", False)
    assert [r.cells["word_count"].value for r in rows] == [10.0, 30.0, None]


def _three_theses(project, tmp_path):
    """b.pdf (bachelor, excluded, raw_text artefact), a.pdf (master), c.pdf (no run)."""
    theses = {}
    for name in ("b.pdf", "a.pdf", "c.pdf"):
        pdf = tmp_path / name
        pdf.write_bytes(b"%PDF-" + name.encode())
        theses[name] = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        run_id = project.repo.record_run(
            theses["b.pdf"].id, "mod_classify_thesis_type", "0.1.0", "ok",
            metrics={"thesis_type": "bachelor"},
        )
        project.repo.record_run(
            theses["a.pdf"].id, "mod_classify_thesis_type", "0.1.0", "ok",
            metrics={"thesis_type": "master"},
        )
        project.repo.record_artefact(
            theses["b.pdf"].id, "raw_text", "artefacts/1/raw_text.txt", run_id
        )
    project.repo.set_excluded(theses["b.pdf"].id, True)
    return theses


def _names(rows):
    return [r.thesis.pdf_filename for r in rows]


def test_sort_by_file_lead_column(project, tmp_path):
    """#60: the 'file' identity and the default (None) sort agree."""
    _three_theses(project, tmp_path)
    rows = grid_model.load_rows(project.repo, [])
    assert _names(grid_model.sort_rows(rows, "file", False)) == ["a.pdf", "b.pdf", "c.pdf"]
    assert _names(grid_model.sort_rows(rows, "file", True)) == ["c.pdf", "b.pdf", "a.pdf"]
    assert _names(grid_model.sort_rows(rows, None, False)) == ["a.pdf", "b.pdf", "c.pdf"]


def test_sort_by_type_lead_column_blanks_last(project, tmp_path):
    """#60: clicking Type sorts by the detected type, never by file name; the
    not-yet-analysed row stays at the bottom in ascending order (Sec. 9.2)."""
    _three_theses(project, tmp_path)
    rows = grid_model.load_rows(project.repo, [])
    ordered = grid_model.sort_rows(rows, "type", False)
    assert [r.thesis_type for r in ordered] == ["bachelor", "master", ""]
    assert _names(ordered) == ["b.pdf", "a.pdf", "c.pdf"]  # not alphabetical
    assert [r.thesis_type for r in grid_model.sort_rows(rows, "type", True)] == [
        "", "master", "bachelor",
    ]


def test_sort_by_excluded_lead_column(project, tmp_path):
    """#60: clicking Excluded groups the excluded rows, file name as tie-break."""
    _three_theses(project, tmp_path)
    rows = grid_model.load_rows(project.repo, [])
    ordered = grid_model.sort_rows(rows, "excluded", False)
    assert _names(ordered) == ["a.pdf", "c.pdf", "b.pdf"]  # excluded b.pdf last
    assert _names(grid_model.sort_rows(rows, "excluded", True))[0] == "b.pdf"


def test_sort_by_artefact_presence_column(project, tmp_path):
    """#60: an artefact column sorts on presence of that artefact kind."""
    _three_theses(project, tmp_path)
    rows = grid_model.load_rows(project.repo, [])
    ordered = grid_model.sort_rows(rows, "raw_text", True)
    assert _names(ordered)[0] == "b.pdf"  # the only row with a raw_text artefact
    assert "raw_text" in ordered[0].artefacts
    assert _names(grid_model.sort_rows(rows, "raw_text", False))[-1] == "b.pdf"


def test_sort_by_unknown_key_falls_back_to_the_tie_break(project, tmp_path):
    """A key that matches no cell (e.g. a column dropped by a mode switch)
    degrades to 'every value blank' - so the file-name tie-break decides -
    rather than raising a KeyError (#60)."""
    _three_theses(project, tmp_path)
    rows = grid_model.load_rows(project.repo, [])
    assert _names(grid_model.sort_rows(rows, "no_such_metric", False)) == [
        "a.pdf", "b.pdf", "c.pdf",
    ]


def test_sort_by_state_lead_column_groups_garbled_rows(project, tmp_path):
    """#65: the State column sorts on the garbled flag (blank rows first
    ascending), file name as tie-break."""
    for name in ("a.pdf", "b.pdf"):
        pdf = tmp_path / name
        pdf.write_bytes(b"%PDF-" + name.encode())
        thesis = project.repo.add_thesis(pdf)
        if name == "a.pdf":
            with project.repo.transaction():
                project.repo.record_run(
                    thesis.id, "mod_check_extraction_quality", "0.1.0", "ok",
                    metrics={"extraction_quality": "garbled"},
                )
    rows = grid_model.load_rows(project.repo, [])
    assert [r.garbled for r in grid_model.sort_rows(rows, "state", False)] == [False, True]
    assert [r.garbled for r in grid_model.sort_rows(rows, "state", True)] == [True, False]


def test_has_analysis_reflects_presence_of_runs(project, tmp_path):
    """A row carries has_analysis=True when the thesis has any cached run (so
    excluding it must scrub), and False for a never-analysed thesis (#11)."""
    analysed = seed(project, tmp_path)  # four recorded runs
    fresh = tmp_path / "fresh.pdf"
    fresh.write_bytes(b"%PDF-fresh")
    fresh_thesis = project.repo.add_thesis(fresh)  # no runs
    rows = {r.thesis.id: r for r in grid_model.load_rows(project.repo, COLUMNS)}
    assert rows[analysed.id].has_analysis is True
    assert rows[fresh_thesis.id].has_analysis is False


def test_exclude_toggle_needs_confirmation_only_for_analysed_exclude():
    """Confirmation is required only when *excluding* a thesis that has cached
    analysis to scrub; un-excluding or excluding a fresh thesis is silent (#11)."""
    thesis = Thesis(id=1, pdf_sha256=None, pdf_path="/x.pdf", pdf_filename="x.pdf")
    analysed = grid_model.ThesisRow(thesis=thesis, has_analysis=True)
    fresh = grid_model.ThesisRow(thesis=thesis, has_analysis=False)
    assert grid_model.exclude_toggle_needs_confirmation(analysed, True) is True
    assert grid_model.exclude_toggle_needs_confirmation(analysed, False) is False
    assert grid_model.exclude_toggle_needs_confirmation(fresh, True) is False
    assert grid_model.exclude_toggle_needs_confirmation(fresh, False) is False


def test_basic_mode_columns_are_a_curated_subset():
    registry = default_registry()
    basic = metric_columns(registry, extended=False)
    extended = metric_columns(registry, extended=True)
    assert [c.metric for c in basic] == list(BASIC_METRICS)
    assert len(extended) == 34  # all catalogue metrics (ADR-0011 rev. 7: +removed_monospace_chars, +removed_math_chars, #22)
    assert {c.metric for c in basic} < {c.metric for c in extended}


def test_lead_columns_match_the_sdd_column_set():
    """Sec. 9.3 "Column sets": the four lead columns, in order, both modes, each
    with header help (#65)."""
    assert LEAD_COLUMNS == ("excluded", "state", "file", "type")
    assert all(column_help(name) for name in LEAD_COLUMNS)
    assert all(column_help(kind) for kind in ARTEFACT_COLUMNS)


def test_basic_mode_shows_the_publication_year():
    """#65: the professor persona defaults to basic mode, so the project's
    primary research axis (Sec. 2.1) must be a basic-mode column."""
    basic = [c.metric for c in metric_columns(default_registry(), extended=False)]
    assert "publication_year" in basic
    assert basic.index("publication_year") == basic.index("n_pages") + 1
