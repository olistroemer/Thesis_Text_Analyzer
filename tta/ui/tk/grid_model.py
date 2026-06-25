"""Pure data model behind the grid - no Tk imports, unit-testable.

Maps repository state to per-cell render states (Sec. 9.9: ok / na / error /
not-yet-run), computes IQR outlier bounds (Sec. 9.5), and sorts rows.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from tta.core.db.repository import Repository
from tta.core.types import Thesis
from tta.ui.tk.columns import MetricColumn

OK, NA, ERROR, MISSING = "ok", "na", "error", "missing"


@dataclass(frozen=True)
class Cell:
    status: str  # ok | na | error | missing (Sec. 9.9)
    value: float | str | None = None
    reason: str | None = None

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


def load_rows(repo: Repository, columns: list[MetricColumn]) -> list[ThesisRow]:
    theses = repo.list_theses(local_only=True, include_excluded=True)
    run_status: dict[tuple[int, str], tuple[str, str | None]] = {}
    values: dict[tuple[int, str], float | str | None] = {}
    for row in repo.current_metrics():
        run_status[(row["thesis_id"], row["module_name"])] = (row["status"], row["reason"])
        if row["metric_name"] is not None:
            value = row["value_num"] if row["value_num"] is not None else row["value_text"]
            values[(row["thesis_id"], row["metric_name"])] = value

    rows = []
    for thesis in theses:
        cells = {}
        for column in columns:
            status, reason = run_status.get((thesis.id, column.module), (MISSING, None))
            cells[column.metric] = Cell(
                status=status,
                value=values.get((thesis.id, column.metric)),
                reason=reason,
            )
        rows.append(
            ThesisRow(
                thesis=thesis,
                cells=cells,
                artefacts=repo.current_artefacts(thesis.id),
                garbled=values.get((thesis.id, "extraction_quality")) == "garbled",
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


def sort_rows(rows: list[ThesisRow], metric: str | None, reverse: bool) -> list[ThesisRow]:
    """Sort by a metric column (None -> by filename). Missing values sort last."""
    if metric is None:
        return sorted(rows, key=lambda r: r.thesis.pdf_filename.lower(), reverse=reverse)

    def key(row: ThesisRow):
        value = row.cells[metric].value
        if isinstance(value, (int, float)):
            return (0, value, "")
        if isinstance(value, str):
            return (1, 0.0, value.lower())
        return (2, 0.0, "")

    return sorted(rows, key=key, reverse=reverse)
