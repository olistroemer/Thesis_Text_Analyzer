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
