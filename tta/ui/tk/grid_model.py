"""Pure data model behind the grid - no Tk imports, unit-testable.

Maps repository state to per-cell render states (Sec. 9.9: ok / na / error /
not-yet-run), computes IQR outlier bounds (Sec. 9.5), and sorts rows.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from tta.core.db.repository import Repository
from tta.core.types import Thesis
from tta.ui.tk.columns import ARTEFACT_COLUMNS, MetricColumn

OK, NA, ERROR, MISSING = "ok", "na", "error", "missing"

# Sec. 9.9 tooltip copy (ASCII only, ADR-0018).
NOT_YET_RUN_HINT = "Not yet analysed - click Run to compute."
GARBLED_TOOLTIP = (
    "Text extraction was flagged as garbled for this thesis; every metric in "
    "this row may be unreliable (US-PROF-QUALITY)."
)


@dataclass(frozen=True)
class Cell:
    status: str  # ok | na | error | missing (Sec. 9.9)
    value: float | str | None = None
    reason: str | None = None
    detail: str | None = None  # error traceback / exception text (Sec. 9.9 error)

    def display(self) -> str:
        if self.status == ERROR:
            return "err"
        if self.status in (NA, MISSING) or self.value is None:
            return ""
        if isinstance(self.value, float):
            return f"{self.value:g}" if self.value == int(self.value) else f"{self.value:.2f}"
        return str(self.value)


@dataclass
class ThesisRow:
    thesis: Thesis
    cells: dict[str, Cell] = field(default_factory=dict)  # metric -> Cell
    artefacts: dict[str, str] = field(default_factory=dict)  # kind -> relative path
    garbled: bool = False
    thesis_type: str = ""  # detected `thesis_type` metric (ADR-0019, #9); "" until run
    has_analysis: bool = False  # any module_runs row exists (there is cached
    # analysis to scrub when excluding, #11)


def exclude_toggle_needs_confirmation(row: ThesisRow, new_excluded: bool) -> bool:
    """Whether flipping ``excluded`` to ``new_excluded`` for ``row`` must prompt
    a destructive-scrub confirmation (US-PROF-EXCLUDE, #11).

    Only when *excluding* a thesis that has a cached analysis to delete: that
    triggers ``purge_analysis`` (irreversible local deletion of artefacts +
    metrics + run history). Un-excluding, or excluding a never-analysed thesis
    (nothing cached yet), needs no confirmation. Pure - unit-testable without
    Tk."""
    return new_excluded and row.has_analysis


def _error_details(repo: Repository) -> dict[tuple[int, str], str]:
    """Current-run error tracebacks keyed by (thesis, module). Not carried by
    ``v_current_metrics`` (Sec. 8.1.1), so read from the history view directly
    to feed the folded error tooltip (Sec. 9.9)."""
    rows = repo.conn.execute(
        "SELECT thesis_id, module_name, error_traceback FROM v_module_run_history "
        "WHERE recency_rank = 1 AND error_traceback IS NOT NULL"
    ).fetchall()
    return {(row["thesis_id"], row["module_name"]): row["error_traceback"] for row in rows}


def load_rows(repo: Repository, columns: list[MetricColumn]) -> list[ThesisRow]:
    theses = repo.list_theses(local_only=True, include_excluded=True)
    run_status: dict[tuple[int, str], tuple[str, str | None]] = {}
    values: dict[tuple[int, str], float | str | None] = {}
    for row in repo.current_metrics():
        run_status[(row["thesis_id"], row["module_name"])] = (row["status"], row["reason"])
        if row["metric_name"] is not None:
            value = row["value_num"] if row["value_num"] is not None else row["value_text"]
            values[(row["thesis_id"], row["metric_name"])] = value
    details = _error_details(repo)
    # theses that carry any run row -> there is cached analysis to scrub when
    # excluding (#11). run_status spans every status (ok/na/error), so this is
    # "has any module_runs row" regardless of outcome.
    analysed_ids = {thesis_id for (thesis_id, _module) in run_status}

    rows = []
    for thesis in theses:
        cells = {}
        for column in columns:
            status, reason = run_status.get((thesis.id, column.module), (MISSING, None))
            cells[column.metric] = Cell(
                status=status,
                value=values.get((thesis.id, column.metric)),
                reason=reason,
                detail=details.get((thesis.id, column.module)) if status == ERROR else None,
            )
        detected_type = values.get((thesis.id, "thesis_type"))
        artefacts = repo.current_artefacts(thesis.id)
        rows.append(
            ThesisRow(
                thesis=thesis,
                cells=cells,
                artefacts=artefacts,
                garbled=values.get((thesis.id, "extraction_quality")) == "garbled",
                thesis_type=detected_type if isinstance(detected_type, str) else "",
                has_analysis=thesis.id in analysed_ids or bool(artefacts),
            )
        )
    return rows


def outlier_bounds(rows: list[ThesisRow], columns: list[MetricColumn]) -> dict[str, tuple[float, float]]:
    """Per-metric IQR fences, 1.5 x IQR beyond Q1/Q3 - matplotlib's
    boxplot default (Sec. 9.5). Metrics with < 4 numeric values are skipped."""
    bounds = {}
    for column in columns:
        numbers = [
            c.value
            for row in rows
            if isinstance((c := row.cells[column.metric]).value, (int, float)) and c.status == OK
        ]
        if len(numbers) < 4:
            continue
        # method="inclusive" = linear interpolation, matplotlib's default
        q1, _, q3 = statistics.quantiles(numbers, n=4, method="inclusive")
        iqr = q3 - q1
        bounds[column.metric] = (q1 - 1.5 * iqr, q3 + 1.5 * iqr)
    return bounds


def is_outlier(cell: Cell, bounds: tuple[float, float] | None) -> bool:
    if bounds is None or not isinstance(cell.value, (int, float)) or cell.status != OK:
        return False
    return not bounds[0] <= cell.value <= bounds[1]


def _value_key(value: float | str | None, tie_break: str) -> tuple[int, float, str, str]:
    """Rank/number/text/tie-break tuple: numbers first, then text, blanks last
    (Sec. 9.2). ``tie_break`` keeps the order deterministic across equal values."""
    if isinstance(value, bool):  # bool is an int - rank it as text, not as 0/1
        return (1, 0.0, str(value).lower(), tie_break)
    if isinstance(value, (int, float)):
        return (0, float(value), "", tie_break)
    if isinstance(value, str) and value:
        return (1, 0.0, value.lower(), tie_break)
    return (2, 0.0, "", tie_break)


def sort_rows(rows: list[ThesisRow], key: str | None, reverse: bool) -> list[ThesisRow]:
    """Sort by a *column identity* (Sec. 9.2), not by grid position.

    ``key`` is the raw column name the grid header carries: a lead column
    ("file", "type", "excluded"), an artefact kind, or a metric name. ``None``
    means the default sort, by file name. Blank/missing values sort last in
    ascending order and every column tie-breaks on the file name, so the row
    order is deterministic (#60).
    """
    if key is None or key == "file":
        return sorted(rows, key=lambda r: r.thesis.pdf_filename.lower(), reverse=reverse)

    def key_func(row: ThesisRow):
        tie_break = row.thesis.pdf_filename.lower()
        if key == "type":
            return _value_key(row.thesis_type, tie_break)
        if key == "excluded":
            return (0, float(bool(row.thesis.excluded)), "", tie_break)
        if key in ARTEFACT_COLUMNS:
            return (0, float(key in row.artefacts), "", tie_break)
        cell = row.cells.get(key)
        return _value_key(cell.value if cell is not None else None, tie_break)

    return sorted(rows, key=key_func, reverse=reverse)


def cell_tooltip(cell: Cell) -> str | None:
    """Hover text for a metric cell, per its render state (Sec. 9.9).

    ``ok`` cells have no tooltip. ``na`` surfaces the reason; ``error`` shows a
    one-line reason and, folded below it, the exception text; ``missing`` shows
    the not-yet-run hint. Returns None when there is nothing to show.
    """
    if cell.status == NA:
        return cell.reason or "Not applicable for this thesis."
    if cell.status == ERROR:
        text = "Error: " + (cell.reason or "module raised an exception")
        if cell.detail:
            text += "\n\n" + cell.detail
        return text
    if cell.status == MISSING:
        return NOT_YET_RUN_HINT
    return None
