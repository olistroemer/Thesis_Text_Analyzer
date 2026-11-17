"""`tta` command line - first-class primary adapter (ADR-0003).

Output rules: human-readable tables on stdout by default; `--format
{human,json,csv}` for machine-readable output (JSON is the scripting
contract); logs and progress go to stderr; exit codes follow sysexits
(0 ok, 1 partial, 64 misuse, 65 data error, 70 internal).
"""

from __future__ import annotations

import json
import signal
import sys
import traceback
import webbrowser
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.table import Table

import tta
from tta.cli import _stdio
from tta.core import events
from tta.core import i18n
from tta.core import privacy_metadata
from tta.core.config import load_config
from tta.core.cover_rules import CoverRulesError, load_cover_ruleset
from tta.core.db import migrator
from tta.core.discovery import collect_pdfs
from tta.core.export import ExportPolicy, export_database, export_profiling
from tta.core.help_corpus import (
    KIND_SECTIONS,
    SECTIONS,
    find_page,
    first_paragraph,
    help_root,
    list_field,
    opens_with_title,
    read_page,
    text_field,
)
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


# ---- user-facing command help (ADR-0020) ---------------------------------
# Every command carries an explicit `help=_(...)` (and `short_help=_(...)`
# where the one-line form in the command list should differ). Click prefers
# it over the function docstring, which is what makes this translatable at
# all: a docstring is a bare literal, cannot be wrapped in `_()`, and ADR-0018
# forbids the German from living in a *.py file anyway. It also separates the
# two audiences - the docstrings below keep the issue and ADR cross-references
# for developers, and the strings here are what a professor reads, with no
# "#42" or "ADR-0007" in them.


@click.group(name="tta", help=_(
    "Thesis Text Analyzer: measure the text metrics of student theses and "
    "compare them across a whole cohort."
))
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


@cli.command(help=_(
    "Show the application version and the version of every analysis module."
))
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


@cli.command(
    short_help=_("Collect diagnostics for a support request."),
    help=_(
        "Collect diagnostics for a support request: versions, the state of the "
        "project, and an offline self-check of the analysis libraries.\n"
        "\n"
        "Nothing is changed - the database is opened read-only and no migration "
        "is applied. The command exits with a non-zero status if any check "
        "fails, so it can be used in a script."
    ),
)
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


@cli.group(help=_("Create, migrate or compact the project database."))
def db() -> None:
    """Initialise / migrate / vacuum the project database."""


@db.command("init", help=_(
    "Create the project in the --project directory, or migrate an existing one."
))
@click.pass_context
def db_init(ctx: click.Context) -> None:
    """Create (or migrate) the project in --project."""
    with open_project(ctx, create=True) as project:
        stdout.print(
            _("project ready at {path}").format(path=project.dir.resolve() / DB_FILENAME)
        )


@db.command("migrate", help=_(
    "Apply any pending schema migrations, after taking a safety backup."
))
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


@db.command("vacuum", help=_("Compact the project database file."))
@click.pass_context
def db_vacuum(ctx: click.Context) -> None:
    """Compact the database file."""
    with open_project(ctx) as project:
        project.repo.conn.execute("VACUUM")
    stdout.print(_("vacuumed"))


# -- list ------------------------------------------------------------------


@cli.command("list", help=_(
    "List the known theses with the status of their analysis."
))
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
        # RFC 4180 "\r\n" rows on every OS, written untranslated: a stdout that
        # translates "\n" (Windows' default) doubled the CR (see _stdio)
        _stdio.write_csv_rows(sys.stdout, rows, list(rows[0]) if rows else ["id"])
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


@cli.command(
    short_help=_("Exclude a thesis from analysis and exports."),
    help=_(
        "Exclude the thesis THESIS_ID from analysis and from exports.\n"
        "\n"
        "This is the command-line form of the Excluded checkbox in the window. "
        "If the thesis has already been analysed, its cached analysis is "
        "deleted from this machine: the extracted text, the tokens and the PDF "
        "metadata, together with its metric values and its run history. That "
        "cannot be undone. The source PDF is never touched. Excluding a thesis "
        "before it is analysed simply prevents any analysis from being cached."
    ),
)
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


@cli.command(
    short_help=_("Re-include a previously excluded thesis."),
    help=_(
        "Re-include a previously excluded thesis, clearing its excluded flag."
        "\n\n"
        "The thesis becomes eligible again and is analysed on the next run. "
        "Analysis that was deleted when it was excluded is not restored; run "
        "the analysis again to recompute it."
    ),
)
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


@cli.command(
    short_help=_("Remove a thesis from the project entirely."),
    help=_(
        "Remove the thesis THESIS_ID from the project entirely.\n"
        "\n"
        "The stronger form of `exclude`, for a PDF that was added by mistake. "
        "Excluding keeps the thesis on record, so its identity is remembered "
        "and it is never silently analysed again; removing deletes the record "
        "as well, so the same PDF can afterwards be added again as a new "
        "thesis. Its cached analysis goes with it. This cannot be undone: "
        "nothing restores it, and there is no record left to re-include. The "
        "source PDF is never touched."
    ),
)
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


@cli.group(help=_("Inspect the catalogue of analysis modules."))
def module() -> None:
    """List module details (the analysis catalogue)."""


@module.command("list", help=_(
    "List every registered module, in the order in which it runs."
))
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


@module.command("show", help=_(
    "Show what one module reads and what it produces."
))
@click.argument("name")
def module_show(name: str) -> None:
    """Spec details for one module.

    The description is the module's help page - its title and first
    paragraph - not the Python docstring, which is English and names
    internals (ADR-0012 rev. 5, #78). The docstring is the fallback only for
    a module without a page: a contributed one, since the corpus gate
    guarantees a page for every registered module.
    """
    try:
        mod = default_registry().get(name)
    except KeyError as exc:
        raise click.UsageError(str(exc)) from exc
    s = mod.spec
    stdout.print(f"[bold]{s.name}[/bold] {s.version}")
    page = find_page(s.name, "module")
    if page is not None:
        fields, body = read_page(page)
        title = text_field(fields, "title")
        if title:
            stdout.print(f"[bold]{escape(title)}[/bold]")
        paragraph = first_paragraph(body)
        if paragraph:
            stdout.print(Markdown(paragraph))
    else:
        doc = (type(mod).__module__ and sys.modules[type(mod).__module__].__doc__) or ""
        if doc:
            stdout.print(escape(doc.strip().split("\n\n")[0]))
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


@cli.command(
    short_help=_("Add PDF files or folders and analyse them."),
    help=_(
        "Add INPUTS (PDF files or folders) and analyse them.\n"
        "\n"
        "Without INPUTS, every thesis already in the project is analysed. By "
        "default only what is missing, out of date or previously failed is "
        "computed; --rerun computes everything again. The type of a thesis is "
        "detected during the analysis, not entered when the file is added."
    ),
)
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
@click.option("--cover-rules", "cover_rules_path",
              type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help=_("Researcher option: apply the repository rules in this file "
                     "(skip cover pages, ignore pages and passages that are no "
                     "evidence) when reading the title page. Without it every thesis "
                     "is read unmodified. Theses analysed with and without a ruleset "
                     "are kept apart: changing the choice re-analyses the title-page "
                     "modules."))
@click.option("--format", "fmt", type=click.Choice(["human", "json"]), default="human")
@click.pass_context
def run(ctx, inputs, modules, rerun, dry_run, workers, fmt, open_report,
        cover_rules_path) -> None:
    """Add INPUTS (PDF files or directories) and run analyses.

    Without INPUTS, runs on all known theses. Default mode runs missing,
    stale, and previously-errored pairs; --rerun runs everything. Thesis type
    is detected during the run (mod_classify_thesis_type), not set on add.

    --cover-rules is the researcher-only ruleset of ADR-0023 (a CLI-only
    option under ADR-0003 rev. 2026-11-17). Without it no repository rule
    applies and the text is read unmodified, exactly as in the GUI. With it
    the two title-page modules carry the ruleset in their version, so the
    planner re-runs them whenever the choice changes and runs with and
    without it are never mixed.
    """
    cover_rules = None
    if cover_rules_path is not None:
        try:
            cover_rules = load_cover_ruleset(cover_rules_path)
        except CoverRulesError as exc:
            raise click.BadParameter(str(exc), param_hint="--cover-rules") from exc
        stderr.print(
            _("cover rules: {id} version {version} ({fingerprint}), {count} rule(s)").format(
                id=cover_rules.id,
                version=cover_rules.version,
                fingerprint=cover_rules.fingerprint(),
                count=len(cover_rules.rule_ids()),
            ),
            markup=False,
        )
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
        runner = project.make_runner(
            registry=default_registry(cover_rules), bus=bus, workers=workers
        )
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
        webbrowser.open(report_path.resolve().as_uri())  # -C defaults to "."
    if summary.error or summary.cancelled:
        ctx.exit(EX_PARTIAL)


# -- export / import -----------------------------------------------------------


@cli.command(
    short_help=_("Write the researcher export, free of personal data."),
    help=_(
        "Write the researcher export: an SQLite file holding the metric values "
        "and no personal data.\n"
        "\n"
        "With --profiling, the flat per-run timing dataset is written instead: "
        "one CSV row per module run, with its duration and the size of the PDF "
        "it was measured on. Both obey the same rules - only data produced on "
        "this machine, and no identifying column."
    ),
)
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


@cli.command("import", help=_(
    "Import another installation's export as a new, read-only source."
))
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


@cli.group(help=_("Render the data-protection statement."))
def privacy() -> None:
    """Render the GDPR privacy statement (ADR-0009)."""


@privacy.command("report", help=_(
    "Render the data-protection statement. It is generated from the privacy "
    "registry in the code and is never hand-written, so it cannot fall behind "
    "what the application actually stores."
))
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
def privacy_report(fmt: str) -> None:
    """Generated from core/privacy_metadata.py - never hand-edited."""
    if fmt == "json":
        click.echo(privacy_metadata.render_report_json())
        return
    click.echo(privacy_metadata.render_statement_md())


# -- report -----------------------------------------------------------------------


def _write_report(out: Path, project: Project) -> Path:
    """Render in core, write in the adapter (ADR-0002). Overwrites."""
    document = report.render_html(report.collect(project.repo))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    return out


@cli.command(
    "report",
    short_help=_("Write the stand-alone HTML report for the cohort."),
    help=_(
        "Write the stand-alone HTML report over the whole cohort.\n"
        "\n"
        "One self-contained file: every style rule and every chart is inline, "
        "it makes no request to the network, and it contains no file names, "
        "paths, notes or document text. The file is written, not opened - a "
        "command-line tool must not start a browser unasked. Use "
        "`tta run --open-report` to have it opened."
    ),
)
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


def _help_markdown(fields: dict, body: str) -> str:
    """One help page as the terminal shows it (ADR-0012 rev. 5, #78).

    The body only: front matter is parsed, never rendered. The ``title`` is
    the heading when the body does not open with one of its own, and
    ``see_also`` becomes a trailing block naming each target's title and the
    slug ``tta help`` accepts for it.
    """
    parts = []
    title = text_field(fields, "title")
    if title and not opens_with_title(body):
        parts.append(f"# {title}")
    parts.append(body.strip())
    see_also = []
    for uri in list_field(fields, "see_also"):
        kind, _separator, slug = uri.partition(":")
        if kind not in KIND_SECTIONS or not slug:
            continue
        target = find_page(slug, kind)
        label = text_field(read_page(target)[0], "title") if target is not None else ""
        see_also.append(f"- {label} (`{slug}`)" if label else f"- `{slug}`")
    if see_also:
        parts.append("## " + _("See also"))
        parts.append("\n".join(see_also))
    return "\n\n".join(parts)


@cli.command("help", help=_(
    "Show a help topic - a module, a metric or a concept - in the terminal."
))
@click.argument("topic", required=False)
def help_(topic: str | None) -> None:
    """Render a help topic (module, metric, or concept) in the terminal."""
    if topic:
        page = find_page(topic)
        if page is None:
            raise DataError(_("no help topic {topic}").format(topic=repr(topic)))
        stdout.print(Markdown(_help_markdown(*read_page(page))))
        return
    root = help_root()
    available = [
        f"{section}/{entry.name[:-3]}"
        for section in SECTIONS
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
    # A redirected Windows stdout must not abort a command (see _stdio).
    _stdio.replace_unencodable_output()
    try:
        cli(standalone_mode=True)
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(EX_INTERNAL)


if __name__ == "__main__":
    main()
