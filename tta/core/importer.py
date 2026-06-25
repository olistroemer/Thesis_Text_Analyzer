"""Import a professor's export into the researcher's merged DB (SDD §8.3.2).

Each import becomes one new `sources` row with `kind='imported'`; thesis
and run ids are remapped into the local id space. Imported theses are
read-only context — the runner's `kind='local'` filter never touches
them (US-RES-LOCAL-RERUN).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tta.core.db import migrator


class ImportError_(Exception):
    """Export file unreadable, wrong schema version, or name collision."""


@dataclass
class ImportStats:
    source_id: int
    name: str
    theses: int
    runs: int
    metrics: int


def import_export(conn: sqlite3.Connection, export_path: Path | str, name: str) -> ImportStats:
    """ATTACH + copy with id remapping; one transaction (ADR-0007)."""
    export_path = Path(export_path)
    if not export_path.exists():
        raise ImportError_(f"export file not found: {export_path}")

    conn.execute("ATTACH DATABASE ? AS src", (str(export_path),))
    try:
        try:
            info = dict(conn.execute("SELECT key, value FROM src.export_info"))
        except sqlite3.OperationalError as exc:
            raise ImportError_(f"not a tta export (no export_info table): {export_path}") from exc
        ours = max(migrator.applied_versions(conn), default=0)
        theirs = int(info.get("schema_version", "0"))
        if theirs != ours:
            raise ImportError_(
                f"schema version mismatch: export has v{theirs}, this database has v{ours}"
            )
        if conn.execute("SELECT 1 FROM sources WHERE name = ?", (name,)).fetchone():
            raise ImportError_(f"a source named {name!r} already exists")

        exporter = conn.execute(
            "SELECT institution, app_version, pipeline_summary FROM src.sources LIMIT 1"
        ).fetchone()

        with conn:
            cur = conn.execute(
                "INSERT INTO sources (name, kind, institution, app_version, schema_version,"
                " pipeline_summary, created_at) VALUES (?, 'imported', ?, ?, ?, ?, ?)",
                (
                    name,
                    exporter["institution"] if exporter else None,
                    exporter["app_version"] if exporter else None,
                    theirs,
                    exporter["pipeline_summary"] if exporter else None,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            source_id = cur.lastrowid

            thesis_ids: dict[int, int] = {}
            for row in conn.execute("SELECT * FROM src.theses"):
                cur = conn.execute(
                    "INSERT INTO theses (source_id, pdf_sha256, pdf_size_bytes, type,"
                    " language_hint, excluded, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        source_id,
                        row["pdf_sha256"],
                        row["pdf_size_bytes"],
                        row["type"],
                        row["language_hint"],
                        row["excluded"],
                        row["added_at"],
                    ),
                )
                thesis_ids[row["id"]] = cur.lastrowid

            run_ids: dict[int, int] = {}
            for row in conn.execute("SELECT * FROM src.module_runs"):
                cur = conn.execute(
                    "INSERT INTO module_runs (thesis_id, module_name, module_version,"
                    " status, reason, started_at, duration_ms)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        thesis_ids[row["thesis_id"]],
                        row["module_name"],
                        row["module_version"],
                        row["status"],
                        row["reason"],
                        row["started_at"],
                        row["duration_ms"],
                    ),
                )
                run_ids[row["id"]] = cur.lastrowid

            metric_count = 0
            for row in conn.execute("SELECT * FROM src.metric_values"):
                conn.execute(
                    "INSERT INTO metric_values (run_id, metric_name, value_num, value_text)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        run_ids[row["run_id"]],
                        row["metric_name"],
                        row["value_num"],
                        row["value_text"],
                    ),
                )
                metric_count += 1
        return ImportStats(
            source_id=source_id,
            name=name,
            theses=len(thesis_ids),
            runs=len(run_ids),
            metrics=metric_count,
        )
    finally:
        conn.execute("DETACH DATABASE src")
