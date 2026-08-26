"""Diagnostics bundle for support / bug reports (#42, ADR-0003).

Lives in core so both adapters can render it and so it is testable
without a CLI runner (ADR-0002). Two rules define this module:

* **Read-only.** A diagnostic that repairs what it inspects hides the
  fault being reported. Nothing here migrates, creates or writes: the
  database is opened read-only and `Project.open` (which migrates) is
  deliberately not used.
* **The offline check really blocks the network.** QA-PRIV promises the
  app never reaches out, so the three third-party pieces that plausibly
  could - NLTK ``punkt_tab``, ``langdetect``, ``textstat`` - are probed
  with outbound sockets disabled. Asserting offline-ness proves nothing;
  doing the work with the network unplugged does.

Those three libraries cost ~0.6 s to import, so every one of them is
imported inside the probe that needs it, never at module scope: `doctor`
is one command among many and no other command may pay for it.
"""

from __future__ import annotations

import contextlib
import os
import platform
import socket
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import tta
from tta.core.config import CONFIG_FILENAME, load_config
from tta.core.modules.registry import default_registry

DB_FILENAME = "tta.sqlite"  # duplicated from core.project to keep this import-light

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    """One named diagnostic with a verdict a script can branch on."""

    name: str
    status: str  # ok | warn | fail
    detail: str


@dataclass
class Diagnostics:
    app: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    modules: dict[str, str] = field(default_factory=dict)
    project: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def status(self) -> str:
        """Worst check status: `fail` beats `warn` beats `ok`."""
        statuses = {c.status for c in self.checks}
        return FAIL if FAIL in statuses else (WARN if WARN in statuses else OK)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app,
            "runtime": self.runtime,
            "modules": self.modules,
            "project": self.project,
            "config": self.config,
            "checks": [asdict(c) for c in self.checks],
            "status": self.status,
        }


class NetworkBlocked(RuntimeError):
    """An offline probe tried to open a connection (QA-PRIV violation)."""


@contextlib.contextmanager
def no_network() -> Iterator[None]:
    """Disable outbound connections for the duration of the block.

    Patches the two entry points every stdlib/urllib/requests path funnels
    through. Restored in ``finally``, so a probe raising does not leave the
    interpreter unable to make connections.
    """
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def _blocked(*args, **kwargs):
        target = args[1] if len(args) > 1 else (args[0] if args else None)
        raise NetworkBlocked(f"outbound connection attempted to {target!r}")

    socket.socket.connect = _blocked  # type: ignore[method-assign]
    socket.create_connection = _blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        socket.create_connection = real_create  # type: ignore[assignment]


def _probe_nltk() -> list[Check]:
    """punkt_tab must resolve for every supported language, from local data."""
    # Deferred with nltk itself: importing `mod_tokenize` for one dict would
    # drag nltk into every importer of this module (see the note below).
    import nltk

    from tta.core.modules.tokenize import NLTK_LANGUAGES

    checks = [
        Check(
            "nltk.data.path",
            OK,
            "; ".join(str(p) for p in nltk.data.path) or "<empty>",
        )
    ]
    for code, language in sorted(NLTK_LANGUAGES.items()):
        name = f"nltk.punkt_tab[{code}]"
        try:
            found = nltk.data.find(f"tokenizers/punkt_tab/{language}/")
            nltk.sent_tokenize("Eine Probe. Noch eine.", language=language)
            checks.append(Check(name, OK, f"{language} model at {found}"))
        except NetworkBlocked as exc:
            checks.append(Check(name, FAIL, f"tried to download the model: {exc}"))
        except LookupError:
            checks.append(
                Check(
                    name,
                    FAIL,
                    f"punkt_tab model for {language} not found - release builds bundle "
                    f"it (ADR-0014); from source run 'python -m nltk.downloader punkt_tab'",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            checks.append(Check(name, FAIL, f"{type(exc).__name__}: {exc}"))
    return checks


def _probe_library(name: str, call) -> Check:
    try:
        return Check(name, OK, str(call()))
    except NetworkBlocked as exc:
        return Check(name, FAIL, f"tried to reach the network: {exc}")
    except Exception as exc:
        return Check(name, FAIL, f"{type(exc).__name__}: {exc}")


def offline_self_check() -> list[Check]:
    """Exercise every third-party piece that could reach out, with the
    network unplugged (#42, QA-PRIV)."""

    def _langdetect() -> str:
        from langdetect import detect_langs

        return f"detected {detect_langs('This is a short English sentence.')[0]}"

    def _textstat() -> str:
        import textstat

        score = textstat.flesch_reading_ease("The cat sat on the mat.")
        return f"flesch_reading_ease sample = {score}"

    with no_network():
        checks = _probe_nltk()
        checks.append(_probe_library("langdetect", _langdetect))
        checks.append(_probe_library("textstat", _textstat))
    return checks


def _inspect_database(db_path: Path) -> tuple[dict[str, Any], list[Check]]:
    """Read-only look at the project DB: applied schema versions + integrity."""
    info: dict[str, Any] = {"path": str(db_path), "exists": db_path.exists()}
    if not db_path.exists():
        return info, [
            Check(
                "database",
                WARN,
                f"no project at {db_path.parent} ({DB_FILENAME} missing) - "
                f"run 'tta db init' first",
            )
        ]
    info["size_bytes"] = db_path.stat().st_size
    checks: list[Check] = []
    conn = None
    try:
        # read-only URI: doctor must never migrate or repair what it reports on
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        from tta.core.db import migrator

        applied = migrator.applied_versions(conn)
        info["schema_version"] = max(applied) if applied else None
        info["applied_migrations"] = applied
        shipped = [version for version, _ in migrator.available_migrations()]
        info["latest_shipped_migration"] = max(shipped) if shipped else None
        pending = sorted(set(shipped) - set(applied))
        if pending:
            checks.append(
                Check("schema_version", WARN, f"pending migrations {pending} - run 'tta db migrate'")
            )
        else:
            checks.append(Check("schema_version", OK, f"schema at {info['schema_version']}"))

        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        info["integrity_check"] = integrity
        checks.append(
            Check("integrity_check", OK if integrity == "ok" else FAIL, integrity)
        )
        counts = {}
        for table in ("theses", "module_runs", "metric_values", "artefact_files"):
            try:
                counts[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                counts[table] = None
        info["row_counts"] = counts
    except sqlite3.Error as exc:
        checks.append(Check("database", FAIL, f"{type(exc).__name__}: {exc}"))
    finally:
        if conn is not None:
            conn.close()
    return info, checks


def collect(project_dir: Path | str = ".") -> Diagnostics:
    """Everything a bug report needs, in one read-only pass (#42)."""
    project_dir = Path(project_dir)
    diag = Diagnostics()
    diag.app = {
        "version": tta.__version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
    }
    diag.runtime = {
        "python": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "os_name": os.name,
        "cpu_count": os.cpu_count(),
    }

    try:
        diag.modules = {
            m.spec.name: m.spec.version for m in default_registry().in_topological_order()
        }
        diag.checks.append(Check("module_registry", OK, f"{len(diag.modules)} modules registered"))
    except Exception as exc:
        diag.checks.append(Check("module_registry", FAIL, f"{type(exc).__name__}: {exc}"))

    db_info, db_checks = _inspect_database(project_dir / DB_FILENAME)
    diag.project = {"dir": str(project_dir.resolve()), "database": db_info}
    diag.checks.extend(db_checks)

    config_path = project_dir / CONFIG_FILENAME
    config = load_config(project_dir)
    diag.config = {
        "path": str(config_path),
        "exists": config_path.exists(),
        "workers": config.workers,
        "ui_mode": config.ui_mode,
        "outlier_scheme": config.outlier_scheme,
        "institution": config.institution,
    }

    diag.checks.extend(offline_self_check())
    return diag
