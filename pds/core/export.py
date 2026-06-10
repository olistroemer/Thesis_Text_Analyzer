"""Anonymisation + export (SDD §8.3, ADR-0007, QA-PRIV).

A single SQLite file mirroring the local schema minus PII columns and
the `artefact_files` table, plus an `export_info` metadata table. Only
the local source is exported — imported cohorts on a researcher machine
are someone else's data and never re-travel.

What never ships (§8.3.1): `theses.pdf_path/pdf_filename/notes/tags`,
rows with `excluded=1`, `module_runs.error_traceback/notes`, the whole
`artefact_files` table; `theses.added_at` is rounded to day.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import pds
from pds.core.db import migrator


class ExportPolicy(str, Enum):
    """Parameterised even in MVP (SDD §12: aggregate-only mode may follow)."""

    FULL = "full"  # complete module_runs + metric_values history (default)
    CURRENT_ONLY = "current-only"  # latest run per (thesis, module) only


@dataclass
class ExportStats:
    path: Path
    theses: int
    runs: int
    metrics: int
    policy: ExportPolicy


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
    pdf_sha256     TEXT NOT NULL,
    pdf_size_bytes INTEGER,
    type           TEXT NOT NULL,
    language_hint  TEXT,
    excluded       INTEGER NOT NULL,
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
                " SELECT t.id, t.source_id, t.pdf_sha256, t.pdf_size_bytes, t.type,"
                "        t.language_hint, t.excluded, date(t.added_at)"
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
                "app_version": pds.__version__,
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
