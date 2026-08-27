"""Export tests (ADR-0007, Sec. 8.3.1): the anonymisation rules are enforced here."""

import csv
import sqlite3

import pytest

from tta.core.export import (
    PROFILING_COLUMNS,
    ExportPolicy,
    export_database,
    export_profiling,
)


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
            diagnostics={"debug": "content-derived"},
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
    assert {"error_traceback", "diagnostics"}.isdisjoint(run_cols)

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


# -- profiling export (#47, ADR-0015, QA-RES) --------------------------------


def profiling_rows(project, tmp_path, policy=ExportPolicy.FULL, name="profiling.csv"):
    stats = export_profiling(project.conn, tmp_path / "out" / name, policy)
    with open(stats.path, encoding="utf-8", newline="") as handle:
        return stats, list(csv.DictReader(handle))


def test_profiling_export_has_one_row_per_run_with_a_derived_rate(project, tmp_path):
    """duration_ms per (thesis, module) plus the ms/byte rate the ADR-0015
    budgets are actually about (#47)."""
    a, _b = populate(project, tmp_path)
    project.conn.execute("UPDATE theses SET pdf_size_bytes = 100 WHERE id = ?", (a.id,))
    project.conn.execute("UPDATE module_runs SET duration_ms = 250")
    project.conn.commit()

    stats, rows = profiling_rows(project, tmp_path)

    assert list(rows[0]) == list(PROFILING_COLUMNS)
    assert stats.rows == len(rows) == 2  # both mod_x runs of the included thesis
    assert stats.modules == 1
    assert {r["module_name"] for r in rows} == {"mod_x"}
    assert {r["duration_ms"] for r in rows} == {"250"}
    assert {float(r["ms_per_byte"]) for r in rows} == {2.5}  # 250 ms / 100 bytes


def test_profiling_export_omits_pii_and_imported_and_excluded(project, tmp_path):
    """Same two rules as the cohort export: local source only, no PII column -
    and the excluded thesis's runs are absent like its rows are (#47)."""
    _a, b = populate(project, tmp_path)
    stats, rows = profiling_rows(project, tmp_path)

    assert set(PROFILING_COLUMNS).isdisjoint(
        {"pdf_path", "pdf_filename", "notes", "tags", "error_traceback"}
    )
    blob = stats.path.read_bytes()
    assert b"secret_name" not in blob and b"student X" not in blob
    assert b"Traceback" not in blob  # the errored run ships its status, not its traceback
    assert all(int(r["thesis_id"]) != b.id for r in rows)


def test_profiling_export_keeps_errored_and_na_runs(project, tmp_path):
    """A module that reliably fails after 30 s is exactly what a performance
    investigation is looking for, so non-ok runs stay (#47)."""
    populate(project, tmp_path)
    _, rows = profiling_rows(project, tmp_path)
    assert {r["status"] for r in rows} == {"error", "ok"}


def test_profiling_export_blank_rate_when_size_or_duration_missing(project, tmp_path):
    """No rate exists without a duration and a positive size; the cell is left
    empty rather than fabricated or zero (matches module_duration_stats)."""
    a, _ = populate(project, tmp_path)
    project.conn.execute("UPDATE theses SET pdf_size_bytes = 0 WHERE id = ?", (a.id,))
    project.conn.commit()
    _, zero_size = profiling_rows(project, tmp_path, name="zero.csv")
    assert {r["ms_per_byte"] for r in zero_size} == {""}

    project.conn.execute("UPDATE theses SET pdf_size_bytes = NULL WHERE id = ?", (a.id,))
    project.conn.commit()
    _, null_size = profiling_rows(project, tmp_path, name="null.csv")
    assert {r["ms_per_byte"] for r in null_size} == {""}
    assert {r["pdf_size_bytes"] for r in null_size} == {""}
    assert {r["duration_ms"] for r in null_size} == {""}  # populate records no durations


def test_profiling_export_current_only_trims_history(project, tmp_path):
    """--current-only composes with --profiling, as it does with the cohort
    export: the latest run per (thesis, module) only."""
    populate(project, tmp_path)
    full, full_rows = profiling_rows(project, tmp_path, name="full.csv")
    trimmed, trimmed_rows = profiling_rows(
        project, tmp_path, ExportPolicy.CURRENT_ONLY, name="trimmed.csv"
    )
    assert full.rows == 2 and trimmed.rows == 1
    assert {r["module_version"] for r in trimmed_rows} == {"1.1.0"}
    assert {r["module_version"] for r in full_rows} == {"1.0.0", "1.1.0"}
    assert trimmed.policy is ExportPolicy.CURRENT_ONLY


def test_profiling_export_of_an_empty_project_is_a_header_only_file(project, tmp_path):
    stats, rows = profiling_rows(project, tmp_path)
    assert stats.rows == 0 and stats.modules == 0 and rows == []
    assert stats.path.read_text(encoding="utf-8").splitlines() == [",".join(PROFILING_COLUMNS)]


def test_profiling_export_refuses_to_overwrite(project, tmp_path):
    populate(project, tmp_path)
    out = tmp_path / "existing.csv"
    out.write_bytes(b"do not clobber")
    with pytest.raises(FileExistsError):
        export_profiling(project.conn, out)
    assert out.read_bytes() == b"do not clobber"
