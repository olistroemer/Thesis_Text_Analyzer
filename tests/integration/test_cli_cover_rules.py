"""`tta run --cover-rules` (ADR-0023, ADR-0003 rev. 2026-11-17, #81, #82).

The researcher-only cover-page ruleset: runs with and without it are told
apart by the module version, so the planner re-runs the two title-page modules
whenever the choice changes and the two kinds of result are never mixed.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from tta.cli.main import cli
from tta.core.cover_rules import load_cover_ruleset
from tta.core.modules.registry import default_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
ETH_FILE = REPO_ROOT / "research" / "cover_rules" / "eth_research_collection.toml"
TITLE_PAGE_MODULES = ("mod_classify_thesis_type", "mod_determine_publication_year")

runner = CliRunner()


def invoke(*args, expect_exit=0):
    result = runner.invoke(cli, [str(a) for a in args], catch_exceptions=False)
    assert result.exit_code == expect_exit, result.output + result.stderr
    return result


@pytest.fixture
def project_dir(tmp_path):
    invoke("-C", tmp_path / "proj", "db", "init")
    return tmp_path / "proj"


def _seed_analysed(project_dir, registry):
    """One thesis with an ok run of every module at ``registry``'s versions and
    its raw_text/pdf_metadata artefacts on disk - no real pipeline needed."""
    from tta.core import db
    from tta.core.artefacts import ArtefactStore
    from tta.core.db.repository import Repository

    pdf = project_dir / "seed.pdf"
    pdf.write_bytes(b"%PDF-seed content")
    conn = db.connect(project_dir / "tta.sqlite")
    repo = Repository(conn)
    thesis = repo.add_thesis(pdf)
    store = ArtefactStore(project_dir)
    with repo.transaction():
        for module in registry.in_topological_order():
            run_id = repo.record_run(thesis.id, module.spec.name, module.spec.version, "ok")
            for kind in module.spec.produces_artefacts:
                src = project_dir / f"{kind}.tmp"
                src.write_text("{}", encoding="utf-8")
                repo.record_artefact(thesis.id, kind, store.store(thesis.id, run_id, kind, src), run_id)
    conn.close()


def _planned(result):
    return sorted(line.split(": ", 1)[1] for line in result.stdout.splitlines() if ": mod_" in line)


def test_default_run_after_a_default_run_plans_nothing(project_dir):
    _seed_analysed(project_dir, default_registry())
    result = invoke("-C", project_dir, "run", "--dry-run")
    assert "0 (thesis x module) pairs planned" in result.stdout


def test_switching_the_ruleset_on_replans_only_the_title_page_modules(project_dir):
    _seed_analysed(project_dir, default_registry())
    result = invoke("-C", project_dir, "run", "--cover-rules", ETH_FILE, "--dry-run")
    assert _planned(result) == [f"{name} (stale)" for name in TITLE_PAGE_MODULES]
    assert "cover rules: eth-research-collection" in result.stderr or (
        "Deckblattregeln: eth-research-collection" in result.stderr
    )


def test_switching_the_ruleset_off_replans_them_again(project_dir):
    _seed_analysed(project_dir, default_registry(load_cover_ruleset(ETH_FILE)))
    with_rules = invoke("-C", project_dir, "run", "--cover-rules", ETH_FILE, "--dry-run")
    assert "0 (thesis x module) pairs planned" in with_rules.stdout
    without = invoke("-C", project_dir, "run", "--dry-run")
    assert _planned(without) == [f"{name} (stale)" for name in TITLE_PAGE_MODULES]


def test_an_invalid_ruleset_is_a_usage_error_64(project_dir, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('id = "x"\nversion = "1"\n', encoding="utf-8")
    result = runner.invoke(cli, ["-C", str(project_dir), "run", "--cover-rules", str(bad), "--dry-run"])
    assert result.exit_code == 64  # misuse (ADR-0003 exit codes)
    assert "--cover-rules" in result.output + result.stderr


@pytest.mark.slow
def test_a_real_run_records_the_ruleset(project_dir, english_pdf):
    from tta.core import db

    invoke("-C", project_dir, "run", english_pdf, "--cover-rules", ETH_FILE, "--format", "json")
    conn = db.connect(project_dir / "tta.sqlite")
    rows = conn.execute(
        "SELECT module_name, module_version, diagnostics FROM module_runs WHERE module_name IN (?, ?)",
        TITLE_PAGE_MODULES,
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    for row in rows:
        assert "+covers.eth-research-collection." in row["module_version"]
        diagnostics = json.loads(row["diagnostics"])
        assert diagnostics["cover_rules"]["id"] == "eth-research-collection"
        assert diagnostics["cover_pages"] == []  # the fixture has no cover page
