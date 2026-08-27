"""`tta` command line - first-class primary adapter (ADR-0003).

Output rules: human-readable tables on stdout by default; `--format
{human,json,csv}` for machine-readable output (JSON is the scripting
contract); logs and progress go to stderr; exit codes follow sysexits
(0 ok, 1 partial, 64 misuse, 65 data error, 70 internal).
"""

from __future__ import annotations

import csv
import json
import re
import signal
import sys
import traceback
import webbrowser
from datetime import date
from importlib import resources
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

import tta
from tta.core import events
from tta.core import i18n
from tta.core import privacy_metadata
from tta.core.config import load_config
from tta.core.db import migrator
from tta.core.discovery import collect_pdfs
from tta.core.export import ExportPolicy, export_database, export_profiling
from tta.core.i18n import _
from tta.core.importer import ImportError_, import_export
from tta.core.modules.registry import default_registry
from tta.core.project import DB_FILENAME, Project
from tta.core import report

stdout = Console()
stderr = Console(stderr=True)

EX_PARTIAL = 1
EX_INTERNAL = 70

click.UsageError.exit_code = 64  # sysexits EX_USAGE (click default is 2)


class DataError(click.ClickException):
    exit_code = 65  # sysexits EX_DATAERR


@click.group(name="tta")
@click.option(
    "--project",
    "-C",
    "project_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=".",
    help=_("Project directory (default: current directory)."),
)
@click.pass_context
def cli(ctx: click.Context, project_dir: Path) -> None:
    """Thesis Text Analyzer."""
    # SDD Sec. 9.6 / ADR-0020: [ui] locale in the project's tta.toml, else
    # TTA_LOCALE, else German. load_config tolerates a missing file, so this
    # also works before `tta db init`. Option --help text is the one thing
    # this cannot reach: click resolved it when this module was imported.
    i18n.install(config_locale=load_config(project_dir).ui_locale)
    ctx.obj = project_dir


def open_project(ctx: click.Context, create: bool = False) -> Project:
    try:
        return Project.open(ctx.obj, create=create)
    except FileNotFoundError as exc:
        raise DataError(str(exc)) from exc


# -- version -------------------------------------------------------------


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["human", "json"]), default="human")
def version(fmt: str) -> None:
    """App version + module versions (QA-REPRO)."""
    modules = {m.spec.name: m.spec.version for m in default_registry().in_topological_order()}
    if fmt == "json":
        click.echo(json.dumps({"app": tta.__version__, "modules": modules}, indent=2))
        return
    stdout.print(f"tta {tta.__version__}")
    for name, mod_version in modules.items():
        stdout.print(f"  {name} {mod_version}")


# -- doctor --------------------------------------------------------------


_STATUS_GLYPH = {"ok": "[ok]", "warn": "[!]", "fail": "[x]"}


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["human", "json"]), default="human")
@click.pass_context
def doctor(ctx: click.Context, fmt: str) -> None:
    """Dump diagnostics for a support / bug report (#42, ADR-0003).

    Read-only: never migrates, creates or repairs anything. Exits 1 if any
    check fails, so `tta doctor >/dev/null || ...` works in a script.
    """
    # Imported here, not at module scope: `doctor` pulls in nltk/textstat/
    # langdetect for its offline self-check, ~0.6 s that every other command
    # (`version`, `list`, `--help`) would otherwise pay. Same reason
    # extract_pymupdf.py defers `fitz`.
    from tta.core import doctor as doctor_core

    diag = doctor_core.collect(ctx.obj)
    if fmt == "json":
        click.echo(json.dumps(diag.to_dict(), indent=2))
    else:
        # markup/highlight off throughout: check names and details carry square
        # brackets ("[ok]", "nltk.punkt_tab[en]") that rich would eat as tags
        def line(text: str) -> None:
            stdout.print(text, markup=False, highlight=False)

        database = diag.project["database"]
        line(f"tta {diag.app['version']} (frozen={diag.app['frozen']})")
        line(
            f"  python {diag.runtime['python']} "
            f"{diag.runtime['python_implementation']} on {diag.runtime['platform']}"
        )
        line(f"  project {diag.project['dir']}")
        line(
            f"  database {database['path']} "
            f"(schema {database.get('schema_version')}, "
            f"integrity {database.get('integrity_check', 'n/a')})"
        )
        line(
            f"  config {diag.config['path']} "
            f"(present={diag.config['exists']}, workers={diag.config['workers']}, "
            f"ui_mode={diag.config['ui_mode']})"
        )
        line(f"  modules {len(diag.modules)} registered")
        for name, mod_version in diag.modules.items():
            line(f"    {name} {mod_version}")
        line(_("checks:"))
        for check in diag.checks:
            glyph = _STATUS_GLYPH.get(check.status, check.status)
            line(f"  {glyph} {check.name}: {check.detail}")
        line(_("overall: {status}").format(status=diag.status))
    if diag.failed:
        names = ", ".join(c.name for c in diag.failed)
        stderr.print(_("failing checks: {names}").format(names=names))
        ctx.exit(EX_PARTIAL)


# -- db ------------------------------------------------------------------


@cli.group()
def db() -> None:
    """Initialise / migrate / vacuum the project database."""


@db.command("init")
@click.pass_context
def db_init(ctx: click.Context) -> None:
    """Create (or migrate) the project in --project."""
    with open_project(ctx, create=True) as project:
        stdout.print(
            _("project ready at {path}").format(path=project.dir.resolve() / DB_FILENAME)
        )


@db.command("migrate")
@click.pass_context
def db_migrate(ctx: click.Context) -> None:
    """Apply pending schema migrations (with defensive backup)."""
    project_dir: Path = ctx.obj
    db_path = project_dir / DB_FILENAME
    if not db_path.exists():
        raise DataError(
            _("no project at {path} - run `tta db init` first").format(path=project_dir)
        )
    applied = migrator.migrate(db_path)
    stdout.print(
        _("applied migrations: {versions}").format(versions=applied)
        if applied
        else _("schema is up to date")
    )


@db.command("vacuum")
@click.pass_context
def db_vacuum(ctx: click.Context) -> None:
    """Compact the database file."""
    with open_project(ctx) as project:
        project.repo.conn.execute("VACUUM")
    stdout.print(_("vacuumed"))


# -- list ------------------------------------------------------------------


@cli.command("list")
@click.option("--format", "fmt", type=click.Choice(["human", "json", "csv"]), default="human")
@click.pass_context
def list_theses(ctx: click.Context, fmt: str) -> None:
    """List known theses with their analysis status."""
    with open_project(ctx) as project:
        theses = project.repo.list_theses(local_only=True, include_excluded=True)
        latest = project.repo.latest_runs()
        module_count = len(default_registry().names())
        # thesis type is the detected `thesis_type` metric now, not a column
        # (ADR-0019, #9); blank until the thesis has been analysed
        detected_type = {
            row["thesis_id"]: row["value_text"]
            for row in project.repo.current_metrics()
            if row["metric_name"] == "thesis_type"
        }
        rows = []
        for thesis in theses:
            counts = {"ok": 0, "na": 0, "error": 0}
            for (thesis_id, _module), run in latest.items():
                if thesis_id == thesis.id:
                    counts[run["status"]] += 1
            rows.append(
                {
                    "id": thesis.id,
                    "filename": thesis.pdf_filename,
                    "type": detected_type.get(thesis.id, ""),
                    "excluded": thesis.excluded,
                    "ok": counts["ok"],
                    "na": counts["na"],
                    "error": counts["error"],
                    "missing": module_count - sum(counts.values()),
                }
            )
    if fmt == "json":
        click.echo(json.dumps(rows, indent=2))
    elif fmt == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]) if rows else ["id"])
        writer.writeheader()
        writer.writerows(rows)
    else:
        table = Table(title=_("{count} theses").format(count=len(rows)))
        # Column headers are display text; the JSON/CSV field names above are
        # the machine contract and stay English (ADR-0020).
        for column in (
            _("id"), _("filename"), _("type"), _("status"), _("excluded")
        ):
            table.add_column(column)
        for row in rows:
            status = _("{ok} ok | {na} na | {error} err | {missing} todo").format(
                ok=row["ok"], na=row["na"], error=row["error"], missing=row["missing"]
            )
            table.add_row(
                str(row["id"]), row["filename"], row["type"], status,
                _("yes") if row["excluded"] else "",
            )
        stdout.print(table)


# -- exclude / include -------------------------------------------------------


@cli.command()
@click.argument("thesis_id", type=int)
@click.option(
    "--yes", "-y", is_flag=True,
    help=_("Skip the confirmation prompt (for scripts)."),
)
@click.pass_context
def exclude(ctx: click.Context, thesis_id: int, yes: bool) -> None:
    """Exclude thesis THESIS_ID from analysis and exports (US-PROF-EXCLUDE).

    Mirrors the GUI Excluded checkbox (ADR-0003, #11). If the thesis has
    already been analysed, its cached analysis is scrubbed: the on-disk
    artefacts (raw text, tokens, PDF metadata) plus its metric and run-history
    rows are deleted from this machine (ADR-0006 rev. 5). This is destructive
    and irreversible; the source PDF is not touched. Excluding before a run
    simply prevents any analysis from ever being cached.
    """
    with open_project(ctx) as project:
        try:
            project.repo.get_thesis(thesis_id)
        except KeyError as exc:
            raise DataError(str(exc)) from exc
        has_analysis = bool(
            project.repo.conn.execute(
                "SELECT 1 FROM module_runs WHERE thesis_id = ? LIMIT 1", (thesis_id,)
            ).fetchone()
        )
        if has_analysis and not yes:
            confirmed = click.confirm(
                _(
                    "Exclude thesis {thesis_id} and permanently delete its cached "
                    "analysis from this machine (artefacts, metrics, run history)? "
                    "This is destructive and cannot be undone. The source PDF is "
                    "not touched."
                ).format(thesis_id=thesis_id),
            )
            if not confirmed:
                stdout.print(_("aborted; no changes made"))
                return
        project.repo.set_excluded(thesis_id, True)
        scrub_error: OSError | None = None
        if has_analysis:
            try:
                project.repo.purge_analysis(thesis_id, store=project.store)
            except OSError as exc:
                scrub_error = exc
        artefacts_dir = project.store.resolve(f"artefacts/{thesis_id}")
    if not has_analysis:
        stdout.print(_("excluded thesis {thesis_id}").format(thesis_id=thesis_id))
    elif scrub_error is None:
        stdout.print(
            _("excluded thesis {thesis_id}; cached analysis scrubbed").format(
                thesis_id=thesis_id
            )
        )
    else:
        # DB analysis removed, but the local files could not be fully deleted;
        # they never leave the machine (ADR-0007) - warn rather than claim a
        # clean scrub, and exit partial so scripts notice (#11 review).
        stderr.print(
            _(
                "excluded thesis {thesis_id}; analysis records removed, but some "
                "cached files could not be deleted: {folder} ({error}). "
                "They are never exported; delete that folder manually to remove "
                "them."
            ).format(thesis_id=thesis_id, folder=artefacts_dir, error=scrub_error)
        )
        ctx.exit(EX_PARTIAL)


@cli.command()
@click.argument("thesis_id", type=int)
@click.pass_context
def include(ctx: click.Context, thesis_id: int) -> None:
    """Re-include a previously excluded thesis (clears the excluded flag).

    The thesis becomes eligible again and re-runs as "missing" on the next
    run (ADR-0003, #11). Analysis scrubbed at exclude time is not restored;
    re-run to recompute it.
    """
    with open_project(ctx) as project:
        try:
            project.repo.get_thesis(thesis_id)
        except KeyError as exc:
            raise DataError(str(exc)) from exc
        project.repo.set_excluded(thesis_id, False)
    stdout.print(_("included thesis {thesis_id}").format(thesis_id=thesis_id))


@cli.command()
@click.argument("thesis_id", type=int)
@click.option(
    "--yes", "-y", is_flag=True,
    help=_("Skip the confirmation prompt (for scripts)."),
)
@click.pass_context
def remove(ctx: click.Context, thesis_id: int, yes: bool) -> None:
    """Remove thesis THESIS_ID from the project entirely (#63).

    The harder version of `exclude`, for a PDF added by accident. Exclude
    keeps the thesis row so its identity is remembered and it is never
    silently re-analysed; remove deletes the row as well, because a mis-added
    thesis has no identity worth keeping - so the same PDF can afterwards be
    added again as a fresh thesis. Its cached analysis (artefacts, metrics,
    run history) goes with it. Destructive and irreversible; nothing restores
    it and there is no row left to `include`. The source PDF is not touched.
    """
    with open_project(ctx) as project:
        try:
            thesis = project.repo.get_thesis(thesis_id)
        except KeyError as exc:
            raise DataError(str(exc)) from exc
        if not yes:
            confirmed = click.confirm(
                _(
                    "Remove thesis {thesis_id} ({filename}) from the project and "
                    "permanently delete its cached analysis from this machine "
                    "(artefacts, metrics, run history)? The thesis is forgotten "
                    "entirely - this cannot be undone, and the source PDF is not "
                    "touched."
                ).format(thesis_id=thesis_id, filename=thesis.pdf_filename),
            )
            if not confirmed:
                stdout.print(_("aborted; no changes made"))
                return
        remove_error: OSError | None = None
        try:
            project.repo.delete_thesis(thesis_id, store=project.store)
        except OSError as exc:
            remove_error = exc
        artefacts_dir = project.store.resolve(f"artefacts/{thesis_id}")
    if remove_error is None:
        stdout.print(_("removed thesis {thesis_id}").format(thesis_id=thesis_id))
    else:
        # The rows are gone (DB-first ordering) but the local files are not;
        # they never leave the machine (ADR-0007) - warn rather than claim a
        # clean removal, and exit partial so scripts notice.
        stderr.print(
            _(
                "removed thesis {thesis_id}; database rows deleted, but some cached "
                "files could not be deleted: {folder} ({error}). "
                "They are never exported; delete that folder manually to remove "
                "them."
            ).format(thesis_id=thesis_id, folder=artefacts_dir, error=remove_error)
        )
        ctx.exit(EX_PARTIAL)


# -- module ----------------------------------------------------------------


@cli.group()
def module() -> None:
    """List module details (the analysis catalogue)."""


@module.command("list")
@click.option("--format", "fmt", type=click.Choice(["human", "json"]), default="human")
def module_list(fmt: str) -> None:
    """All registered modules in execution order."""
    specs = [m.spec for m in default_registry().in_topological_order()]
    if fmt == "json":
        click.echo(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "version": s.version,
                        "consumes": list(s.consumes),
                        "produces_artefacts": list(s.produces_artefacts),
                        "produces_metrics": list(s.produces_metrics),
                    }
                    for s in specs
                ],
                indent=2,
            )
        )
        return
    table = Table(title=_("module catalogue"))
    for column in (_("module"), _("version"), _("consumes"), _("produces")):
        table.add_column(column)
    for s in specs:
        produces = list(s.produces_artefacts) + list(s.produces_metrics)
        table.add_row(s.name, s.version, ", ".join(s.consumes) or "-", ", ".join(produces))
    stdout.print(table)


@module.command("show")
@click.argument("name")
def module_show(name: str) -> None:
    """Spec details for one module."""
    try:
        mod = default_registry().get(name)
    except KeyError as exc:
        raise click.UsageError(str(exc)) from exc
    s = mod.spec
    stdout.print(f"[bold]{s.name}[/bold] {s.version}")
    doc = (type(mod).__module__ and sys.modules[type(mod).__module__].__doc__) or ""
    if doc:
        stdout.print(doc.strip().split("\n\n")[0])
    stdout.print(
        _("consumes:  {value}").format(
            value=", ".join(s.consumes) or _("- (reads the PDF directly)")
        )
    )
    stdout.print(
        _("artefacts: {value}").format(value=", ".join(s.produces_artefacts) or "-")
    )
    stdout.print(
        _("metrics:   {value}").format(value=", ".join(s.produces_metrics) or "-")
    )


# -- run ---------------------------------------------------------------------


def _collect_pdfs(inputs: tuple[Path, ...]) -> list[Path]:
    """Thin shim over the collector shared with the GUI (#62).

    The walk used to live here, which is why the GUI had no folder add at
    all; it now lives in ``core.discovery`` and is case-insensitive, so a
    ``.PDF`` is no longer skipped.
    """
    return collect_pdfs(inputs)


@cli.command()
@click.argument("inputs", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--module", "-m", "modules", multiple=True,
              help=_("Restrict to specific modules (repeatable; US-PROF-SELECT)."))
@click.option("--rerun", is_flag=True, help=_("Re-run everything regardless of state."))
@click.option("--dry-run", is_flag=True, help=_("Print the plan without executing."))
@click.option("--workers", type=int, default=None,
              help=_("Concurrent theses (default: cores - 1)."))
@click.option("--open-report", is_flag=True,
              help=_("Write the HTML report and open it in a browser when the run "
                     "finishes (off by default; Sec. 9.8.3, #70)."))
@click.option("--format", "fmt", type=click.Choice(["human", "json"]), default="human")
@click.pass_context
def run(ctx, inputs, modules, rerun, dry_run, workers, fmt, open_report) -> None:
    """Add INPUTS (PDF files or directories) and run analyses.

    Without INPUTS, runs on all known theses. Default mode runs missing,
    stale, and previously-errored pairs; --rerun runs everything. Thesis type
    is detected during the run (mod_classify_thesis_type), not set on add.
    """
    with open_project(ctx, create=True) as project:
        pdfs = _collect_pdfs(inputs)
        if pdfs:
            # one batched transaction for the whole INPUTS set, and one summary
            # line instead of one per file (#61, SDD Sec. 8.1)
            added = project.repo.add_theses(pdfs)
            stderr.print(
                _("added {count} theses from {paths} input path(s)").format(
                    count=len(added), paths=len(inputs)
                )
            )

        bus = events.EventBus()
        bus.subscribe(
            events.ModuleCompleted,
            lambda e: stderr.print(
                f"  [thesis {e.thesis_id}] {e.module_name} {e.status} ({e.duration_ms} ms)",
                markup=False,  # literal brackets, not rich tags
            ),
        )
        bus.subscribe(
            events.ThesisCompleted,
            lambda e: stderr.print(f"thesis {e.thesis_id} done: {e.summary}", markup=False),
        )
        runner = project.make_runner(bus=bus, workers=workers)
        try:
            plan = runner.plan(modules=list(modules) or None, rerun=rerun)
        except KeyError as exc:
            raise click.UsageError(str(exc)) from exc

        if dry_run:
            for line in plan.describe():
                click.echo(line)
            click.echo(
                _("{count} (thesis x module) pairs planned").format(
                    count=plan.pair_count
                )
            )
            return

        # Ctrl-C is skip-pending cancellation (ADR-0013): the handler tells
        # the runner to stop submitting new theses; in-flight ones finish and
        # execute() returns normally, then we exit with the partial code
        # (ADR-0003). signal.signal must run on the main thread, which is where
        # the CLI executes (the GUI, running execute() off-thread, uses a
        # Cancel button instead).
        def _on_sigint(signum, frame) -> None:
            stderr.print(
                _("cancelling - finishing in-flight theses (Ctrl-C again to force)...")
            )
            runner.cancel()

        previous_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, _on_sigint)
        try:
            summary = runner.execute(plan)
        finally:
            signal.signal(signal.SIGINT, previous_handler)

        # --open-report is the explicit ask, so it ignores the GUI's
        # ui.open_report_after_run preference - but it still honours the
        # suppression rules (nothing to show after a cancelled or all-errored
        # run, Sec. 9.8.3). Writing happens here, opening after the project
        # closes.
        report_path = None
        if open_report and report.should_offer_report(
            "always", cancelled=summary.cancelled, ok=summary.ok
        ) == "open":
            report_path = _write_report(report.default_report_path(project.dir), project)

    payload = {
        "theses_completed": summary.theses_completed,
        "ok": summary.ok,
        "na": summary.na,
        "error": summary.error,
        "cancelled": summary.cancelled,
        "duration_s": round(summary.duration_s, 2),
    }
    if fmt == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        cancelled_note = _(" | cancelled") if summary.cancelled else ""
        stdout.print(
            _(
                "{theses} theses | {ok} ok | {na} na | {error} errors | "
                "{duration} s"
            ).format(
                theses=summary.theses_completed,
                ok=summary.ok,
                na=summary.na,
                error=summary.error,
                duration=payload["duration_s"],
            )
            + cancelled_note
        )
    if report_path is not None:
        stderr.print(_("report written to {path}").format(path=report_path))
        webbrowser.open(report_path.as_uri())
    if summary.error or summary.cancelled:
        ctx.exit(EX_PARTIAL)


# -- export / import -----------------------------------------------------------


@cli.command()
@click.argument("out", required=False, type=click.Path(path_type=Path))
@click.option("--current-only", is_flag=True,
              help=_("Trim history to the latest run per (thesis, module)."))
@click.option("--profiling", is_flag=True,
              help=_("Dump per-run durations as CSV instead of the cohort export "
                     "(QA-RES)."))
@click.pass_context
def export(
    ctx: click.Context, out: Path | None, current_only: bool, profiling: bool
) -> None:
    """Produce the researcher export (PII-stripped SQLite, ADR-0007).

    With --profiling, writes the flat per-run profiling dataset instead: one
    CSV row per module run with its duration and the PDF size it was measured
    on, for checking real timings against the per-module budgets in ADR-0015
    (#47). Same rules as the cohort export - local source only, no PII column.
    """
    with open_project(ctx) as project:
        policy = ExportPolicy.CURRENT_ONLY if current_only else ExportPolicy.FULL
        label = project.config.institution or "export"
        try:
            if profiling:
                if out is None:
                    out = (
                        project.dir / "exports"
                        / f"{label}-profiling-{date.today():%Y-%m-%d}.csv"
                    )
                profile_stats = export_profiling(project.repo.conn, out, policy)
            else:
                if out is None:
                    out = project.dir / "exports" / f"{label}-{date.today():%Y-%m-%d}.sqlite"
                stats = export_database(project.repo.conn, out, policy)
        except FileExistsError as exc:
            raise DataError(str(exc)) from exc
    if profiling:
        stdout.print(
            _(
                "exported {rows} module runs across {modules} modules "
                "({policy}) -> {path}"
            ).format(
                rows=profile_stats.rows,
                modules=profile_stats.modules,
                policy=profile_stats.policy.value,
                path=profile_stats.path,
            )
        )
    else:
        stdout.print(
            _(
                "exported {theses} theses, {runs} runs, {metrics} metric values "
                "({policy}) -> {path}"
            ).format(
                theses=stats.theses,
                runs=stats.runs,
                metrics=stats.metrics,
                policy=stats.policy.value,
                path=stats.path,
            )
        )


@cli.command("import")
@click.argument("export_file", type=click.Path(exists=True, path_type=Path))
@click.option("--name", required=True,
              help=_('Source label, e.g. "FH Wedel CS 2026".'))
@click.pass_context
def import_(ctx: click.Context, export_file: Path, name: str) -> None:
    """Import a professor's export as a new read-only source (Sec. 8.3.2)."""
    with open_project(ctx) as project:
        try:
            stats = import_export(project.repo.conn, export_file, name)
        except ImportError_ as exc:
            raise DataError(str(exc)) from exc
    stdout.print(
        _(
            "imported source {source_id} ({name}): {theses} theses, {runs} runs, "
            "{metrics} metric values"
        ).format(
            source_id=stats.source_id,
            name=repr(stats.name),
            theses=stats.theses,
            runs=stats.runs,
            metrics=stats.metrics,
        )
    )


# -- privacy --------------------------------------------------------------------


_HTML_COMMENT = re.compile(r"<!--.*?-->\s*", re.DOTALL)


def _load_stub(filename: str) -> str:
    text = (resources.files("tta.core") / "help" / "privacy" / filename).read_text("utf-8")
    return _HTML_COMMENT.sub("", text).strip()


@cli.group()
def privacy() -> None:
    """Render the GDPR privacy statement (ADR-0009)."""


@privacy.command("report")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
def privacy_report(fmt: str) -> None:
    """Generated from core/privacy_metadata.py - never hand-edited."""
    if fmt == "json":
        click.echo(privacy_metadata.render_report_json())
        return
    click.echo(
        privacy_metadata.render_report_md(
            rights_stub=_load_stub("rights_stub.md"),
            controller_stub=_load_stub("controller_stub.md"),
        )
    )


# -- report -----------------------------------------------------------------------


def _write_report(out: Path, project: Project) -> Path:
    """Render in core, write in the adapter (ADR-0002). Overwrites."""
    document = report.render_html(report.collect(project.repo))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    return out


@cli.command("report")
@click.option("--out", type=click.Path(path_type=Path), default=None,
              help=_("Where to write it (default: "
                     "<project>/reports/report-<date>.html)."))
@click.pass_context
def write_report(ctx: click.Context, out: Path | None) -> None:
    """Write the stand-alone HTML cohort report (Sec. 9.8, ADR-0016 rev. 2).

    One self-contained file: every style rule and every chart inline, no
    external request, and no file names, paths, notes or document text
    (Sec. 9.8.3). It is written, not opened - a CLI must not launch a
    browser unasked; `tta run --open-report` does that on request.
    """
    with open_project(ctx) as project:
        theses = report.collect(project.repo).theses
        written = _write_report(out or report.default_report_path(project.dir), project)
    stdout.print(
        _("report over {theses} theses -> {path}").format(theses=theses, path=written)
    )


# -- help -------------------------------------------------------------------------


@cli.command("help")
@click.argument("topic", required=False)
def help_(topic: str | None) -> None:
    """Render a help topic (module, metric, or concept) in the terminal."""
    root = resources.files("tta.core") / "help"
    sections = ("modules", "metrics", "concepts")
    if topic:
        for section in sections:
            candidate = root / section / f"{topic}.md"
            if candidate.is_file():
                stdout.print(Markdown(candidate.read_text("utf-8")))
                return
        raise DataError(_("no help topic {topic}").format(topic=repr(topic)))
    available = [
        f"{section}/{entry.name[:-3]}"
        for section in sections
        if (root / section).is_dir()
        for entry in sorted((root / section).iterdir())
        if entry.name.endswith(".md")
    ]
    if available:
        stdout.print(_("available topics:"))
        for slug in available:
            stdout.print(f"  {slug}")
    else:
        stdout.print(_("no help topics installed yet"))


def main() -> None:
    """Console entry point: map uncaught errors to sysexits EX_SOFTWARE."""
    # The runner spawns workers (multiprocessing 'spawn', #32); in a frozen
    # --onefile build spawn re-executes this binary, so freeze_support must
    # intercept the worker/tracker sub-process before Click parses argv.
    # No-op when not frozen / not a spawned child (ADR-0014).
    import multiprocessing

    multiprocessing.freeze_support()
    try:
        cli(standalone_mode=True)
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(EX_INTERNAL)


if __name__ == "__main__":
    main()
