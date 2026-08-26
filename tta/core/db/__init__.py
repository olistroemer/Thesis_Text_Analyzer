"""SQLite persistence: schema, migrations, repository (SDD Sec. 8.1, ADR-0006)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the project database with the connection settings core relies on."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # ADR-0006 first-run hashing (#59): WAL takes the rollback-journal fsync out of every
    # commit - the dominant cost of add_thesis and of the first-run hashing
    # pass - and lets the runner's background-thread connection (#27) read
    # while the main one writes instead of blocking on it. synchronous=NORMAL
    # is WAL's standard companion: an OS crash can cost the most recent
    # transactions, never a corrupt database. Best-effort: a filesystem that
    # refuses WAL (some network mounts) just stays in rollback-journal mode.
    try:
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            logger.debug("journal_mode stayed %r for %s", mode, db_path)
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.Error:
        logger.debug("could not enable WAL on %s - keeping the default", db_path)
    return conn
