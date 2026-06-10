"""Forward-only SQL migrations (ADR-0006, ADR-0014).

Numbered ``NNNN_*.sql`` files under ``migrations/`` are applied in order;
applied versions are recorded in ``schema_version``. Before applying to a
non-empty database a defensive backup ``<db>.bak.<version>`` is written;
if migration fails the backup remains and the error propagates (the app
refuses to open the project, ADR-0014).
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from pds.core import db

_MIGRATION_NAME = re.compile(r"^(\d{4})_.+\.sql$")


def available_migrations() -> list[tuple[int, str]]:
    """Sorted ``(version, sql)`` pairs shipped with the package."""
    found = []
    for entry in resources.files("pds.core.db").joinpath("migrations").iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry.read_text(encoding="utf-8")))
    found.sort()
    return found


def applied_versions(conn: sqlite3.Connection) -> list[int]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return []
    return [r["version"] for r in conn.execute("SELECT version FROM schema_version ORDER BY version")]


def migrate(db_path: Path | str) -> list[int]:
    """Bring the database at ``db_path`` up to the latest schema.

    Returns the list of newly applied versions (empty if up to date).
    """
    db_path = Path(db_path)
    existed = db_path.exists() and db_path.stat().st_size > 0
    conn = db.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.commit()
        already = set(applied_versions(conn))
        pending = [(v, sql) for v, sql in available_migrations() if v not in already]
        if not pending:
            return []
        if existed:
            shutil.copy2(db_path, db_path.with_name(f"{db_path.name}.bak.{pending[0][0]}"))
        applied = []
        for version, sql in pending:
            with conn:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (version, datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
            applied.append(version)
        return applied
    finally:
        conn.close()
