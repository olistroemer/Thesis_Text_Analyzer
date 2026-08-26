"""Diagnostics bundle for support / bug reports (#42, ADR-0003)."""

import socket
import sqlite3

import pytest

from tta.core import doctor


def test_collect_reports_app_runtime_and_modules(tmp_path):
    diag = doctor.collect(tmp_path)
    assert diag.app["version"]
    assert diag.runtime["python"] and diag.runtime["platform"]
    assert "mod_tokenize" in diag.modules
    assert {c.name for c in diag.checks} >= {
        "module_registry",
        "nltk.punkt_tab[de]",
        "nltk.punkt_tab[en]",
        "langdetect",
        "textstat",
    }


def test_missing_project_is_a_warning_not_a_failure(tmp_path):
    """A user filing a bug report may have no project yet."""
    diag = doctor.collect(tmp_path)
    database = next(c for c in diag.checks if c.name == "database")
    assert database.status == "warn"
    assert diag.failed == []
    assert diag.status == "warn"


def test_reports_schema_version_and_integrity(project):
    diag = doctor.collect(project.dir)
    info = diag.project["database"]
    assert info["exists"] is True
    assert info["schema_version"] >= 1
    assert info["integrity_check"] == "ok"
    assert info["row_counts"]["theses"] == 0
    assert {c.name for c in diag.checks} >= {"schema_version", "integrity_check"}
    assert diag.status == "ok"


def test_is_read_only_and_never_migrates(tmp_path):
    """A diagnostic that repairs what it inspects hides the reported fault:
    doctor must not create the project, nor migrate an existing one."""
    doctor.collect(tmp_path)
    assert not (tmp_path / "tta.sqlite").exists()
    assert list(tmp_path.iterdir()) == []

    # an un-migrated database keeps its (absent) schema and gains no tables
    db_path = tmp_path / "tta.sqlite"
    sqlite3.connect(db_path).close()
    diag = doctor.collect(tmp_path)
    assert diag.project["database"]["schema_version"] is None
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    conn.close()
    assert tables == []
    pending = next(c for c in diag.checks if c.name == "schema_version")
    assert pending.status == "warn" and "pending migrations" in pending.detail


def test_corrupt_database_is_reported_not_raised(tmp_path):
    (tmp_path / "tta.sqlite").write_bytes(b"this is not a database at all")
    diag = doctor.collect(tmp_path)
    assert diag.failed  # surfaced as a failing check, not an exception
    assert any(c.name in ("database", "integrity_check") for c in diag.failed)


def test_no_network_blocks_outbound_connections_and_restores():
    with doctor.no_network():
        with pytest.raises(doctor.NetworkBlocked):
            socket.create_connection(("example.invalid", 80))
        with pytest.raises(doctor.NetworkBlocked):
            socket.socket().connect(("example.invalid", 80))
    # restored afterwards: a real (failing) resolution, not NetworkBlocked
    with pytest.raises(OSError) as excinfo:
        socket.create_connection(("example.invalid", 80), timeout=0.1)
    assert not isinstance(excinfo.value, doctor.NetworkBlocked)


def test_offline_self_check_actually_runs_with_the_network_down():
    """QA-PRIV: the probes must succeed from local data alone (#42)."""
    checks = doctor.offline_self_check()
    assert checks
    assert [c for c in checks if c.status == "fail"] == []


def test_to_dict_is_json_serialisable(tmp_path):
    import json

    payload = json.loads(json.dumps(doctor.collect(tmp_path).to_dict()))
    assert payload["status"] in ("ok", "warn", "fail")
    assert all({"name", "status", "detail"} == set(c) for c in payload["checks"])
