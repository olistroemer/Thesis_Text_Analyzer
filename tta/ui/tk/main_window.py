"""Main window (Sec. 9.2): menu bar, toolbar, Grid/Report tabs, status line.

Runs execute on a background thread; domain events are marshalled into
the Tk loop via a queue drained by ``root.after`` (ADR-0002 invariant 3).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from tta.core import events
from tta.core.config import save_config
from tta.core.modules.registry import default_registry
from tta.core.privacy_metadata import render_report_md
from tta.core.project import Project
from tta.ui.tk import dialogs
from tta.ui.tk.columns import metric_columns
from tta.ui.tk.grid import GridView
from tta.ui.tk.report import ReportView

POLL_MS = 100

FIRST_LAUNCH_BANNER = (
    "Your project lives at {path}. All thesis data and analyses are stored here. "
    "To move or back up the project, copy this folder. To use a different "
    "location, choose File -> Open Project..."
)


class MainWindow:
    def __init__(self, project: Project, first_launch: bool = False):
        self.project = project
        self.registry = default_registry()
        self.root = tk.Tk()
        self.root.title(f"Thesis Text Analyzer - {project.dir}")
        self.root.geometry("1100x700")
        self._event_queue: queue.Queue = queue.Queue()
        self._run_thread: threading.Thread | None = None
        self._runner = None

        self._build_menu()
        if first_launch:
            self._build_banner()
        self._build_toolbar()
        self._build_tabs()
        self.status = ttk.Label(self.root, anchor="w", padding=(8, 2))
        self.status.pack(fill="x", side="bottom")

        self.refresh()
        self.root.after(POLL_MS, self._drain_events)

    # -- construction --------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open Project...", command=self._open_project)
        file_menu.add_command(label="Export...", command=self._export)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        self._extended = tk.BooleanVar(value=self.project.config.ui_mode == "extended")
        view_menu.add_checkbutton(
            label="Extended mode", variable=self._extended, command=self._mode_changed
        )
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Privacy statement", command=self._show_privacy)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_banner(self) -> None:
        banner = ttk.Frame(self.root, padding=8)
        text = FIRST_LAUNCH_BANNER.format(path=self.project.dir)
        ttk.Label(banner, text=text, wraplength=900, justify="left").pack(side="left")
        ttk.Button(banner, text="X", width=3, command=banner.destroy).pack(side="right")
        banner.pack(fill="x")

    def _build_toolbar(self) -> None:
        self.toolbar = ttk.Frame(self.root, padding=4)
        self.toolbar.pack(fill="x")
        self._toolbar_buttons: dict[str, ttk.Button] = {}
        self._render_toolbar()

    def _render_toolbar(self) -> None:
        for child in self.toolbar.winfo_children():
            child.destroy()
        extended = self._extended.get()
        # Sec. 9.3: basic = Add files | Run all | Report | Export | Help
        buttons = [("Add files", self._add_files), ("Run all", lambda: self._run(rerun=False))]
        if extended:
            buttons += [
                ("Re-run all", lambda: self._run(rerun=True)),
                ("Update stale", lambda: self._run(rerun=False)),
            ]
        buttons += [
            ("Report", self._show_report),
            ("Export", self._export),
            ("? Help", self._show_privacy),
        ]
        self._toolbar_buttons = {}
        for label, command in buttons:
            button = ttk.Button(self.toolbar, text=label, command=command)
            button.pack(side="left", padx=2)
            self._toolbar_buttons[label] = button
        self._update_report_button()

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.grid_view = GridView(self.notebook, self.project.repo, self.project.store)
        self.report_view = ReportView(self.notebook, self.project.repo)
        self.notebook.add(self.grid_view, text="Grid")
        self.notebook.add(self.report_view, text="Report")
        self.notebook.pack(fill="both", expand=True)

    # -- state ------------------------------------------------------------------

    def refresh(self) -> None:
        self.grid_view.reload(
            metric_columns(self.registry, self._extended.get()),
            show_artefacts=self._extended.get(),
        )
        self._update_report_button()
        self._set_status("Ready")

    def _update_report_button(self) -> None:
        """Disabled until one successful run exists (ADR-0016)."""
        has_data = (
            self.project.repo.conn.execute(
                "SELECT COUNT(*) FROM v_current_metrics WHERE status='ok' AND source_id IN"
                " (SELECT id FROM sources WHERE kind='local')"
            ).fetchone()[0]
            > 0
        )
        button = self._toolbar_buttons.get("Report")
        if button:
            button.configure(state="normal" if has_data else "disabled")

    def _set_status(self, prefix: str) -> None:
        self.status.configure(text=f"{prefix} | {self.grid_view.status_text()}")

    def _mode_changed(self) -> None:
        self.project.config.ui_mode = "extended" if self._extended.get() else "basic"
        save_config(self.project.dir, self.project.config)
        self._render_toolbar()
        self.refresh()

    # -- actions -----------------------------------------------------------------

    def _add_files(self) -> None:
        added = dialogs.add_files_flow(self.root, self.project)
        if added:
            self.refresh()
            self._set_status(f"Added {added} theses - click Run all")

    def _run(self, rerun: bool) -> None:
        if self._run_thread and self._run_thread.is_alive():
            messagebox.showinfo("Run", "A run is already in progress.", parent=self.root)
            return
        self._set_status("Planning...")
        self._show_cancel_control()
        self._run_thread = threading.Thread(
            target=self._run_worker, args=(rerun,), daemon=True
        )
        self._run_thread.start()

    def _show_cancel_control(self) -> None:
        """Swap the run toolbar for a single Cancel button while a run is in
        progress (skip-pending cancellation, ADR-0013). The normal toolbar is
        restored on RunCompleted/RunCancelled by ``_render_toolbar``."""
        for child in self.toolbar.winfo_children():
            child.destroy()
        self._toolbar_buttons = {}
        button = ttk.Button(self.toolbar, text="Cancel run", command=self._cancel_run)
        button.pack(side="left", padx=2)
        self._toolbar_buttons["Cancel run"] = button

    def _cancel_run(self) -> None:
        """Tell the active runner to stop submitting new theses. In-flight
        theses finish; the toolbar is restored when the run reports done."""
        runner = self._runner
        if runner is not None:
            runner.cancel()
        button = self._toolbar_buttons.get("Cancel run")
        if button:
            button.configure(state="disabled")
        self._set_status("Cancelling - finishing in-flight theses...")

    def _run_worker(self, rerun: bool) -> None:
        """Background run: own the DB connection here, since sqlite3
        connections are thread-affine (#27). Events still marshal to the
        Tk thread via the queue drained by ``root.after``."""
        bus = events.EventBus()
        bus.subscribe_all(self._event_queue.put)
        repo = self.project.connect()
        try:
            self._runner = self.project.make_runner(repo=repo, bus=bus)
            plan = self._runner.plan(rerun=rerun)
            if plan.pair_count == 0:
                self._event_queue.put(events.RunCompleted(None))
                return
            self._runner.execute(plan)
        finally:
            self._runner = None
            repo.conn.close()

    def _drain_events(self) -> None:
        try:
            while True:
                event = self._event_queue.get_nowait()
                if isinstance(event, events.ModuleCompleted):
                    self._set_status(
                        f"Running... thesis {event.thesis_id}: {event.module_name} {event.status}"
                    )
                elif isinstance(event, events.ThesisCompleted):
                    self.grid_view.reload(
                        metric_columns(self.registry, self._extended.get()),
                        show_artefacts=self._extended.get(),
                    )
                elif isinstance(event, (events.RunCompleted, events.RunCancelled)):
                    self._render_toolbar()  # restore normal run controls
                    self.refresh()
                    cancelled = isinstance(event, events.RunCancelled)
                    self._set_status("Run cancelled" if cancelled else "Run finished")
                    # Sec. 9.8.2: re-render while Report tab is active
                    if self.notebook.index("current") == 1:
                        self.report_view.render()
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain_events)

    def _show_report(self) -> None:
        self.report_view.render()
        self.notebook.select(self.report_view)

    def _export(self) -> None:
        dialogs.export_flow(self.root, self.project)

    def _open_project(self) -> None:
        from tkinter import filedialog

        from tta.ui.tk.recent import remember_project

        chosen = filedialog.askdirectory(parent=self.root, title="Open project folder")
        if not chosen:
            return
        remember_project(chosen)
        messagebox.showinfo(
            "Open Project", "The project opens on next start.", parent=self.root
        )

    def _show_privacy(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Privacy statement")
        window.geometry("800x600")
        text = tk.Text(window, wrap="word")
        text.insert("1.0", render_report_md())
        text.configure(state="disabled")
        scrollbar = ttk.Scrollbar(window, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)

    def _show_about(self) -> None:
        import tta

        messagebox.showinfo(
            "About",
            f"Thesis Text Analyzer {tta.__version__}\n"
            "Data Science Project Group SS26 - FH Wedel",
            parent=self.root,
        )

    def run(self) -> None:
        self.root.mainloop()
