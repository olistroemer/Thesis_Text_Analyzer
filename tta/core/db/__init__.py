"""SQLite persistence: schema, migrations, repository (SDD §8.1, ADR-0006)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the project database with the connection settings core relies on."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
