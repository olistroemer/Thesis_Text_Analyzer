"""File-add and export dialogs (Sec. 9.7 happy path: no surprises, sensible
defaults, one decision per dialog)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

from tta.core.export import ExportPolicy, export_database
from tta.core.project import Project


def add_files_flow(parent, project: Project) -> int:
    """Multi-select file dialog -> add immediately. Returns count.

    No type mini-dialog (ADR-0019, #9): thesis type is detected at run time
    by ``mod_classify_thesis_type``, and adding stays instant and dialog-free
    (US-RES-LOW-FRICTION; ADR-0006 rev. 4 defers hashing to run time)."""
    filenames = filedialog.askopenfilenames(
        parent=parent, title="Add thesis PDFs", filetypes=[("PDF files", "*.pdf")]
    )
    if not filenames:
        return 0
    # one batched transaction, not one commit per file (#61, ADR-0006 rev. 6)
    return len(project.repo.add_theses([Path(name) for name in filenames]))


def export_flow(parent, project: Project) -> None:
    """Pre-export confirmation (Sec. 8.3, QA-PRIV): row count + path, one
    Export button, no further choices."""
    theses = project.repo.list_theses(local_only=True, include_excluded=False)
    if not theses:
        messagebox.showinfo("Export", "Nothing to export yet - add and analyse theses first.",
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
        "Only anonymised metric values were written - no documents, file names, "
        "or text left your machine.\n\nShow in folder?",
        parent=parent,
    ):
        from tta.ui.tk.grid import open_with_default_app

        open_with_default_app(stats.path.parent)
