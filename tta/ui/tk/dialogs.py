"""File-add and export dialogs (Sec. 9.7 happy path: no surprises, sensible
defaults, one decision per dialog)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

from tta.core.discovery import collect_pdfs
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


def add_folder_flow(parent, project: Project) -> int:
    """Pick one folder -> add every PDF beneath it, recursively. Returns count.

    The CLI has always done this for a directory INPUT; the GUI could only
    multi-select individual files (#62). Both now walk the folder through the
    same core collector (ADR-0002), so ".PDF" is picked up either way.

    The count is confirmed **before** anything is written: a mis-picked folder
    (a home directory, a whole drive) would otherwise dump thousands of rows,
    and undoing an add is a per-thesis operation, not one click. Tk's
    ``askdirectory`` returns a single directory, so this adds one folder per
    invocation; ``collect_pdfs`` itself takes any number, which is what
    ``tta run DIR1 DIR2 ...`` passes."""
    chosen = filedialog.askdirectory(
        parent=parent, title="Add all thesis PDFs in a folder (including subfolders)"
    )
    if not chosen:
        return 0
    folder = Path(chosen)
    pdfs = collect_pdfs([folder])
    if not pdfs:
        messagebox.showinfo(
            "Add folder", f"No PDFs found in or below:\n{folder}", parent=parent
        )
        return 0
    if not messagebox.askyesno(
        "Add folder",
        f"Add {len(pdfs)} PDFs from:\n{folder}\n\n"
        "Subfolders are included. Nothing is read yet - the documents are "
        "only analysed when you click Run.",
        parent=parent,
    ):
        return 0
    return len(project.repo.add_theses(pdfs))

def remove_thesis_flow(parent, project: Project, thesis_id: int) -> bool:
    """Confirm, then remove one thesis from the project. Returns True if it was.

    The harder version of the Excluded checkbox (#63, ADR-0006 rev. 7). The
    wording has to carry the two things that distinguish it from excluding:
    the cached analysis is destroyed, and the thesis row itself is forgotten -
    so nothing can re-include it, and the same PDF adds again as a fresh
    thesis. The source PDF is untouched.

    An incomplete artefact removal is surfaced rather than swallowed (as in
    ``export_flow``'s sibling path for exclude, #11): the rows are already
    gone, the residual files never leave the machine (ADR-0007), and the user
    is told where they are."""
    try:
        thesis = project.repo.get_thesis(thesis_id)
    except KeyError:
        messagebox.showerror(
            "Remove thesis", f"Thesis {thesis_id} is no longer in this project.", parent=parent
        )
        return False
    if not messagebox.askyesno(
        "Remove thesis",
        f"Remove {thesis.pdf_filename} from the project?\n\n"
        "Its analysis results (cached text, tokens, metrics and run history) "
        "are permanently deleted from this machine, and the thesis is "
        "forgotten entirely - unlike excluding it, there is nothing left to "
        "re-include. Adding the same file again later creates a new thesis "
        "with no history.\n\nThe PDF itself is not touched. "
        "This cannot be undone.",
        parent=parent,
        icon="warning",
        default="no",
    ):
        return False
    try:
        project.repo.delete_thesis(thesis_id, store=project.store)
    except OSError as exc:
        artefacts_dir = project.store.resolve(f"artefacts/{thesis_id}")
        messagebox.showwarning(
            "Remove thesis",
            f"{thesis.pdf_filename} was removed from the project, but some "
            f"cached files could not be deleted:\n{artefacts_dir}\n({exc})\n\n"
            "They are never exported. Delete that folder manually to remove them.",
            parent=parent,
        )
    return True

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
