"""Grid tab: tksheet widget over grid_model (Sec. 9.2, Sec. 9.9, ADR-0001)."""

from __future__ import annotations

import subprocess
import sys
from tkinter import messagebox, ttk

from tksheet import Sheet, num2alpha

from tta.core.artefacts import ArtefactStore
from tta.core.db.repository import Repository
from tta.ui.tk import grid_model
from tta.ui.tk.columns import LEAD_COLUMNS, MetricColumn, column_help

# Sec. 9.9 render states / Sec. 9.5 outlier overlay
COLOR_NA = "#e8e8e8"
COLOR_ERROR = "#ffd0d0"
COLOR_OUTLIER = "#ffe2b0"
# Sec. 9.2: excluded rows render greyed (US-PROF-EXCLUDE, #11).
COLOR_EXCLUDED = "#c8c8c8"
COLOR_EXCLUDED_FG = "#707070"

# Lead-column positions (LEAD_COLUMNS = "excluded", "file", "type").
EXCLUDED_COL = LEAD_COLUMNS.index("excluded")
FILE_COL = LEAD_COLUMNS.index("file")


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
        self._sorted = False
        # note keys set on the last render, cleared before the next one so a
        # shrunk/re-ordered row set never leaves a stale hover tooltip (Sec. 9.9)
        self._note_cells: set[tuple[int, int]] = set()
        self._note_headers: set[int] = set()
        self.sheet = Sheet(self, headers=[], data=[])
        self.sheet.enable_bindings(
            "single_select",
            "row_select",
            "column_select",
            "column_width_resize",
            "copy",
            "arrowkeys",
        )
        # Sec. 9.9: hover tooltips over cells and headers. tksheet surfaces a
        # cell/header "note" as a hover popup when tooltips are enabled; the
        # notes themselves are (re)set per render in ``_set_notes``.
        self.sheet.set_options(tooltips=True, redraw=False)
        # Sort on a header click (#40). tksheet's "column_select" extra binding
        # fires only when the selected column *changes*, so a repeat click on
        # the already-sorted column emitted no event and DESC was unreachable.
        # Binding on the header widget with add="+" is not enough either:
        # tksheet's own press handler runs first on the shared widget tag and
        # returns "break" on a no-change re-click, which suppresses the appended
        # callback. So install the handler on a private bindtag placed ahead of
        # tksheet's - it fires first (before any "break") on every click and
        # returns None, leaving tksheet's selection visuals intact.
        header = self.sheet.CH
        tag = f"gridHeaderClick{id(self)}"
        header.bindtags((tag, *header.bindtags()))
        header.bind_class(tag, "<Button-1>", self._on_header_click)
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
        headers = list(LEAD_COLUMNS) + self.artefact_kinds + [c.metric for c in self.columns]
        if self._sorted:
            index = self._sorted_header_index()
            if index is not None:
                headers[index] += " (desc)" if self._sort_reverse else " (asc)"
        return headers

    def _sorted_header_index(self) -> int | None:
        """Header position of the current sort column (ASCII indicator, #40)."""
        if self._sort_metric is None:
            return FILE_COL  # default sort is by filename
        offset = len(LEAD_COLUMNS) + len(self.artefact_kinds)
        for i, column in enumerate(self.columns):
            if column.metric == self._sort_metric:
                return offset + i
        return None

    def _render(self) -> None:
        bounds = grid_model.outlier_bounds(self.rows, self.columns)
        data = []
        for row in self.rows:
            file_label = ("[!] " if row.garbled else "") + row.thesis.pdf_filename
            # LEAD_COLUMNS order: excluded (bool -> tksheet checkbox), file, type
            line = [bool(row.thesis.excluded), file_label, row.thesis_type]
            line += ["[x]" if kind in row.artefacts else "" for kind in self.artefact_kinds]
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
        self._apply_excluded_column()
        self._set_notes()
        self.sheet.redraw()

    def _apply_excluded_column(self) -> None:
        """Register the lead Excluded column as a tksheet checkbox bound to the
        toggle handler, and grey excluded rows (Sec. 9.2, #11). Re-applied each
        render because ``set_sheet_data`` resets column options."""
        self.sheet.checkbox(
            self.sheet.span(num2alpha(EXCLUDED_COL)),
            edit_data=False,  # keep the per-row bool already in the cell data
            check_function=self._on_excluded_toggle,
            text="",
            redraw=False,
        )
        excluded_rows = [r for r, row in enumerate(self.rows) if row.thesis.excluded]
        if excluded_rows:
            self.sheet.highlight_rows(
                rows=excluded_rows, bg=COLOR_EXCLUDED, fg=COLOR_EXCLUDED_FG, redraw=False
            )

    def _set_notes(self) -> None:
        """Attach the Sec. 9.9 hover tooltips: a per-metric explanation on each
        column header, and per-cell text for na/error/not-yet-run cells plus the
        garbled-row indicator. Notes set last render are cleared first."""
        sheet = self.sheet
        for r, c in self._note_cells:
            sheet.note(sheet.span(r, c), note=None)
        for c in self._note_headers:
            sheet.note(sheet.span(num2alpha(c), header=True), note=None)
        self._note_cells = set()
        self._note_headers = set()

        names = list(LEAD_COLUMNS) + self.artefact_kinds + [c.metric for c in self.columns]
        for c, name in enumerate(names):
            help_text = column_help(name)
            if help_text:
                sheet.note(sheet.span(num2alpha(c), header=True), note=help_text)
                self._note_headers.add(c)

        offset = len(LEAD_COLUMNS) + len(self.artefact_kinds)
        for r, row in enumerate(self.rows):
            if row.garbled:
                sheet.note(sheet.span(r, FILE_COL), note=grid_model.GARBLED_TOOLTIP)
                self._note_cells.add((r, FILE_COL))
            for i, column in enumerate(self.columns):
                tip = grid_model.cell_tooltip(row.cells[column.metric])
                if tip:
                    col = offset + i
                    sheet.note(sheet.span(r, col), note=tip)
                    self._note_cells.add((r, col))

    # -- interactions ---------------------------------------------------------

    def _on_header_click(self, event) -> None:
        """Header click sorts (US-PROF-SORT); a repeat click on the same
        column flips ASC<->DESC (#40)."""
        column = self.sheet.identify_column(event, allow_end=False)
        if column is None:
            return
        offset = len(LEAD_COLUMNS) + len(self.artefact_kinds)
        metric = (
            self.columns[column - offset].metric
            if offset <= column < offset + len(self.columns)
            else None
        )
        if self._sorted and metric == self._sort_metric:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_metric, self._sort_reverse = metric, False
        self._sorted = True
        self.rows = grid_model.sort_rows(self.rows, self._sort_metric, self._sort_reverse)
        self._render()

    def _on_excluded_toggle(self, event) -> None:
        """Excluded checkbox toggled (US-PROF-EXCLUDE, #11). Excluding an
        already-analysed thesis prompts a destructive-scrub confirmation and
        then calls ``purge_analysis``; declining reverts the checkbox.
        Un-excluding (or excluding a never-analysed thesis) just flips the flag
        so the thesis re-runs as 'missing' on the next Run.

        ``event.row`` is the data-row index (rows are not tksheet-reordered) and
        ``event.value`` is the new checked state (tksheet flipped it before this
        callback)."""
        r = event.row
        if not (0 <= r < len(self.rows)):
            return
        row = self.rows[r]
        new_excluded = bool(event.value)
        if grid_model.exclude_toggle_needs_confirmation(row, new_excluded):
            confirmed = messagebox.askyesno(
                "Exclude thesis",
                f'Exclude "{row.thesis.pdf_filename}" and permanently delete its '
                "cached analysis from this machine (extracted text, tokens, PDF "
                "metadata and all metric values)?\n\n"
                "This is destructive and cannot be undone. The source PDF file is "
                "not touched.",
                icon="warning",
                default="no",
                parent=self,
            )
            if not confirmed:
                self._reload_current()  # revert the checkbox to the stored state
                return
        self.repo.set_excluded(row.thesis.id, new_excluded)
        if new_excluded and row.has_analysis:
            try:
                self.repo.purge_analysis(row.thesis.id, store=self.store)
            except OSError:
                # The DB analysis is gone, but some local artefact files could
                # not be removed (e.g. a locked file). They never leave this
                # machine (ADR-0007) - say so rather than imply a clean scrub.
                folder = self.store.resolve(f"artefacts/{row.thesis.id}")
                messagebox.showwarning(
                    "Scrub incomplete",
                    f'"{row.thesis.pdf_filename}" was excluded and its analysis '
                    "records were removed, but some cached files could not be "
                    f"deleted:\n\n{folder}\n\nThey remain on this machine only and "
                    "are never exported. Delete that folder manually to remove "
                    "them.",
                    parent=self,
                )
        self._reload_current()

    def _reload_current(self) -> None:
        """Reload the grid keeping the current columns and mode (used to apply or
        revert an Excluded toggle without the parent window's help)."""
        self.reload(self.columns, show_artefacts=bool(self.artefact_kinds))

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
        if c == FILE_COL:
            open_with_default_app(row.thesis.pdf_path)
        elif 0 < len(self.artefact_kinds) and len(LEAD_COLUMNS) <= c < len(LEAD_COLUMNS) + len(self.artefact_kinds):
            kind = self.artefact_kinds[c - len(LEAD_COLUMNS)]
            if kind in row.artefacts:
                open_with_default_app(self.store.resolve(row.artefacts[kind]))

    def status_text(self) -> str:
        return f"{len(self.rows)} theses"
