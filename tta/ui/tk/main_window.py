"""Main window (Sec. 9.2): menu bar, toolbar, Grid/Report tabs, status line.

Runs execute on a background thread; domain events are marshalled into
the Tk loop via a queue drained by ``root.after`` (ADR-0002 invariant 3).
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from tta.core import events, progress
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
    def __init__(
        self, project: Project, first_launch: bool = False, notice: str | None = None
    ):
        self.project = project
        # A startup notice means the remembered project could not be opened
        # and the default one was used instead (#41, SDD Sec. 5.6.1). It
        # shares the banner area with the first-launch text.
        self._notice = notice
        self.registry = default_registry()
        self.root = tk.Tk()
        self.root.title(f"Thesis Text Analyzer - {project.dir}")
        self.root.geometry("1100x700")
        self._event_queue: queue.Queue = queue.Queue()
        self._run_thread: threading.Thread | None = None
        self._runner = None
        # Live progress + size-weighted ETA (#39); widgets live in the run area
        # next to the Cancel control, state is reset between runs.
        self._progress_bar: ttk.Progressbar | None = None
        self._progress_label: ttk.Label | None = None
        self._reset_progress_state()

        self._build_menu()
        if first_launch or notice:
            self._build_banner(first_launch=first_launch, notice=notice)
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

    def _build_banner(self, first_launch: bool = True, notice: str | None = None) -> None:
        banner = ttk.Frame(self.root, padding=8)
        lines = []
        if notice:
            lines.append(notice)
        if first_launch:
            lines.append(FIRST_LAUNCH_BANNER.format(path=self.project.dir))
        text = "\n\n".join(lines)
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
        """Swap the run toolbar for a Cancel button plus an inline determinate
        progress bar + ETA label while a run is in progress (skip-pending
        cancellation, ADR-0013; live progress, #39). The normal toolbar is
        restored on RunCompleted/RunCancelled by ``_render_toolbar``."""
        for child in self.toolbar.winfo_children():
            child.destroy()
        self._toolbar_buttons = {}
        button = ttk.Button(self.toolbar, text="Cancel run", command=self._cancel_run)
        button.pack(side="left", padx=2)
        self._toolbar_buttons["Cancel run"] = button
        self._progress_bar = ttk.Progressbar(
            self.toolbar, mode="determinate", length=240, maximum=1, value=0
        )
        self._progress_bar.pack(side="left", padx=(12, 4))
        self._progress_label = ttk.Label(self.toolbar, text="Planning...")
        self._progress_label.pack(side="left", padx=2)

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
                if isinstance(event, events.RunStarted):
                    self._begin_progress(event.plan)
                elif isinstance(event, events.ModuleCompleted):
                    self._advance_progress(event)
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
                    self._reset_progress_state()  # drop the (now destroyed) bar refs
                    self.refresh()
                    cancelled = isinstance(event, events.RunCancelled)
                    self._set_status("Run cancelled" if cancelled else "Run finished")
                    # Sec. 9.8.2: re-render while Report tab is active
                    if self.notebook.index("current") == 1:
                        self.report_view.render()
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain_events)

    # -- live progress + size-weighted ETA (#39) --------------------------------

    def _reset_progress_state(self) -> None:
        """Clear the per-run estimator state. The progress widgets are owned by
        the run toolbar and destroyed by ``_render_toolbar``, so only the
        references are dropped here."""
        self._progress_bar = None
        self._progress_label = None
        self._run_total = 0
        self._run_done = 0
        self._run_remaining: list[tuple[int, str]] = []  # (thesis_id, module_name)
        self._run_sizes: dict[int, int] = {}
        self._run_rates: dict[str, float] = {}  # historical ms/byte at run start
        self._run_obs: dict[str, list[float]] = {}  # module -> [sum_ms, sum_bytes]
        self._run_start = 0.0

    def _begin_progress(self, plan) -> None:
        """Initialise the determinate bar + ETA from the run plan (RunStarted).

        The per-module historical rates and thesis sizes come from the main-
        thread repository (reads only; the runner writes on its own connection,
        #27). In-run observations are folded in as pairs complete."""
        self._run_total = plan.pair_count
        self._run_done = 0
        self._run_remaining = [
            (tp.thesis.id, pm.name) for tp in plan.theses for pm in tp.modules
        ]
        self._run_sizes = self.project.repo.thesis_sizes()
        self._run_rates = self.project.repo.module_duration_stats()
        self._run_obs = {}
        self._run_start = time.monotonic()
        if self._progress_bar is not None:
            self._progress_bar.configure(maximum=max(self._run_total, 1), value=0)
        self._render_progress()

    def _advance_progress(self, event: events.ModuleCompleted) -> None:
        """Advance one (thesis x module) pair on ModuleCompleted and recompute
        the ETA, folding this module's observed cost into the in-run rate."""
        pair = (event.thesis_id, event.module_name)
        if pair in self._run_remaining:
            self._run_remaining.remove(pair)
        self._run_done += 1
        size = self._run_sizes.get(event.thesis_id, 0)
        if event.status == "ok" and event.duration_ms and size > 0:
            acc = self._run_obs.setdefault(event.module_name, [0.0, 0.0])
            acc[0] += event.duration_ms
            acc[1] += size
        if self._progress_bar is not None:
            self._progress_bar.configure(value=self._run_done)
        self._render_progress()

    def _merged_rates(self) -> dict[str, float]:
        """History rates overlaid with the rate observed so far this run
        (mean ms/byte over this run's ok pairs of each module)."""
        rates = dict(self._run_rates)
        for module, (sum_ms, sum_bytes) in self._run_obs.items():
            if sum_bytes > 0:
                rates[module] = sum_ms / sum_bytes
        return rates

    def _render_progress(self) -> None:
        if self._progress_label is None:
            return
        remaining = [(module, self._run_sizes.get(tid, 0)) for tid, module in self._run_remaining]
        est = progress.estimate(
            self._run_done,
            self._run_total,
            remaining,
            self._merged_rates(),
            time.monotonic() - self._run_start,
        )
        if not est.total:
            text = ""
        elif est.eta_seconds is None:
            text = f"{est.done}/{est.total} pairs - estimating..."
        else:
            text = f"{est.done}/{est.total} pairs - ~{progress.format_eta(est.eta_seconds)} left"
        self._progress_label.configure(text=text)

    def _show_report(self) -> None:
        self.report_view.render()
        self.notebook.select(self.report_view)

    def _export(self) -> None:
        dialogs.export_flow(self.root, self.project)

    def _open_project(self) -> None:
        from pathlib import Path
        from tkinter import filedialog

        from tta.core.project import DB_FILENAME, remember_project

        chosen = filedialog.askdirectory(parent=self.root, title="Open project folder")
        if not chosen:
            return
        target = Path(chosen)
        try:
            remember_project(target)
        except OSError as exc:
            messagebox.showerror(
                "Open Project",
                f"Could not remember {target}:\n{type(exc).__name__}: {exc}",
                parent=self.root,
            )
            return
        # An empty folder is a legitimate choice - the first-launch banner
        # sends the user here to pick a different location - so say plainly
        # that the project will be created there (#41, SDD Sec. 9.7).
        if (target / DB_FILENAME).exists():
            detail = "The project opens on next start."
        else:
            detail = "That folder is not a project yet; it is created there on next start."
        messagebox.showinfo("Open Project", f"{target}\n\n{detail}", parent=self.root)

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
