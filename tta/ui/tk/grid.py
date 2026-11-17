"""Grid tab: tksheet widget over grid_model (Sec. 9.2, Sec. 9.9, ADR-0001)."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from tksheet import Sheet, num2alpha

from tta.core.artefacts import ArtefactStore
from tta.core.db.repository import Repository
from tta.core.i18n import N_, _, format_integer
from tta.core.types import thesis_type_label
from tta.ui.tk import detail, grid_model
from tta.ui.tk.columns import (
    ARTEFACT_COLUMNS,
    LEAD_COLUMNS,
    MetricColumn,
    column_help,
    column_label,
)

# Sec. 9.9 render states / Sec. 9.5 outlier overlay
COLOR_NA = "#e8e8e8"
COLOR_ERROR = "#ffd0d0"
COLOR_OUTLIER = "#ffe2b0"
# Sec. 9.2: excluded rows render greyed (US-PROF-EXCLUDE, #11).
COLOR_EXCLUDED = "#c8c8c8"
COLOR_EXCLUDED_FG = "#707070"

# Lead-column positions (LEAD_COLUMNS = "excluded", "state", "file", "type").
EXCLUDED_COL = LEAD_COLUMNS.index("excluded")
STATE_COL = LEAD_COLUMNS.index("state")
FILE_COL = LEAD_COLUMNS.index("file")

# Sec. 9.9 whole-row indicator, rendered in the State column (#65). ADR-0018:
# ASCII marker, not a glyph.
STATE_GARBLED = "[!]"

# Sec. 9.2 header sort indicator (#40) and the details-panel heading (#16).
SORT_ASC = N_("{header} (asc)")
SORT_DESC = N_("{header} (desc)")
DETAIL_HEADING = N_("{filename} - {label}")
DETAIL_METRIC_NAME = N_("Column name: {name}")
STATUS_THESES = N_("{count} theses")

# Sec. 9.2 column widths (#90): room around the header text, in pixels. tksheet
# itself measures a header at text width + 7; the rest keeps the label clear of
# the column borders.
HEADER_PADDING = 18


def header_widths(headers, measure, minimum: int, padding: int = HEADER_PADDING) -> list[int]:
    """Column widths that fit each displayed header (Sec. 9.2, #90).

    ``measure`` maps a header string to its pixel width in the header font.
    A column is never narrower than ``minimum`` (tksheet's default width),
    so short headers keep the familiar layout; only a header that would be
    cut off widens its column. Cell contents are deliberately ignored.
    """
    return [max(minimum, measure(header) + padding) for header in headers]


def open_with_default_app(path) -> None:
    if sys.platform == "win32":
        import os

        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class GridView(ttk.Frame):
    def __init__(
        self,
        parent,
        repo: Repository,
        store: ArtefactStore,
        on_remove=None,
    ):
        super().__init__(parent)
        self.repo = repo
        self.store = store
        self.columns: list[MetricColumn] = []
        self.artefact_kinds: list[str] = []
        self.rows: list[grid_model.ThesisRow] = []
        # raw name of the column sorted on - a lead column, an artefact kind or
        # a metric (Sec. 9.2, #60). None = the default sort, by file name.
        self._sort_key: str | None = None
        self._sort_reverse = False
        self._sorted = False
        # Extended mode (Sec. 9.3). The caller passes it as ``show_artefacts``:
        # the artefact-presence columns are exactly the extended-only columns.
        # Only the traceback inside the details panel is gated on it (Sec. 9.9).
        self.extended = False
        self.sheet = Sheet(self, headers=[], data=[])
        self.sheet.enable_bindings(
            "single_select",
            "row_select",
            "column_select",
            "column_width_resize",
            "copy",
            "arrowkeys",
        )
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
        # Row context menu (#76). Removing a thesis is a ROW action: it acts on
        # one thesis, and a destructive step nothing can undo should not sit a
        # misclick from the Excluded checkbox. A trashcan in a cell was asked
        # for and is not available - tksheet 7.6 has no per-cell image API, and
        # a trashcan character would render as a missing-glyph box (#26,
        # ADR-0018). Button-3 is bound and the row resolved here rather than
        # through tksheet's own popup menu, so the row under the cursor is
        # unambiguous - the same reason _on_header_click resolves its column.
        self._on_remove = on_remove
        self._row_menu = tk.Menu(self, tearoff=False)
        self._row_menu.add_command(
            label=_("Remove thesis..."), command=self._remove_menu_row
        )
        self._menu_row: int | None = None
        self.sheet.MT.bind("<Button-3>", self._on_row_right_click)
        self.sheet.pack(fill="both", expand=True)

    # -- data ---------------------------------------------------------------

    def reload(self, columns: list[MetricColumn], show_artefacts: bool) -> None:
        self.columns = columns
        self.extended = show_artefacts
        self.artefact_kinds = list(ARTEFACT_COLUMNS) if show_artefacts else []
        self.rows = grid_model.sort_rows(
            grid_model.load_rows(self.repo, columns), self._sort_key, self._sort_reverse
        )
        self._render()

    def _column_names(self) -> list[str]:
        """Raw column names, left to right: lead columns, artefact-presence
        columns (extended mode), then metric columns. This list *is* the
        column-identity model: headers and sort keys both index into it (#60)."""
        return list(LEAD_COLUMNS) + self.artefact_kinds + [c.metric for c in self.columns]

    def _header(self) -> list[str]:
        """Displayed headers: human-friendly labels (#16), with the ASCII sort
        indicator on the sorted one (#40).

        The *identity* model stays ``_column_names()`` - sort keys, the DB and
        the export all speak raw names. Only what the professor reads is
        translated (US-PROF-EXPLAIN, SDD Sec. 9.6)."""
        headers = [column_label(name) for name in self._column_names()]
        if self._sorted:
            index = self._sorted_header_index()
            if index is not None:
                template = SORT_DESC if self._sort_reverse else SORT_ASC
                headers[index] = _(template).format(header=headers[index])
        return headers

    def _sorted_header_index(self) -> int | None:
        """Header position of the current sort column (ASCII indicator, #40).
        The indicator lands on the column actually sorted on, whichever kind of
        column that is (#60)."""
        key = "file" if self._sort_key is None else self._sort_key  # default sort
        names = self._column_names()
        return names.index(key) if key in names else None

    def _render(self) -> None:
        bounds = grid_model.outlier_bounds(self.rows, self.columns)
        data = []
        for row in self.rows:
            # LEAD_COLUMNS order: excluded (bool -> editable tksheet checkbox),
            # state, file (bare name - the state marker has its own column since
            # #65, so names no longer shift row to row), type.
            line = [
                bool(row.thesis.excluded),
                STATE_GARBLED if row.garbled else "",
                row.thesis.pdf_filename,
                thesis_type_label(row.thesis_type) if row.thesis_type else "",
            ]
            # bools, rendered as read-only checkboxes by _apply_artefact_columns
            line += [kind in row.artefacts for kind in self.artefact_kinds]
            line += [row.cells[c.metric].display() for c in self.columns]
            data.append(line)
        self.sheet.set_sheet_data(data, reset_col_positions=True, redraw=False)
        headers = self._header()
        self.sheet.headers(headers)
        header_font = tkfont.Font(font=self.sheet.header_font())
        self.sheet.set_column_widths(
            header_widths(headers, header_font.measure, self.sheet.ops.default_column_width)
        )
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
        self._apply_artefact_columns()
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

    def _apply_artefact_columns(self) -> None:
        """Render the artefact-presence columns as *read-only* tksheet checkboxes
        (Sec. 9.2, #65): state="disabled" draws the box greyed and makes
        ``click_checkbox`` a no-op, so a click cannot fabricate or clear
        presence, while double-click-to-open still works. Re-applied each render
        because ``set_sheet_data`` resets column options."""
        for i in range(len(self.artefact_kinds)):
            self.sheet.checkbox(
                self.sheet.span(num2alpha(len(LEAD_COLUMNS) + i)),
                edit_data=False,  # keep the per-row bool already in the cell data
                state="disabled",
                text="",
                redraw=False,
            )

    # -- interactions ---------------------------------------------------------

    def _on_header_click(self, event) -> None:
        """Header click sorts (US-PROF-SORT); a repeat click on the same
        column flips ASC<->DESC (#40)."""
        column = self.sheet.identify_column(event, allow_end=False)
        if column is None:
            return
        names = self._column_names()
        if not 0 <= column < len(names):
            return
        key = names[column]
        if self._sorted and key == self._sort_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key, self._sort_reverse = key, False
        self._sorted = True
        self.rows = grid_model.sort_rows(self.rows, self._sort_key, self._sort_reverse)
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
                _("Exclude thesis"),
                _(
                    'Exclude "{filename}" and permanently delete its cached '
                    "analysis from this machine (extracted text, tokens, PDF "
                    "metadata and all metric values)?\n\n"
                    "This is destructive and cannot be undone. The source PDF file "
                    "is not touched."
                ).format(filename=row.thesis.pdf_filename),
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
                    _("Scrub incomplete"),
                    _(
                        '"{filename}" was excluded and its analysis records were '
                        "removed, but some cached files could not be deleted:"
                        "\n\n{folder}\n\nThey remain on this machine only and are "
                        "never exported. Delete that folder manually to remove "
                        "them."
                    ).format(filename=row.thesis.pdf_filename, folder=folder),
                    parent=self,
                )
        self._reload_current()

    def _reload_current(self) -> None:
        """Reload the grid keeping the current columns and mode (used to apply or
        revert an Excluded toggle without the parent window's help)."""
        self.reload(self.columns, show_artefacts=bool(self.artefact_kinds))

    def selected_thesis_id(self) -> int | None:
        """The thesis id of the currently selected row, or None (#63)."""
        selected = self.sheet.get_currently_selected()
        if not selected:
            return None
        r = selected.row
        if not (0 <= r < len(self.rows)):
            return None
        return self.rows[r].thesis.id

    def _on_row_right_click(self, event) -> None:
        """Select the row under the cursor and offer the row actions (#76)."""
        if self._on_remove is None:
            return
        row = self.sheet.identify_row(event, allow_end=False)
        if row is None or not (0 <= row < len(self.rows)):
            return
        self._menu_row = row
        self.sheet.select_row(row)
        self._row_menu.tk_popup(event.x_root, event.y_root)

    def _remove_menu_row(self) -> None:
        """Hand the right-clicked thesis to the caller's remove flow.

        The dialog and the reload live in the parent: GridView deliberately
        holds a Repository and an ArtefactStore, not a Project, so it cannot
        run the flow itself (ADR-0002 keeps the grid a view).
        """
        row, self._menu_row = self._menu_row, None
        if row is None or not (0 <= row < len(self.rows)) or self._on_remove is None:
            return
        self._on_remove(self.rows[row].thesis.id)

    def _on_double_click(self, event) -> None:
        """Double-click, the grid's single "open this" gesture (Sec. 9.9,
        US-PROF-DOUBLECLICK): the file cell opens the PDF, an artefact cell the
        cached file, and a metric or State cell with something to explain opens
        the details panel (there are no hover tooltips, #66).

        Data cells only. ``Sheet.bind("<Double-Button-1>", ...)`` installs the
        handler on the header, row-index and corner canvases as well as the
        table, so without this guard double-clicking a column header both
        re-sorted the grid (two header clicks = two sort toggles) and opened
        the details panel for whatever cell happened to be selected."""
        if event is not None and getattr(event, "widget", None) is not self.sheet.MT:
            return
        selected = self.sheet.get_currently_selected()
        if not selected:
            return
        r, c = selected.row, selected.column
        if not (0 <= r < len(self.rows)):
            return
        row = self.rows[r]
        offset = len(LEAD_COLUMNS) + len(self.artefact_kinds)
        if c == FILE_COL:
            open_with_default_app(row.thesis.pdf_path)
        elif len(LEAD_COLUMNS) <= c < offset:
            kind = self.artefact_kinds[c - len(LEAD_COLUMNS)]
            if kind in row.artefacts:
                open_with_default_app(self.store.resolve(row.artefacts[kind]))
        elif c == STATE_COL:
            if row.garbled:
                self._show_details(row, "state", grid_model.GARBLED_DETAIL)
        elif offset <= c < offset + len(self.columns):
            metric = self.columns[c - offset].metric
            body = grid_model.cell_details(row.cells[metric], extended=self.extended)
            if body:
                self._show_details(row, metric, body)

    def _show_details(self, row: grid_model.ThesisRow, column_name: str, body: str) -> None:
        """Open the Sec. 9.9 details panel for one cell. The heading names the
        row and column and carries that column's one-line help, which is why
        COLUMN_HELP outlived the tooltips (#66, and #16 reuses it)."""
        heading = _(DETAIL_HEADING).format(
            filename=row.thesis.pdf_filename, label=column_label(column_name)
        )
        # The raw name stays discoverable here - it is what `tta list`, the
        # export and every help page key on (#16 acceptance criterion).
        heading += "\n" + _(DETAIL_METRIC_NAME).format(name=column_name)
        help_text = column_help(column_name)
        if help_text:
            heading += "\n" + help_text
        detail.show_details(self, heading=heading, body=body)

    def status_text(self) -> str:
        return _(STATUS_THESES).format(count=format_integer(len(self.rows)))
