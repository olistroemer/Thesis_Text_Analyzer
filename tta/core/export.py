"""Anonymisation + export (SDD Sec. 8.3, ADR-0007, QA-PRIV).

A single SQLite file mirroring the local schema minus PII columns and
the `artefact_files` table, plus an `export_info` metadata table. Only
the local source is exported - imported cohorts on a researcher machine
are someone else's data and never re-travel.

What never ships (Sec. 8.3.1): `theses.pdf_path/pdf_filename/notes/tags`,
rows with `excluded=1` **and the `excluded` column itself** (constant-zero
once those rows are filtered out, #64), `module_runs.error_traceback/diagnostics`,
the whole `artefact_files` table; `theses.added_at` is rounded to day.

`export_profiling` is the second, flat output (#47, ADR-0007 rev. 4): a
CSV of per-run durations for QA-RES benchmarks and `doctor`, under the
same local-only, no-PII rules.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import tta
from tta.core.db import migrator


class ExportPolicy(str, Enum):
    """Parameterised even in MVP (SDD Sec. 12: aggregate-only mode may follow)."""

    FULL = "full"  # complete module_runs + metric_values history (default)
    CURRENT_ONLY = "current-only"  # latest run per (thesis, module) only


@dataclass
class ExportStats:
    path: Path
    theses: int
    runs: int
    metrics: int
    policy: ExportPolicy


@dataclass
class ProfilingStats:
    path: Path
    rows: int
    modules: int
    policy: ExportPolicy


#: Column order of the profiling CSV (#47). `ms_per_byte` is derived, not
#: stored: it is the quantity ADR-0015's per-module budgets are about, and the
#: same rate the size-weighted ETA consumes (SDD Sec. 5.5).
PROFILING_COLUMNS = (
    "thesis_id",
    "pdf_sha256",
    "pdf_size_bytes",
    "module_name",
    "module_version",
    "status",
    "started_at",
    "duration_ms",
    "ms_per_byte",
)


# Mirror of the local schema minus PII columns and artefact_files.
# Views are not exported: they reference stripped columns; the importer's
# merged DB provides its own.
_EXPORT_DDL = """
CREATE TABLE export.sources (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    institution      TEXT,
    app_version      TEXT,
    schema_version   INTEGER,
    pipeline_summary TEXT,
    created_at       TEXT NOT NULL
);
CREATE TABLE export.theses (
    id             INTEGER PRIMARY KEY,
    source_id      INTEGER NOT NULL,
    pdf_sha256     TEXT,    -- NULL for a thesis added but never analysed (ADR-0006 rev. 4)
    pdf_size_bytes INTEGER,
    -- no `excluded`: the row filter below leaves it constant-zero (#64)
    added_at       TEXT NOT NULL
);
CREATE TABLE export.module_runs (
    id              INTEGER PRIMARY KEY,
    thesis_id       INTEGER NOT NULL,
    module_name     TEXT NOT NULL,
    module_version  TEXT NOT NULL,
    status          TEXT NOT NULL,
    reason          TEXT,
    started_at      TEXT NOT NULL,
    duration_ms     INTEGER
);
CREATE TABLE export.metric_values (
    run_id      INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    value_num   REAL,
    value_text  TEXT,
    PRIMARY KEY (run_id, metric_name)
);
CREATE TABLE export.export_info (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def export_database(
    conn: sqlite3.Connection,
    out_path: Path | str,
    policy: ExportPolicy = ExportPolicy.FULL,
) -> ExportStats:
    """Write the PII-stripped export of the local source to ``out_path``."""
    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn.execute("ATTACH DATABASE ? AS export", (str(out_path),))
    try:
        with conn:  # single transaction over both databases
            conn.executescript(_EXPORT_DDL)
            conn.execute("INSERT INTO export.sources SELECT * FROM sources WHERE kind = 'local'")
            conn.execute(
                "INSERT INTO export.theses"
                " SELECT t.id, t.source_id, t.pdf_sha256, t.pdf_size_bytes,"
                "        date(t.added_at)"
                " FROM theses t JOIN sources s ON s.id = t.source_id"
                " WHERE s.kind = 'local' AND t.excluded = 0"
            )
            run_filter = ""
            if policy is ExportPolicy.CURRENT_ONLY:
                run_filter = (
                    " AND mr.id IN (SELECT id FROM v_module_run_history WHERE recency_rank = 1)"
                )
            conn.execute(
                "INSERT INTO export.module_runs"
                " SELECT mr.id, mr.thesis_id, mr.module_name, mr.module_version,"
                "        mr.status, mr.reason, mr.started_at, mr.duration_ms"
                " FROM module_runs mr"
                " WHERE mr.thesis_id IN (SELECT id FROM export.theses)" + run_filter
            )
            conn.execute(
                "INSERT INTO export.metric_values"
                " SELECT mv.run_id, mv.metric_name, mv.value_num, mv.value_text"
                " FROM metric_values mv"
                " WHERE mv.run_id IN (SELECT id FROM export.module_runs)"
            )

            def count(table: str) -> int:
                return conn.execute(f"SELECT COUNT(*) FROM export.{table}").fetchone()[0]

            stats = ExportStats(
                path=out_path,
                theses=count("theses"),
                runs=count("module_runs"),
                metrics=count("metric_values"),
                policy=policy,
            )
            info = {
                "schema_version": str(max(migrator.applied_versions(conn), default=0)),
                "app_version": tta.__version__,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "policy": policy.value,
                "thesis_count": str(stats.theses),
                "run_count": str(stats.runs),
            }
            conn.executemany(
                "INSERT INTO export.export_info (key, value) VALUES (?, ?)", info.items()
            )
    finally:
        conn.execute("DETACH DATABASE export")
    return stats


def export_profiling(
    conn: sqlite3.Connection,
    out_path: Path | str,
    policy: ExportPolicy = ExportPolicy.FULL,
) -> ProfilingStats:
    """Write the per-run profiling dataset of the local source as CSV (#47).

    One row per ``module_runs`` row: which module ran on which thesis, how
    long it took, and how large the PDF was - which is what QA-RES benchmarks
    and the ``doctor`` command need to check real durations against ADR-0015's
    per-module budgets. ``ms_per_byte`` is derived here rather than stored, and
    is left empty when the size is unknown or zero (no rate exists), matching
    ``Repository.module_duration_stats``.

    Bound by the same two rules as the cohort export (ADR-0007, SDD Sec. 8.3):
    the **local** source only - imported durations were measured on someone
    else's machine and would corrupt a benchmark - and **no PII column**.
    ``duration_ms`` and ``started_at`` already ship in the cohort export, so
    this discloses nothing new; only the shape changes, from a relational
    database to the one flat table a benchmark wants to read.

    ``CURRENT_ONLY`` trims to the latest run per ``(thesis, module)``. Errored
    and not-applicable runs are kept: a module that reliably fails after 30 s
    is exactly what a performance investigation is looking for. Refuses to
    overwrite an existing file, as :func:`export_database` does.
    """
    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    run_filter = ""
    if policy is ExportPolicy.CURRENT_ONLY:
        run_filter = " AND mr.id IN (SELECT id FROM v_module_run_history WHERE recency_rank = 1)"
    rows = conn.execute(
        "SELECT t.id AS thesis_id, t.pdf_sha256, t.pdf_size_bytes,"
        "       mr.module_name, mr.module_version, mr.status,"
        "       mr.started_at, mr.duration_ms"
        " FROM module_runs mr"
        " JOIN theses t ON t.id = mr.thesis_id"
        " JOIN sources s ON s.id = t.source_id"
        " WHERE s.kind = 'local' AND t.excluded = 0" + run_filter +
        " ORDER BY mr.module_name, t.id, mr.started_at, mr.id"
    ).fetchall()

    modules = set()
    with open(out_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(PROFILING_COLUMNS)
        for row in rows:
            modules.add(row["module_name"])
            size = row["pdf_size_bytes"]
            duration = row["duration_ms"]
            rate = ""
            if duration is not None and size:  # no rate without both (and size > 0)
                rate = f"{duration / size:.9f}"
            writer.writerow(
                [
                    row["thesis_id"],
                    row["pdf_sha256"] if row["pdf_sha256"] is not None else "",
                    size if size is not None else "",
                    row["module_name"],
                    row["module_version"],
                    row["status"],
                    row["started_at"],
                    duration if duration is not None else "",
                    rate,
                ]
            )
    return ProfilingStats(
        path=out_path, rows=len(rows), modules=len(modules), policy=policy
    )
