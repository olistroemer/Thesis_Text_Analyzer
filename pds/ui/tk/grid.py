"""Grid tab: tksheet widget over grid_model (§9.2, §9.9, ADR-0001)."""

from __future__ import annotations

import subprocess
import sys
from tkinter import ttk

from tksheet import Sheet

from pds.core.artefacts import ArtefactStore
from pds.core.db.repository import Repository
from pds.ui.tk import grid_model
from pds.ui.tk.columns import LEAD_COLUMNS, MetricColumn

# §9.9 render states / §9.5 outlier overlay
COLOR_NA = "#e8e8e8"
COLOR_ERROR = "#ffd0d0"
COLOR_OUTLIER = "#ffe2b0"


def open_with_default_app(path) -> None:
    if sys.platform == "win32":
        import os

        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class GridView(ttk.Frame):
    def __init__(self, parent, repo: Repository, store: ArtefactStore):
        super().__init__(parent)
        self.repo = repo
        self.store = store
        self.columns: list[MetricColumn] = []
        self.artefact_kinds: list[str] = []
        self.rows: list[grid_model.ThesisRow] = []
        self._sort_metric: str | None = None
        self._sort_reverse = False
        self.sheet = Sheet(self, headers=[], data=[])
        self.sheet.enable_bindings(
            "single_select", "row_select", "column_width_resize", "copy", "arrowkeys"
        )
        self.sheet.extra_bindings("column_select", self._on_column_select)
        self.sheet.bind("<Double-Button-1>", self._on_double_click)
        self.sheet.pack(fill="both", expand=True)

    # -- data ---------------------------------------------------------------

    def reload(self, columns: list[MetricColumn], show_artefacts: bool) -> None:
        self.columns = columns
        self.artefact_kinds = (
            ["raw_text", "language", "tokens", "pdf_metadata"] if show_artefacts else []
        )
        self.rows = grid_model.sort_rows(
            grid_model.load_rows(self.repo, columns), self._sort_metric, self._sort_reverse
        )
        self._render()

    def _header(self) -> list[str]:
        return list(LEAD_COLUMNS) + self.artefact_kinds + [c.metric for c in self.columns]

    def _render(self) -> None:
        bounds = grid_model.outlier_bounds(self.rows, self.columns)
        data = []
        for row in self.rows:
            file_label = ("⚠ " if row.garbled else "") + row.thesis.pdf_filename
            line = [file_label, row.thesis.type]
            line += ["📄" if kind in row.artefacts else "" for kind in self.artefact_kinds]
            line += [row.cells[c.metric].display() for c in self.columns]
            data.append(line)
        self.sheet.set_sheet_data(data, reset_col_positions=True, redraw=False)
        self.sheet.headers(self._header())
        self.sheet.dehighlight_all()
        offset = len(LEAD_COLUMNS) + len(self.artefact_kinds)
        for r, row in enumerate(self.rows):
            for i, column in enumerate(self.columns):
                cell = row.cells[column.metric]
                color = None
                if cell.status == grid_model.NA:
                    color = COLOR_NA
                elif cell.status == grid_model.ERROR:
                    color = COLOR_ERROR
                elif grid_model.is_outlier(cell, bounds.get(column.metric)):
                    color = COLOR_OUTLIER
                if color:
                    self.sheet.highlight_cells(row=r, column=offset + i, bg=color)
        self.sheet.redraw()

    # -- interactions ---------------------------------------------------------

    def _on_column_select(self, event) -> None:
        """Header click sorts (US-PROF-SORT); repeated click flips order."""
        try:
            column = event["selected"].column
        except Exception:
            return
        offset = len(LEAD_COLUMNS) + len(self.artefact_kinds)
        metric = self.columns[column - offset].metric if column >= offset else None
        if metric == self._sort_metric:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_metric, self._sort_reverse = metric, False
        self.rows = grid_model.sort_rows(self.rows, self._sort_metric, self._sort_reverse)
        self._render()

    def _on_double_click(self, _event) -> None:
        """Double-click: artefact cell opens the cached file, file cell the
        PDF (US-PROF-DOUBLECLICK)."""
        selected = self.sheet.get_currently_selected()
        if not selected:
            return
        r, c = selected.row, selected.column
        if not (0 <= r < len(self.rows)):
            return
        row = self.rows[r]
        if c == 0:
            open_with_default_app(row.thesis.pdf_path)
        elif 0 < len(self.artefact_kinds) and len(LEAD_COLUMNS) <= c < len(LEAD_COLUMNS) + len(self.artefact_kinds):
            kind = self.artefact_kinds[c - len(LEAD_COLUMNS)]
            if kind in row.artefacts:
                open_with_default_app(self.store.resolve(row.artefacts[kind]))

    def status_text(self) -> str:
        return f"{len(self.rows)} theses"
