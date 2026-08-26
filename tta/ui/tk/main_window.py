"""Main window (Sec. 9.2): menu bar, toolbar, thesis grid, status line.

Runs execute on a background thread; domain events are marshalled into
the Tk loop via a queue drained by ``root.after`` (ADR-0002 invariant 3).
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from tta.core import events, progress, report
from tta.core.config import save_config
from tta.core.modules.registry import default_registry
from tta.core.privacy_metadata import render_report_md
from tta.core.project import Project
from tta.ui.tk import dialogs
from tta.ui.tk.columns import metric_columns
from tta.ui.tk.grid import GridView

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
        # Live progress + size-weighted ETA (#39); widgets live in the run area
        # next to the Cancel control, state is reset between runs.
        self._progress_bar: ttk.Progressbar | None = None
        self._progress_label: ttk.Label | None = None
        self._reset_progress_state()

        self._build_menu()
        if first_launch:
            self._build_banner()
        self._build_toolbar()
        self._build_grid()
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
        # Sec. 9.7: basic = Add files | Add folder | Run all | Report | Export | Help
        buttons = [
            ("Add files", self._add_files),
            ("Add folder", self._add_folder),  # recursive folder add (#62)
            ("Run all", lambda: self._run(rerun=False)),
        ]
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

    def _build_grid(self) -> None:
        # No notebook: the report is a generated HTML file opened in the
        # browser, so the grid owns the whole window (Sec. 9.8, ADR-0016 rev. 2).
        self.grid_view = GridView(self.root, self.project.repo, self.project.store)
        self.grid_view.pack(fill="both", expand=True)

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
        self._after_add(dialogs.add_files_flow(self.root, self.project))

    def _add_folder(self) -> None:
        """Add every PDF beneath a chosen folder, recursively (#62, Sec. 9.7).
        The dialog confirms the count before anything is written."""
        self._after_add(dialogs.add_folder_flow(self.root, self.project))

    def _after_add(self, added: int) -> None:
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
                elif isinstance(event, events.ModuleStarted):
                    self._start_progress_pair(event)
                elif isinstance(event, events.ModuleCompleted):
                    self._advance_progress(event)
                    self._set_status(
                        f"Running... thesis {self._thesis_ordinal(event.thesis_id)}: "
                        f"{event.module_name} {event.status}"
                    )
                elif isinstance(event, events.ThesisCompleted):
                    self._run_theses_done += 1
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
                    # Sec. 9.8.3: offer the report (#70). The tab that used to
                    # re-render itself here is gone (ADR-0016 rev. 2).
                    self._maybe_offer_report(event, cancelled)
        except queue.Empty:
            pass
        # #54: re-render every tick while a run is live. The ETA used to be
        # recomputed only on ModuleCompleted, so it froze between events and
        # the in-flight pair got no credit for the seconds already burned - it
        # could not count down. The estimate itself stays a pure function; the
        # clock is read here and passed in.
        if self._progress_label is not None:
            self._render_progress()
        self.root.after(POLL_MS, self._drain_events)

    # -- live progress + size-weighted ETA (#39, #54, #58) ----------------------

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
        # module -> (intercept_ms, slope_ms_per_byte) fitted from history at run
        # start; absent modules fall back to their ADR-0015 prior (#54)
        self._run_costs: dict[str, tuple[float, float]] = {}
        # module -> this run's (size_bytes, duration_ms) observations, blended
        # into history by sample weight rather than overwriting it (#54)
        self._run_obs: dict[str, list[tuple[float, float]]] = {}
        # (thesis_id, module_name) -> monotonic start of a pair still running;
        # its elapsed time is credited against the pair's cost so the ETA decays
        self._run_in_flight: dict[tuple[int, str], float] = {}
        self._run_workers = 1  # Runner.workers: theses run concurrently (#54)
        self._run_theses_total = 0  # len(plan.theses) - the n/N denominator (#58)
        self._run_theses_done = 0  # ThesisCompleted count (#58)
        self._run_thesis_ordinals: dict[int, int] = {}  # thesis id -> 1-based plan position
        self._eta_shown: float | None = None  # damped ETA actually on screen

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
        self._run_costs = self.project.repo.module_duration_stats()
        self._run_obs = {}
        self._run_in_flight = {}
        # Theses run concurrently, modules within a thesis serially, so the ETA
        # needs the worker count to divide by (#54, ADR-0013). The live runner
        # is authoritative (it resolved the default); the configured value is
        # the fallback should the run already have torn down.
        runner_workers = getattr(self._runner, "workers", None)
        self._run_workers = max(1, runner_workers or self.project.config.workers or 1)
        self._run_theses_total = len(plan.theses)
        self._run_theses_done = 0
        self._run_thesis_ordinals = {
            tp.thesis.id: index for index, tp in enumerate(plan.theses, start=1)
        }
        self._eta_shown = None
        if self._progress_bar is not None:
            self._progress_bar.configure(maximum=max(self._run_total, 1), value=0)
        self._render_progress()

    def _thesis_ordinal(self, thesis_id: int) -> str:
        """Ordinal "n/N" for the status line (#58). The raw ``thesis_id`` used to be
        printed here; it is the DB primary key, so after any delete or
        content-dedup fold it reads like a counter without being one."""
        ordinal = self._run_thesis_ordinals.get(thesis_id)
        if ordinal is None or self._run_theses_total <= 0:
            return f"#{thesis_id}"
        return f"{ordinal}/{self._run_theses_total}"

    def _start_progress_pair(self, event: events.ModuleStarted) -> None:
        """Remember when a pair started so the estimator can credit the seconds
        already burned against its cost - what makes the ETA count down (#54)."""
        self._run_in_flight[(event.thesis_id, event.module_name)] = time.monotonic()
        self._render_progress()

    def _advance_progress(self, event: events.ModuleCompleted) -> None:
        """Advance one (thesis x module) pair on ModuleCompleted and recompute
        the ETA, recording this module's observed cost as a sample."""
        pair = (event.thesis_id, event.module_name)
        if pair in self._run_remaining:
            self._run_remaining.remove(pair)
        self._run_in_flight.pop(pair, None)
        self._run_done += 1
        size = self._run_sizes.get(event.thesis_id, 0)
        if event.status == "ok" and event.duration_ms and size > 0:
            self._run_obs.setdefault(event.module_name, []).append(
                (float(size), float(event.duration_ms))
            )
        if self._progress_bar is not None:
            self._progress_bar.configure(value=self._run_done)
        self._render_progress()

    def _merged_costs(self) -> dict[str, tuple[float, float]]:
        """Per-module (intercept, slope) from history with this run's own
        observations blended in **by sample weight** (#54). The old code
        overwrote history with the in-run mean ms/byte the moment one pair
        landed. A module with neither history nor observations stays absent so
        the estimator applies its ADR-0015 prior."""
        costs = dict(self._run_costs)
        for module, samples in self._run_obs.items():
            blended = progress.blend_cost(
                costs.get(module), progress.fit_cost(samples), len(samples)
            )
            if blended is not None:
                costs[module] = blended
        return costs

    def _render_progress(self) -> None:
        if self._progress_label is None:
            return
        now = time.monotonic()
        remaining = [
            (tid, module, self._run_sizes.get(tid, 0)) for tid, module in self._run_remaining
        ]
        in_flight = {pair: max(now - started, 0.0) for pair, started in self._run_in_flight.items()}
        est = progress.estimate(
            self._run_done,
            self._run_total,
            remaining,
            self._merged_costs(),
            in_flight=in_flight,
            workers=self._run_workers,
            theses_total=self._run_theses_total,
            theses_done=self._run_theses_done,
        )
        self._eta_shown = progress.damp_eta(self._eta_shown, est.eta_seconds)
        self._progress_label.configure(text=self._progress_text(est, self._eta_shown))

    def _progress_text(self, est: progress.Progress, eta: float | None) -> str:
        """Label for the run progress bar (SDD Sec. 9.2, #58).

        Theses are the primary figure - "(thesis x module) pairs" means nothing
        to the professor persona. The pair count is a power-user detail and
        appears only in extended mode."""
        if not est.total:
            return ""
        if est.theses_total:
            head = f"thesis {est.theses_done}/{est.theses_total}"
        else:  # no plan thesis count (shouldn't happen in a real run)
            head = f"{est.done}/{est.total} pairs"
        tail = "estimating..." if eta is None else f"~{progress.format_eta(eta)} left"
        text = f"{head} - {tail}"
        if est.theses_total and self._extended.get():
            text += f" - {est.done}/{est.total} pairs"
        return text

    #: the open post-run prompt, if any (#70). Class-level so the attribute
    #: exists before the first run finishes.
    _report_prompt_window = None

    def _show_report(self) -> None:
        """Generate the stand-alone HTML report and open it in the browser
        (Sec. 9.8, ADR-0016 rev. 2). Core renders the document as a string;
        writing the file and launching the browser are the adapter's job."""
        path = self._write_report()
        if path is None:
            return
        self._set_status(f"Report written to {path}")
        webbrowser.open(path.as_uri())

    def _write_report(self) -> Path | None:
        """Write `<project>/reports/report-<date>.html`, overwriting a
        same-day file. Returns None (after an error dialog) if it could not
        be written."""
        path = report.default_report_path(self.project.dir)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report.render_html(report.collect(self.project.repo)), "utf-8")
        except OSError as exc:
            messagebox.showerror(
                "Report", f"Could not write the report:\n{exc}", parent=self.root
            )
            return None
        return path

    def _maybe_offer_report(self, event, cancelled: bool) -> None:
        """Post-run offer (#70, Sec. 9.8.3). The policy is core's - a
        cancelled or all-errored run produced nothing to look at - and this
        only renders the decision."""
        summary = getattr(event, "summary", None)
        decision = report.should_offer_report(
            self.project.config.open_report_after_run,
            cancelled=cancelled,
            ok=getattr(summary, "ok", 0) or 0,
        )
        if decision == "open":
            self._show_report()
        elif decision == "ask":
            self._report_prompt()

    def _report_prompt(self) -> None:
        """Non-modal "open the report?" prompt: no ``grab_set``, so the grid
        stays usable. "Don't ask again" persists the answer to tta.toml as
        `ui.open_report_after_run` = always/never (#70)."""
        existing = self._report_prompt_window
        if existing is not None and existing.winfo_exists():
            existing.lift()  # one prompt at a time, however many runs finish
            return
        window = tk.Toplevel(self.root)
        window.title("Report")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="The run finished. Open the report for this project now?",
            wraplength=360,
            justify="left",
        ).pack(anchor="w")
        remember = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Don't ask again", variable=remember).pack(
            anchor="w", pady=(8, 12)
        )

        def answer(open_it: bool) -> None:
            if remember.get():
                self.project.config.open_report_after_run = "always" if open_it else "never"
                save_config(self.project.dir, self.project.config)
            self._report_prompt_window = None
            window.destroy()
            if open_it:
                self._show_report()

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e")
        ttk.Button(buttons, text="Not now", command=lambda: answer(False)).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(buttons, text="Open report", command=lambda: answer(True)).pack(side="left")
        self._report_prompt_window = window

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
