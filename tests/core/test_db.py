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


def _make_pdfs(tmp_path, count, prefix="t"):
    paths = []
    for n in range(count):
        pdf = tmp_path / f"{prefix}{n}.pdf"
        pdf.write_bytes(b"%PDF-" + str(n).encode())
        paths.append(pdf)
    return paths


class CountingConnection:
    """Delegating proxy that tallies commits (sqlite3.Connection is immutable,
    so it cannot be monkeypatched in place)."""

    def __init__(self, conn):
        self._conn = conn
        self.commits = 0

    def commit(self):
        self.commits += 1
        return self._conn.commit()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_add_theses_commits_once_per_batch(project, tmp_path):
    """O(1) commits, not O(N) (#61, ADR-0006 rev. 6). One fsync per PDF was
    the real cost of adding a folder; count the commits to pin it down."""
    paths = _make_pdfs(tmp_path, 25)
    counting = CountingConnection(project.conn)
    repo = Repository(counting)

    added = repo.add_theses(paths)

    assert len(added) == 25
    assert counting.commits == 1  # one transaction for the batch, not 25
    assert len(project.repo.list_theses()) == 25


def test_add_thesis_one_by_one_would_cost_one_commit_each(project, tmp_path):
    """The regression this fixes: the per-file loop the adapters used to run
    cost one durable commit per PDF (#61)."""
    paths = _make_pdfs(tmp_path, 5)
    counting = CountingConnection(project.conn)
    repo = Repository(counting)
    for path in paths:
        repo.add_thesis(path)
    assert counting.commits == 5  # ... which is why the adapters now batch


def test_add_thesis_still_commits_once_and_matches_the_batch_path(project, tmp_path):
    """add_thesis is a one-element delegate; the single-add contract is
    unchanged (hash NULL, size from stat, path-addressed identity)."""
    pdf = tmp_path / "solo.pdf"
    pdf.write_bytes(b"%PDF-solo")
    single = project.repo.add_thesis(pdf)
    batched = project.repo.add_theses([pdf])
    assert batched == [single]  # same row, re-add updates rather than inserts
    assert single.pdf_sha256 is None
    assert len(project.repo.list_theses()) == 1


def test_add_theses_returns_rows_in_first_appearance_order(project, tmp_path):
    """One Thesis per distinct path, in input order; a path repeated inside one
    batch resolves to a single row, exactly as re-adding it would (#61)."""
    a, b = _make_pdfs(tmp_path, 2)
    added = project.repo.add_theses([b, a, b, str(b)])
    assert [t.pdf_filename for t in added] == ["t1.pdf", "t0.pdf"]
    assert len(project.repo.list_theses()) == 2


def test_add_theses_mixes_new_rows_and_re_adds(project, tmp_path):
    """The batched dedup SELECT must classify each path correctly: existing
    paths update in place (identity + history kept), new paths insert."""
    a, b = _make_pdfs(tmp_path, 2)
    first = project.repo.add_thesis(a)
    with project.repo.transaction():
        project.repo.record_run(first.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
    a.write_bytes(b"%PDF-grown-larger")  # size changes; the re-add picks it up

    added = project.repo.add_theses([a, b])

    assert added[0].id == first.id  # same row, not a duplicate
    assert added[1].id != first.id
    assert len(project.repo.list_theses()) == 2
    row = project.conn.execute(
        "SELECT pdf_size_bytes FROM theses WHERE id = ?", (first.id,)
    ).fetchone()
    assert row["pdf_size_bytes"] == len(b"%PDF-grown-larger")
    assert project.repo.latest_runs()[(first.id, "mod_x")] is not None  # history kept


def test_add_theses_chunks_large_batches(project, tmp_path, monkeypatch):
    """Very large batches are split across transactions so a failure part-way
    does not discard what already committed (#61)."""
    monkeypatch.setattr("tta.core.db.repository._ADD_CHUNK", 4)
    paths = _make_pdfs(tmp_path, 10)
    added = project.repo.add_theses(paths)
    assert len(added) == 10
    assert [t.pdf_filename for t in added] == [p.name for p in paths]
    assert len(project.repo.list_theses()) == 10


def test_add_theses_missing_file_leaves_earlier_chunks_committed(project, tmp_path, monkeypatch):
    """A vanished path aborts its own chunk with nothing written (the stat
    happens before the transaction opens), but earlier chunks stay (#61)."""
    monkeypatch.setattr("tta.core.db.repository._ADD_CHUNK", 2)
    a, b, c = _make_pdfs(tmp_path, 3)
    missing = tmp_path / "gone.pdf"
    with pytest.raises(FileNotFoundError):
        project.repo.add_theses([a, b, c, missing])
    # chunk 1 (a, b) committed; chunk 2 (c, missing) wrote nothing at all
    assert [t.pdf_filename for t in project.repo.list_theses()] == ["t0.pdf", "t1.pdf"]


def test_add_theses_empty_batch_is_a_noop(project):
    assert project.repo.add_theses([]) == []


def test_excluded_filtering(project, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    project.repo.set_excluded(thesis.id, True)
    assert project.repo.list_theses(include_excluded=False) == []
    assert len(project.repo.list_theses(include_excluded=True)) == 1


def test_purge_analysis_scrubs_rows_and_disk_keeps_thesis(project, tmp_path):
    """Excluding an already-analysed thesis scrubs its cached analysis
    (US-PROF-EXCLUDE, ADR-0006 rev. 5, #11): the metric/run/artefact rows and
    the on-disk artefacts/<id>/ tree go, the theses row stays excluded=1."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-content")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        run_id = project.repo.record_run(
            thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1}
        )
        src = tmp_path / "raw_text.txt"
        src.write_text("secret extracted text", encoding="utf-8")
        rel = project.store.store(thesis.id, run_id, "raw_text", src)
        project.repo.record_artefact(thesis.id, "raw_text", rel, run_id)
    tree = project.dir / "artefacts" / str(thesis.id)
    assert tree.exists()

    project.repo.set_excluded(thesis.id, True)
    project.repo.purge_analysis(thesis.id, store=project.store)

    # the three row-sets are gone
    assert project.conn.execute("SELECT COUNT(*) AS n FROM module_runs").fetchone()["n"] == 0
    assert project.conn.execute("SELECT COUNT(*) AS n FROM metric_values").fetchone()["n"] == 0
    assert project.conn.execute("SELECT COUNT(*) AS n FROM artefact_files").fetchone()["n"] == 0
    assert project.repo.current_artefacts(thesis.id) == {}
    # the on-disk artefact subtree is removed
    assert not tree.exists()
    # the theses row is kept with excluded=1 (identity remembered)
    kept = project.repo.get_thesis(thesis.id)
    assert kept.excluded is True
    # the source PDF is untouched
    assert pdf.exists() and pdf.read_bytes() == b"%PDF-content"


def test_purge_analysis_is_robust_without_store_or_artefacts(project, tmp_path):
    """purge_analysis works DB-only (no store) and when nothing was cached."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
    # no store passed, no artefacts dir on disk: must not raise
    project.repo.purge_analysis(thesis.id)
    assert project.repo.latest_runs() == {}
    # a store call on a thesis whose subtree does not exist is a no-op
    project.repo.purge_analysis(thesis.id, store=project.store)


def test_purge_analysis_surfaces_disk_failure_after_db_scrub(project, tmp_path, monkeypatch):
    """A filesystem failure during the scrub is not swallowed (#11 review):
    purge_analysis raises so the caller can warn. The DB scrub commits first,
    so the rows are already gone; the residual files never leave the machine."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-content")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        run_id = project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
        src = tmp_path / "raw_text.txt"
        src.write_text("secret", encoding="utf-8")
        rel = project.store.store(thesis.id, run_id, "raw_text", src)
        project.repo.record_artefact(thesis.id, "raw_text", rel, run_id)

    def _boom(self, thesis_id):
        raise PermissionError("file is locked")

    monkeypatch.setattr("tta.core.artefacts.ArtefactStore.purge", _boom)

    project.repo.set_excluded(thesis.id, True)
    with pytest.raises(OSError):
        project.repo.purge_analysis(thesis.id, store=project.store)

    # DB scrub committed before the (failed) disk step: rows already gone
    assert project.repo.latest_runs() == {}
    assert project.conn.execute("SELECT COUNT(*) AS n FROM metric_values").fetchone()["n"] == 0
    # theses row kept with the exclusion persisted
    assert project.repo.get_thesis(thesis.id).excluded is True


def _analyse(project, thesis, tmp_path, text=b"secret extracted text"):
    """Give a thesis one cached run with an on-disk artefact."""
    with project.repo.transaction():
        run_id = project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
        src = tmp_path / f"raw_{thesis.id}.txt"
        src.write_bytes(text)
        rel = project.store.store(thesis.id, run_id, "raw_text", src)
        project.repo.record_artefact(thesis.id, "raw_text", rel, run_id)
    return run_id


def test_delete_thesis_forgets_the_row_and_the_analysis(project, tmp_path):
    """Remove is the harder version of exclude (#63, ADR-0006 rev. 7): unlike
    purge_analysis it takes the theses row too, so the same PDF can be added
    again as a fresh thesis with no history."""
    pdf = tmp_path / "mistake.pdf"
    pdf.write_bytes(b"%PDF-content")
    thesis = project.repo.add_thesis(pdf)
    _analyse(project, thesis, tmp_path)
    tree = project.dir / "artefacts" / str(thesis.id)
    assert tree.exists()

    project.repo.delete_thesis(thesis.id, store=project.store)

    for table in ("module_runs", "metric_values", "artefact_files", "theses"):
        n = project.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        assert n == 0, f"{table} still has rows"
    with pytest.raises(KeyError):
        project.repo.get_thesis(thesis.id)
    assert not tree.exists()  # on-disk PII artefacts gone
    assert pdf.exists() and pdf.read_bytes() == b"%PDF-content"  # source PDF untouched


def test_removed_pdf_can_be_re_added_as_a_fresh_thesis(project, tmp_path):
    """The whole point of deleting the row: the remembered row would otherwise
    keep blocking a clean re-add of the same file (#63). Re-adding gives a
    brand-new thesis - no runs, no metrics, hash deferred again. (SQLite may
    hand back the same integer id, since it reuses a freed rowid; what matters
    is that nothing of the old thesis survives.)"""
    pdf = tmp_path / "mistake.pdf"
    pdf.write_bytes(b"%PDF-content")
    first = project.repo.add_thesis(pdf)
    project.repo.assign_content_hash(first)  # hashed, so the row is fully-formed
    _analyse(project, first, tmp_path)
    project.repo.delete_thesis(first.id, store=project.store)

    again = project.repo.add_thesis(pdf)
    assert again.pdf_sha256 is None  # hashing deferred again: no identity carried over
    assert project.repo.latest_runs() == {}
    assert project.repo.current_metrics() == []
    assert project.repo.current_artefacts(again.id) == {}
    assert len(project.repo.list_theses()) == 1


def test_delete_thesis_differs_from_purge_analysis(project, tmp_path):
    """Side by side: purge keeps the row (identity remembered, excluded=1),
    delete does not (identity forgotten). Sibling rows are untouched by both."""
    kept_pdf = tmp_path / "kept.pdf"
    kept_pdf.write_bytes(b"%PDF-kept")
    gone_pdf = tmp_path / "gone.pdf"
    gone_pdf.write_bytes(b"%PDF-gone")
    other_pdf = tmp_path / "other.pdf"
    other_pdf.write_bytes(b"%PDF-other")
    kept, gone, other = project.repo.add_theses([kept_pdf, gone_pdf, other_pdf])
    for thesis in (kept, gone, other):
        _analyse(project, thesis, tmp_path)

    project.repo.set_excluded(kept.id, True)
    project.repo.purge_analysis(kept.id, store=project.store)
    project.repo.delete_thesis(gone.id, store=project.store)

    assert project.repo.get_thesis(kept.id).excluded is True  # row remembered
    with pytest.raises(KeyError):
        project.repo.get_thesis(gone.id)  # row forgotten
    # the untouched sibling keeps its run and its artefacts
    assert project.repo.latest_runs()[(other.id, "mod_x")]["status"] == "ok"
    assert (project.dir / "artefacts" / str(other.id)).exists()


def test_delete_thesis_works_without_a_store_or_any_analysis(project, tmp_path):
    pdf = tmp_path / "never_run.pdf"
    pdf.write_bytes(b"x")
    thesis = project.repo.add_thesis(pdf)
    project.repo.delete_thesis(thesis.id)  # no store, nothing cached: must not raise
    assert project.repo.list_theses() == []


def test_delete_thesis_unknown_id_raises(project):
    """An adapter must not be able to report a removal that never happened."""
    with pytest.raises(KeyError):
        project.repo.delete_thesis(999)


def test_delete_thesis_surfaces_disk_failure_after_db_delete(project, tmp_path, monkeypatch):
    """Same contract as purge_analysis: the DB commit precedes the filesystem
    step, and an OSError propagates instead of claiming a clean removal."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-content")
    thesis = project.repo.add_thesis(pdf)
    _analyse(project, thesis, tmp_path)

    def _boom(self, thesis_id):
        raise PermissionError("file is locked")

    monkeypatch.setattr("tta.core.artefacts.ArtefactStore.purge", _boom)
    with pytest.raises(OSError):
        project.repo.delete_thesis(thesis.id, store=project.store)

    # rows already gone (DB-first ordering)
    with pytest.raises(KeyError):
        project.repo.get_thesis(thesis.id)
    assert project.repo.latest_runs() == {}


def test_dedup_fold_uses_the_shared_delete_implementation(project, tmp_path, monkeypatch):
    """One delete implementation, not two (#63): the content-dedup fold - until
    now the only place executing DELETE FROM theses - calls the same helper."""
    a = tmp_path / "a.pdf"
    a.write_bytes(b"%PDF-identical")
    b = tmp_path / "b.pdf"
    b.write_bytes(b"%PDF-identical")
    first, second = project.repo.add_theses([a, b])
    project.repo.assign_content_hash(first)

    deleted: list[int] = []
    real = Repository._delete_thesis_rows

    def spy(self, thesis_id):
        deleted.append(thesis_id)
        return real(self, thesis_id)

    monkeypatch.setattr(Repository, "_delete_thesis_rows", spy)
    assert project.repo.assign_content_hash(second) == first.id
    assert deleted == [second.id]
    assert len(project.repo.list_theses()) == 1


def test_module_duration_stats_mean_rate_per_module(project, tmp_path):
    """The ETA history query returns mean(duration_ms / pdf_size_bytes) over ok
    runs, per module, guarding NULL/zero sizes and non-ok runs (#39)."""
    a = tmp_path / "a.pdf"
    a.write_bytes(b"x" * 100)  # 100 bytes
    b = tmp_path / "b.pdf"
    b.write_bytes(b"x" * 50)  # 50 bytes
    ta = project.repo.add_thesis(a)
    tb = project.repo.add_thesis(b)
    with project.repo.transaction():
        # mod_a: 200ms/100B = 2.0 and 50ms/50B = 1.0 -> mean 1.5 ms/byte
        project.repo.record_run(ta.id, "mod_a", "1.0.0", "ok", duration_ms=200)
        project.repo.record_run(tb.id, "mod_a", "1.0.0", "ok", duration_ms=50)
        # an errored run is ignored
        project.repo.record_run(ta.id, "mod_a", "1.0.0", "error", duration_ms=999)
        # a run without a duration is ignored
        project.repo.record_run(tb.id, "mod_b", "1.0.0", "ok", duration_ms=None)

    stats = project.repo.module_duration_stats()
    assert stats["mod_a"] == pytest.approx(1.5)
    assert "mod_b" not in stats  # only run had no duration


def test_module_duration_stats_skips_zero_size(project, tmp_path):
    """A zero-byte PDF (size 0) cannot form a rate; it is guarded out (#39)."""
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    thesis = project.repo.add_thesis(empty)
    with project.repo.transaction():
        project.repo.record_run(thesis.id, "mod_a", "1.0.0", "ok", duration_ms=10)
    assert project.repo.module_duration_stats() == {}


def test_thesis_sizes_maps_id_to_bytes(project, tmp_path):
    a = tmp_path / "a.pdf"
    a.write_bytes(b"x" * 42)
    thesis = project.repo.add_thesis(a)
    assert project.repo.thesis_sizes()[thesis.id] == 42


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
