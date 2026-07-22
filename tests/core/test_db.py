"""Migrator + repository tests (SDD Sec. 8.1, ADR-0006)."""

import json
import shutil
import sqlite3

import pytest

from tta.core import db
from tta.core.db import migrator
from tta.core.db.repository import Repository


def test_migrate_fresh_db_applies_initial(tmp_path):
    applied = migrator.migrate(tmp_path / "tta.sqlite")
    assert applied == [1]


def test_migrate_is_idempotent(tmp_path):
    db_path = tmp_path / "tta.sqlite"
    assert migrator.migrate(db_path) == [1]
    assert migrator.migrate(db_path) == []
    assert not list(tmp_path.glob("*.bak.*"))  # no pending work -> no backup


def test_migrate_existing_db_writes_defensive_backup(tmp_path):
    db_path = tmp_path / "tta.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE legacy (x)")
    conn.commit()
    conn.close()
    migrator.migrate(db_path)
    assert (tmp_path / "tta.sqlite.bak.1").exists()


def test_local_source_is_singleton(project):
    first = project.repo.ensure_local_source()
    second = project.repo.ensure_local_source()
    assert first == second
    rows = project.conn.execute("SELECT COUNT(*) AS n FROM sources WHERE kind='local'").fetchone()
    assert rows["n"] == 1


def test_add_is_instant_and_defers_hash(project, tmp_path):
    """Add reads no bytes (ADR-0006 rev. 4, #38): pdf_sha256 stays NULL and
    size comes from a cheap stat, until the first run assigns the hash."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-fake content")
    thesis = project.repo.add_thesis(pdf)
    assert thesis.pdf_sha256 is None
    row = project.conn.execute(
        "SELECT pdf_sha256, pdf_size_bytes FROM theses WHERE id = ?", (thesis.id,)
    ).fetchone()
    assert row["pdf_sha256"] is None
    assert row["pdf_size_bytes"] == len(b"%PDF-fake content")


def test_add_thesis_is_path_addressed(project, tmp_path):
    """Add-time dedup keys on path, not content (rev. 4): re-adding the same
    path keeps identity + history; a moved/renamed file is a new row until
    run-time content-dedup reunites them."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-fake content")
    first = project.repo.add_thesis(pdf)
    again = project.repo.add_thesis(pdf)  # same path -> same row
    assert again.id == first.id

    renamed = tmp_path / "renamed.pdf"
    shutil.move(pdf, renamed)
    moved = project.repo.add_thesis(renamed)  # new path -> new row (not yet hashed)
    assert moved.id != first.id
    assert len(project.repo.list_theses()) == 2


def test_assign_content_hash_sets_then_dedups(project, tmp_path):
    """At run time the hash is computed once; a byte-identical sibling under a
    different path is folded into the canonical (earlier) row (rev. 4, #38)."""
    a = tmp_path / "a.pdf"
    a.write_bytes(b"%PDF-identical")
    b = tmp_path / "b.pdf"
    b.write_bytes(b"%PDF-identical")
    first = project.repo.add_thesis(a)
    second = project.repo.add_thesis(b)

    canonical = project.repo.assign_content_hash(first)
    assert canonical == first.id
    assert project.repo.get_thesis(first.id).pdf_sha256 is not None
    # idempotent: a second call is a no-op once hashed
    assert project.repo.assign_content_hash(project.repo.get_thesis(first.id)) == first.id

    folded = project.repo.assign_content_hash(second)
    assert folded == first.id  # identical content -> folded into the canonical
    assert len(project.repo.list_theses()) == 1
    with pytest.raises(KeyError):
        project.repo.get_thesis(second.id)
    # the canonical adopted the most-recently-seen path
    assert project.repo.get_thesis(first.id).pdf_filename == "b.pdf"


def test_add_thesis_rejects_unknown_type(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    with pytest.raises(ValueError, match="thesis type"):
        project.repo.add_thesis(pdf, type="diploma")


def test_excluded_filtering(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    project.repo.set_excluded(thesis.id, True)
    assert project.repo.list_theses(include_excluded=False) == []
    assert len(project.repo.list_theses(include_excluded=True)) == 1


def test_record_run_metric_typing(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        run_id = project.repo.record_run(
            thesis.id,
            "mod_x",
            "1.0.0",
            "ok",
            metrics={"n": 42, "f": 1.5, "flag": True, "label": "ok", "missing": None},
        )
    rows = {
        r["metric_name"]: (r["value_num"], r["value_text"])
        for r in project.conn.execute("SELECT * FROM metric_values WHERE run_id=?", (run_id,))
    }
    assert rows["n"] == (42.0, None)
    assert rows["f"] == (1.5, None)
    assert rows["flag"] == (1.0, None)
    assert rows["label"] == (None, "ok")
    assert rows["missing"] == (None, None)


def test_record_run_persists_notes_as_json(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        with_notes = project.repo.record_run(
            thesis.id, "mod_x", "1.0.0", "ok", notes={"stop_word_ratio": 0.21}
        )
        without_notes = project.repo.record_run(thesis.id, "mod_y", "1.0.0", "ok")
    rows = {
        r["id"]: r["notes"]
        for r in project.conn.execute("SELECT id, notes FROM module_runs")
    }
    assert json.loads(rows[with_notes]) == {"stop_word_ratio": 0.21}
    assert rows[without_notes] is None  # empty notes stay NULL, not "{}"


def test_record_run_rejects_unsupported_metric_type(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    with pytest.raises(TypeError, match="unsupported value type"):
        with project.repo.transaction():
            project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"bad": [1]})


def test_append_only_history_and_current_view(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
        project.repo.record_run(thesis.id, "mod_x", "1.1.0", "ok", metrics={"m": 2})

    history = project.conn.execute(
        "SELECT module_version, recency_rank FROM v_module_run_history"
        " WHERE thesis_id=? ORDER BY recency_rank",
        (thesis.id,),
    ).fetchall()
    assert [(r["module_version"], r["recency_rank"]) for r in history] == [("1.1.0", 1), ("1.0.0", 2)]

    current = project.repo.current_metrics()
    assert len(current) == 1
    assert current[0]["value_num"] == 2.0
    assert current[0]["module_version"] == "1.1.0"

    latest = project.repo.latest_runs()
    assert latest[(thesis.id, "mod_x")]["module_version"] == "1.1.0"


def test_artefact_reference_upsert(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        run_1 = project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok")
        project.repo.record_artefact(thesis.id, "raw_text", "artefacts/1/1/raw_text.txt", run_1)
        run_2 = project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok")
        project.repo.record_artefact(thesis.id, "raw_text", "artefacts/1/2/raw_text.txt", run_2)
    assert project.repo.current_artefacts(thesis.id) == {"raw_text": "artefacts/1/2/raw_text.txt"}


def test_transaction_rolls_back_on_error(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    with pytest.raises(RuntimeError):
        with project.repo.transaction():
            project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
            raise RuntimeError("boom")
    assert project.repo.latest_runs() == {}
