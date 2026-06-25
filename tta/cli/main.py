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
import sys
import traceback
from datetime import date
from importlib import resources
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

import tta
from tta.core import events
from tta.core import privacy_metadata
from tta.core.db import migrator
from tta.core.export import ExportPolicy, export_database
from tta.core.importer import ImportError_, import_export
from tta.core.modules.registry import default_registry
from tta.core.project import DB_FILENAME, Project
from tta.core.types import THESIS_TYPES

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
    help="Project directory (default: current directory).",
)
@click.pass_context
def cli(ctx: click.Context, project_dir: Path) -> None:
    """Thesis Text Analyzer."""
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


# -- db ------------------------------------------------------------------


@cli.group()
def db() -> None:
    """Initialise / migrate / vacuum the project database."""


@db.command("init")
@click.pass_context
def db_init(ctx: click.Context) -> None:
    """Create (or migrate) the project in --project."""
    with open_project(ctx, create=True) as project:
        stdout.print(f"project ready at {project.dir.resolve() / DB_FILENAME}")


@db.command("migrate")
@click.pass_context
def db_migrate(ctx: click.Context) -> None:
    """Apply pending schema migrations (with defensive backup)."""
    project_dir: Path = ctx.obj
    db_path = project_dir / DB_FILENAME
    if not db_path.exists():
        raise DataError(f"no project at {project_dir} - run `tta db init` first")
    applied = migrator.migrate(db_path)
    stdout.print(f"applied migrations: {applied}" if applied else "schema is up to date")


@db.command("vacuum")
@click.pass_context
def db_vacuum(ctx: click.Context) -> None:
    """Compact the database file."""
    with open_project(ctx) as project:
        project.repo.conn.execute("VACUUM")
    stdout.print("vacuumed")


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
        rows = []
        for thesis in theses:
            counts = {"ok": 0, "na": 0, "error": 0}
            for (thesis_id, _), run in latest.items():
                if thesis_id == thesis.id:
                    counts[run["status"]] += 1
            rows.append(
                {
                    "id": thesis.id,
                    "filename": thesis.pdf_filename,
                    "type": thesis.type,
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
        table = Table(title=f"{len(rows)} theses")
        for column in ("id", "filename", "type", "status", "excluded"):
            table.add_column(column)
        for row in rows:
            status = f"{row['ok']} ok | {row['na']} na | {row['error']} err | {row['missing']} todo"
            table.add_row(
                str(row["id"]), row["filename"], row["type"], status,
                "yes" if row["excluded"] else "",
            )
        stdout.print(table)


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
    table = Table(title="module catalogue")
    for column in ("module", "version", "consumes", "produces"):
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
    stdout.print(f"consumes:  {', '.join(s.consumes) or '- (reads the PDF directly)'}")
    stdout.print(f"artefacts: {', '.join(s.produces_artefacts) or '-'}")
    stdout.print(f"metrics:   {', '.join(s.produces_metrics) or '-'}")


# -- run ---------------------------------------------------------------------


def _collect_pdfs(inputs: tuple[Path, ...]) -> list[Path]:
    pdfs: list[Path] = []
    for path in inputs:
        if path.is_dir():
            pdfs.extend(sorted(path.rglob("*.pdf")))
        else:
            pdfs.append(path)
    return pdfs


@cli.command()
@click.argument("inputs", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--type", "thesis_type", type=click.Choice(THESIS_TYPES), default="unspecified",
              help="Thesis type attribute for newly added files.")
@click.option("--module", "-m", "modules", multiple=True,
              help="Restrict to specific modules (repeatable; US-PROF-SELECT).")
@click.option("--rerun", is_flag=True, help="Re-run everything regardless of state.")
@click.option("--dry-run", is_flag=True, help="Print the plan without executing.")
@click.option("--workers", type=int, default=None, help="Concurrent theses (default: cores - 1).")
@click.option("--format", "fmt", type=click.Choice(["human", "json"]), default="human")
@click.pass_context
def run(ctx, inputs, thesis_type, modules, rerun, dry_run, workers, fmt) -> None:
    """Add INPUTS (PDF files or directories) and run analyses.

    Without INPUTS, runs on all known theses. Default mode runs missing,
    stale, and previously-errored pairs; --rerun runs everything.
    """
    with open_project(ctx, create=True) as project:
        for pdf in _collect_pdfs(inputs):
            thesis = project.repo.add_thesis(pdf, type=thesis_type)
            stderr.print(f"added thesis {thesis.id}: {thesis.pdf_filename}")

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
            click.echo(f"{plan.pair_count} (thesis x module) pairs planned")
            return

        summary = runner.execute(plan)

    payload = {
        "theses_completed": summary.theses_completed,
        "ok": summary.ok,
        "na": summary.na,
        "error": summary.error,
        "duration_s": round(summary.duration_s, 2),
    }
    if fmt == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        stdout.print(
            f"{summary.theses_completed} theses | {summary.ok} ok | "
            f"{summary.na} na | {summary.error} errors | {payload['duration_s']} s"
        )
    if summary.error:
        ctx.exit(EX_PARTIAL)


# -- export / import -----------------------------------------------------------


@cli.command()
@click.argument("out", required=False, type=click.Path(path_type=Path))
@click.option("--current-only", is_flag=True,
              help="Trim history to the latest run per (thesis, module).")
@click.pass_context
def export(ctx: click.Context, out: Path | None, current_only: bool) -> None:
    """Produce the researcher export (PII-stripped SQLite, ADR-0007)."""
    with open_project(ctx) as project:
        if out is None:
            label = project.config.institution or "export"
            out = project.dir / "exports" / f"{label}-{date.today():%Y-%m-%d}.sqlite"
        policy = ExportPolicy.CURRENT_ONLY if current_only else ExportPolicy.FULL
        try:
            stats = export_database(project.repo.conn, out, policy)
        except FileExistsError as exc:
            raise DataError(str(exc)) from exc
    stdout.print(
        f"exported {stats.theses} theses, {stats.runs} runs, "
        f"{stats.metrics} metric values ({stats.policy.value}) -> {stats.path}"
    )


@cli.command("import")
@click.argument("export_file", type=click.Path(exists=True, path_type=Path))
@click.option("--name", required=True, help='Source label, e.g. "FH Wedel CS 2026".')
@click.pass_context
def import_(ctx: click.Context, export_file: Path, name: str) -> None:
    """Import a professor's export as a new read-only source (Sec. 8.3.2)."""
    with open_project(ctx) as project:
        try:
            stats = import_export(project.repo.conn, export_file, name)
        except ImportError_ as exc:
            raise DataError(str(exc)) from exc
    stdout.print(
        f"imported source {stats.source_id} ({stats.name!r}): "
        f"{stats.theses} theses, {stats.runs} runs, {stats.metrics} metric values"
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
        raise DataError(f"no help topic {topic!r}")
    available = [
        f"{section}/{entry.name[:-3]}"
        for section in sections
        if (root / section).is_dir()
        for entry in sorted((root / section).iterdir())
        if entry.name.endswith(".md")
    ]
    if available:
        stdout.print("available topics:")
        for slug in available:
            stdout.print(f"  {slug}")
    else:
        stdout.print("no help topics installed yet")


def main() -> None:
    """Console entry point: map uncaught errors to sysexits EX_SOFTWARE."""
    try:
        cli(standalone_mode=True)
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(EX_INTERNAL)


if __name__ == "__main__":
    main()
