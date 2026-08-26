"""CLI integration tests for the add / remove / export surface.

Kept in its own file (rather than appended to test_cli.py) so parallel
feature branches touching the CLI do not collide.
"""

import json

import pytest
from click.testing import CliRunner

from tta.cli.main import cli

runner = CliRunner()


def invoke(*args, expect_exit=0):
    result = runner.invoke(cli, [str(a) for a in args], catch_exceptions=False)
    assert result.exit_code == expect_exit, result.output + result.stderr
    return result


@pytest.fixture
def project_dir(tmp_path):
    invoke("-C", tmp_path / "proj", "db", "init")
    return tmp_path / "proj"


def _pdf_tree(root):
    """Two PDFs at the top level, one nested, one uppercase, one non-PDF."""
    for rel in ("a.pdf", "b.pdf", "sub/c.pdf", "sub/D.PDF"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-" + rel.encode())
    (root / "readme.txt").write_bytes(b"not a thesis")
    return root


def test_run_adds_a_folder_recursively_including_uppercase(project_dir, tmp_path):
    """The shared core collector recurses and matches `.pdf` case-insensitively,
    so a `.PDF` is no longer skipped silently (#62)."""
    folder = _pdf_tree(tmp_path / "theses")
    invoke("-C", project_dir, "run", folder, "--dry-run")
    rows = json.loads(invoke("-C", project_dir, "list", "--format", "json").stdout)
    assert sorted(r["filename"] for r in rows) == ["D.PDF", "a.pdf", "b.pdf", "c.pdf"]


def test_run_skips_a_non_pdf_named_explicitly(project_dir, tmp_path):
    """An explicitly named non-PDF is skipped rather than added as a thesis
    that would only fail extraction later (#62)."""
    pdf = tmp_path / "real.pdf"
    pdf.write_bytes(b"%PDF-real")
    txt = tmp_path / "notes.txt"
    txt.write_bytes(b"text")
    invoke("-C", project_dir, "run", pdf, txt, "--dry-run")
    rows = json.loads(invoke("-C", project_dir, "list", "--format", "json").stdout)
    assert [r["filename"] for r in rows] == ["real.pdf"]


def test_run_adds_the_whole_input_set_with_one_summary_line(project_dir, tmp_path):
    """One batched transaction and one stderr summary line, not one per file
    (#61)."""
    folder = _pdf_tree(tmp_path / "theses")
    result = invoke("-C", project_dir, "run", folder, "--dry-run")
    assert "added 4 theses" in " ".join(result.stderr.split())
    assert result.stderr.count("added") == 1


def test_re_running_the_same_folder_adds_no_duplicates(project_dir, tmp_path):
    folder = _pdf_tree(tmp_path / "theses")
    invoke("-C", project_dir, "run", folder, "--dry-run")
    invoke("-C", project_dir, "run", folder, "--dry-run")
    rows = json.loads(invoke("-C", project_dir, "list", "--format", "json").stdout)
    assert len(rows) == 4


# -- tta remove (#63) --------------------------------------------------------


def _seed(project_dir, *, analysed: bool, name="seed.pdf"):
    """Add a thesis directly (fast), optionally with a cached run + artefact."""
    from tta.core import db
    from tta.core.artefacts import ArtefactStore
    from tta.core.db.repository import Repository

    pdf = project_dir / name
    pdf.write_bytes(b"%PDF-" + name.encode())
    conn = db.connect(project_dir / "tta.sqlite")
    repo = Repository(conn)
    thesis = repo.add_thesis(pdf)
    if analysed:
        store = ArtefactStore(project_dir)
        with repo.transaction():
            run_id = repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
            src = project_dir / f"raw_{thesis.id}.txt"
            src.write_text("secret extracted text", encoding="utf-8")
            rel = store.store(thesis.id, run_id, "raw_text", src)
            repo.record_artefact(thesis.id, "raw_text", rel, run_id)
    conn.close()
    return thesis.id, pdf


def _rows(project_dir):
    return json.loads(invoke("-C", project_dir, "list", "--format", "json").stdout)


def test_remove_yes_forgets_the_thesis(project_dir):
    """`tta remove <id> --yes` deletes the analysis and the row itself (#63),
    where `exclude` would have kept the row."""
    thesis_id, pdf = _seed(project_dir, analysed=True)
    tree = project_dir / "artefacts" / str(thesis_id)
    assert tree.exists()

    result = invoke("-C", project_dir, "remove", thesis_id, "--yes")
    assert f"removed thesis {thesis_id}" in result.stdout
    assert _rows(project_dir) == []  # the row is gone, not merely excluded
    assert not tree.exists()  # PII artefacts gone from disk
    assert pdf.exists()  # source PDF untouched


def test_remove_confirm_yes_and_no(project_dir):
    """Without --yes the removal is gated: 'n' aborts with no changes."""
    thesis_id, _ = _seed(project_dir, analysed=True)

    declined = runner.invoke(
        cli, ["-C", str(project_dir), "remove", str(thesis_id)], input="n\n"
    )
    assert declined.exit_code == 0, declined.output
    assert "aborted" in declined.output
    assert len(_rows(project_dir)) == 1

    confirmed = runner.invoke(
        cli, ["-C", str(project_dir), "remove", str(thesis_id)], input="y\n"
    )
    assert confirmed.exit_code == 0, confirmed.output
    assert _rows(project_dir) == []


def test_remove_prompts_even_for_a_never_analysed_thesis(project_dir):
    """Unlike exclude, removal always confirms: there is no row left to undo
    it with, analysed or not (#63)."""
    thesis_id, _ = _seed(project_dir, analysed=False)
    declined = runner.invoke(
        cli, ["-C", str(project_dir), "remove", str(thesis_id)], input="n\n"
    )
    assert "aborted" in declined.output
    assert len(_rows(project_dir)) == 1


def test_remove_leaves_siblings_alone(project_dir):
    keep_id, _ = _seed(project_dir, analysed=True, name="keep.pdf")
    drop_id, _ = _seed(project_dir, analysed=True, name="drop.pdf")
    invoke("-C", project_dir, "remove", drop_id, "--yes")
    rows = _rows(project_dir)
    assert [r["id"] for r in rows] == [keep_id]
    assert rows[0]["ok"] == 1  # its run history survived
    assert (project_dir / "artefacts" / str(keep_id)).exists()


def test_remove_unknown_id_exits_65(project_dir):
    result = runner.invoke(cli, ["-C", str(project_dir), "remove", "999", "--yes"])
    assert result.exit_code == 65


def test_remove_disk_failure_is_surfaced(project_dir, monkeypatch):
    """A failed artefact removal does not claim a clean removal: the rows are
    still gone (DB-first ordering), a warning goes to stderr, exit EX_PARTIAL."""
    thesis_id, _ = _seed(project_dir, analysed=True)

    def _boom(self, tid):
        raise PermissionError("file is locked")

    monkeypatch.setattr("tta.core.artefacts.ArtefactStore.purge", _boom)
    result = invoke("-C", project_dir, "remove", thesis_id, "--yes", expect_exit=1)
    assert _rows(project_dir) == []
    assert "could not be deleted" in " ".join(result.stderr.split())


def test_remove_then_re_add_is_a_fresh_thesis(project_dir):
    """The same PDF adds again cleanly once the row is forgotten (#63)."""
    thesis_id, pdf = _seed(project_dir, analysed=True)
    invoke("-C", project_dir, "remove", thesis_id, "--yes")
    invoke("-C", project_dir, "run", pdf, "--dry-run")
    rows = _rows(project_dir)
    assert len(rows) == 1
    assert rows[0]["ok"] == 0 and rows[0]["excluded"] is False  # no inherited history


# -- tta export --profiling (#47) --------------------------------------------


def _seed_with_durations(project_dir):
    from tta.core import db
    from tta.core.db.repository import Repository

    pdf = project_dir / "timed.pdf"
    pdf.write_bytes(b"%PDF-" + bytes(200))
    conn = db.connect(project_dir / "tta.sqlite")
    repo = Repository(conn)
    thesis = repo.add_thesis(pdf)
    with repo.transaction():
        repo.record_run(thesis.id, "mod_tokenize", "1.0.0", "ok", duration_ms=4000)
        repo.record_run(thesis.id, "mod_tokenize", "1.1.0", "ok", duration_ms=3000)
        repo.record_run(thesis.id, "mod_readability", "1.0.0", "error", duration_ms=12)
    conn.close()
    return thesis.id


def test_export_profiling_writes_a_csv_to_the_default_path(project_dir):
    _seed_with_durations(project_dir)
    result = invoke("-C", project_dir, "export", "--profiling")
    assert "3 module runs across 2 modules" in result.stdout

    csvs = list((project_dir / "exports").glob("*profiling*.csv"))
    assert len(csvs) == 1
    lines = csvs[0].read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("thesis_id,pdf_sha256,pdf_size_bytes,module_name")
    assert len(lines) == 4  # header + 3 runs
    assert "mod_readability" in csvs[0].read_text(encoding="utf-8")


def test_export_profiling_current_only_trims(project_dir):
    import csv

    _seed_with_durations(project_dir)
    out = project_dir / "prof.csv"
    result = invoke("-C", project_dir, "export", out, "--profiling", "--current-only")
    assert "2 module runs" in result.stdout  # latest mod_tokenize + the mod_readability run
    with open(out, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    versions = {r["module_name"]: r["module_version"] for r in rows}
    assert versions == {"mod_tokenize": "1.1.0", "mod_readability": "1.0.0"}
    assert rows[0]["ms_per_byte"]  # the derived rate is populated


def test_export_profiling_leaves_the_cohort_export_alone(project_dir):
    """The flag chooses which output is produced; the default is unchanged."""
    _seed_with_durations(project_dir)
    result = invoke("-C", project_dir, "export", project_dir / "cohort.sqlite")
    assert "exported 1 theses" in result.stdout
    assert (project_dir / "cohort.sqlite").exists()


def test_export_profiling_refuses_to_overwrite_exits_65(project_dir):
    _seed_with_durations(project_dir)
    out = project_dir / "prof.csv"
    out.write_bytes(b"do not clobber")
    result = runner.invoke(
        cli, ["-C", str(project_dir), "export", str(out), "--profiling"]
    )
    assert result.exit_code == 65
    assert out.read_bytes() == b"do not clobber"
