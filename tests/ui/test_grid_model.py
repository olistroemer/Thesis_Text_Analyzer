"""Grid model tests - UI data layer without any Tk (ADR-0002 invariant 6)."""

from tta.ui.tk import grid_model
from tta.ui.tk.columns import BASIC_METRICS, MetricColumn, metric_columns
from tta.core.modules.registry import default_registry


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
    """Sec. 9.9 folded error tooltip: the cell keeps the one-line reason and
    the exception text, and cell_tooltip surfaces both."""
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
    tip = grid_model.cell_tooltip(cell)
    assert "ValueError: boom" in tip  # one-line reason
    assert "Traceback" in tip  # folded exception text


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


def test_cell_tooltip_per_render_state():
    Cell = grid_model.Cell
    assert grid_model.cell_tooltip(Cell(status="ok", value=1.0)) is None
    assert grid_model.cell_tooltip(Cell(status="na", reason="no formula: it")) == "no formula: it"
    assert grid_model.cell_tooltip(Cell(status="missing")) == grid_model.NOT_YET_RUN_HINT
    err = grid_model.cell_tooltip(Cell(status="error", reason="boom"))
    assert err == "Error: boom"


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


def test_basic_mode_columns_are_a_curated_subset():
    registry = default_registry()
    basic = metric_columns(registry, extended=False)
    extended = metric_columns(registry, extended=True)
    assert [c.metric for c in basic] == list(BASIC_METRICS)
    assert len(extended) == 29  # all catalogue metrics (ADR-0011: +thesis_type, +publication_year, +publication_year_source)
    assert {c.metric for c in basic} < {c.metric for c in extended}
