"""Export tests (ADR-0007, Sec. 8.3.1): the anonymisation rules are enforced here."""

import sqlite3

import pytest

from tta.core.export import ExportPolicy, export_database


def populate(project, tmp_path):
    """Two theses (one excluded), two runs of one module (history), PII everywhere."""
    pdf_a = tmp_path / "secret_name_a.pdf"
    pdf_a.write_bytes(b"%PDF-a")
    pdf_b = tmp_path / "secret_name_b.pdf"
    pdf_b.write_bytes(b"%PDF-b")
    a = project.repo.add_thesis(pdf_a)
    b = project.repo.add_thesis(pdf_b)
    project.repo.set_excluded(b.id, True)
    project.conn.execute(
        "UPDATE theses SET notes = 'student X, confidential', tags = '[\"secret\"]' WHERE id = ?",
        (a.id,),
    )
    with project.repo.transaction():
        project.repo.record_run(
            a.id, "mod_x", "1.0.0", "error",
            reason="boom",
            error_traceback="Traceback ... /home/prof/secret_name_a.pdf",
            metrics={"m": 1},
            notes={"debug": "content-derived"},
        )
        project.repo.record_run(a.id, "mod_x", "1.1.0", "ok", metrics={"m": 2})
        project.repo.record_run(b.id, "mod_x", "1.1.0", "ok", metrics={"m": 99})
    return a, b


def export_conn(project, tmp_path, policy=ExportPolicy.FULL):
    out = tmp_path / "out" / "export.sqlite"
    stats = export_database(project.conn, out, policy)
    conn = sqlite3.connect(out)
    conn.row_factory = sqlite3.Row
    return stats, conn


def test_pii_columns_do_not_exist_in_export(project, tmp_path):
    populate(project, tmp_path)
    _, conn = export_conn(project, tmp_path)

    theses_cols = {r["name"] for r in conn.execute("PRAGMA table_info(theses)")}
    assert {"pdf_path", "pdf_filename", "notes", "tags"}.isdisjoint(theses_cols)
    run_cols = {r["name"] for r in conn.execute("PRAGMA table_info(module_runs)")}
    assert {"error_traceback", "notes"}.isdisjoint(run_cols)

    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "artefact_files" not in tables
    assert "export_info" in tables


def test_no_pii_strings_anywhere_in_export_file(project, tmp_path):
    populate(project, tmp_path)
    stats, _ = export_conn(project, tmp_path)
    blob = stats.path.read_bytes()
    assert b"secret_name_a" not in blob  # path/filename/traceback all stripped
    assert b"student X" not in blob
    assert b"content-derived" not in blob


def test_excluded_column_is_absent_from_the_export(project, tmp_path):
    """The row filter leaves `excluded` constant-zero, so the column itself is
    stripped too (#64, ADR-0007 rev. 3) - it carried no information and hinted
    that excluded theses might ship."""
    populate(project, tmp_path)
    _, conn = export_conn(project, tmp_path)
    theses_cols = {r["name"] for r in conn.execute("PRAGMA table_info(theses)")}
    assert "excluded" not in theses_cols
    # the columns that do ship are unaffected
    assert theses_cols == {"id", "source_id", "pdf_sha256", "pdf_size_bytes", "added_at"}


def test_excluded_theses_are_stripped(project, tmp_path):
    a, b = populate(project, tmp_path)
    stats, conn = export_conn(project, tmp_path)
    assert stats.theses == 1
    ids = [r["id"] for r in conn.execute("SELECT id FROM theses")]
    assert ids == [a.id]  # ids preserved (Sec. 8.3.1); excluded thesis gone
    # ... and so are its runs and metrics
    assert conn.execute("SELECT COUNT(*) FROM module_runs WHERE thesis_id=?", (b.id,)).fetchone()[0] == 0


def test_added_at_rounded_to_day(project, tmp_path):
    populate(project, tmp_path)
    _, conn = export_conn(project, tmp_path)
    added = conn.execute("SELECT added_at FROM theses").fetchone()[0]
    assert len(added) == 10  # YYYY-MM-DD, no time-of-day fingerprint


def test_full_policy_keeps_history_current_only_trims(project, tmp_path):
    populate(project, tmp_path)
    full_stats, full = export_conn(project, tmp_path)
    assert full_stats.runs == 2  # both mod_x invocations of the included thesis

    trimmed_stats = export_database(
        project.conn, tmp_path / "trimmed.sqlite", ExportPolicy.CURRENT_ONLY
    )
    trimmed = sqlite3.connect(trimmed_stats.path)
    assert trimmed_stats.runs == 1
    assert trimmed.execute("SELECT module_version FROM module_runs").fetchone()[0] == "1.1.0"


def test_export_info_metadata(project, tmp_path):
    populate(project, tmp_path)
    _, conn = export_conn(project, tmp_path)
    info = dict(conn.execute("SELECT key, value FROM export_info"))
    assert info["schema_version"] == "1"
    assert info["policy"] == "full"
    assert info["thesis_count"] == "1"


def test_refuses_to_overwrite(project, tmp_path):
    populate(project, tmp_path)
    out = tmp_path / "existing.sqlite"
    out.write_bytes(b"do not clobber")
    with pytest.raises(FileExistsError):
        export_database(project.conn, out)
    assert out.read_bytes() == b"do not clobber"
