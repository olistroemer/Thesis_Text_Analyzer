"""File-add and export dialogs (§9.7 happy path: no surprises, sensible
defaults, one decision per dialog)."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from tta.core.export import ExportPolicy, export_database
from tta.core.project import Project
from tta.core.types import THESIS_TYPES


def ask_thesis_type(parent) -> str | None:
    """Optional Type mini-dialog after file selection (US-PROF-ATTRS).
    Returns None when cancelled, else a THESIS_TYPES value."""
    dialog = tk.Toplevel(parent)
    dialog.title("Thesis type")
    dialog.transient(parent)
    dialog.grab_set()
    choice = tk.StringVar(value="unspecified")
    ttk.Label(dialog, text="Type for the added theses:", padding=8).pack(anchor="w")
    for value in THESIS_TYPES:
        ttk.Radiobutton(dialog, text=value.capitalize(), variable=choice, value=value).pack(
            anchor="w", padx=16
        )
    result: list[str | None] = [None]

    def confirm():
        result[0] = choice.get()
        dialog.destroy()

    buttons = ttk.Frame(dialog, padding=8)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="OK", command=confirm).pack(side="right")
    ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=4)
    parent.wait_window(dialog)
    return result[0]


def add_files_flow(parent, project: Project) -> int:
    """Multi-select file dialog → type mini-dialog → add. Returns count."""
    filenames = filedialog.askopenfilenames(
        parent=parent, title="Add thesis PDFs", filetypes=[("PDF files", "*.pdf")]
    )
    if not filenames:
        return 0
    thesis_type = ask_thesis_type(parent)
    if thesis_type is None:
        return 0
    for filename in filenames:
        project.repo.add_thesis(filename, type=thesis_type)
    return len(filenames)


def export_flow(parent, project: Project) -> None:
    """Pre-export confirmation (§8.3, QA-PRIV): row count + path, one
    Export button, no further choices."""
    theses = project.repo.list_theses(local_only=True, include_excluded=False)
    if not theses:
        messagebox.showinfo("Export", "Nothing to export yet — add and analyse theses first.",
                            parent=parent)
        return
    label = project.config.institution or "export"
    exports_dir = project.dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    out = filedialog.asksaveasfilename(
        parent=parent,
        title=f"Export {len(theses)} theses (results only, no documents)",
        initialdir=exports_dir,
        initialfile=f"{label}-{date.today():%Y-%m-%d}.sqlite",
        defaultextension=".sqlite",
        filetypes=[("SQLite database", "*.sqlite")],
    )
    if not out:
        return
    try:
        stats = export_database(project.repo.conn, out, ExportPolicy.FULL)
    except FileExistsError as exc:
        messagebox.showerror("Export", str(exc), parent=parent)
        return
    if messagebox.askyesno(
        "Export complete",
        f"Exported {stats.theses} theses ({stats.runs} runs) to:\n{stats.path}\n\n"
        "Only anonymised metric values were written — no documents, file names, "
        "or text left your machine.\n\nShow in folder?",
        parent=parent,
    ):
        from tta.ui.tk.grid import open_with_default_app

        open_with_default_app(stats.path.parent)
