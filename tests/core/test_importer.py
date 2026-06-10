"""Importer tests (SDD §8.3.2, US-RES-IMPORT, US-RES-LOCAL-RERUN)."""

import pytest

from pds.core.export import export_database
from pds.core.importer import ImportError_, ImportStats, import_export
from pds.core.modules.registry import ModuleRegistry
from pds.core.runner import Runner
from tests.core.test_export import populate
from tests.core.test_runner import FakeExtract


@pytest.fixture
def export_file(project, tmp_path):
    populate(project, tmp_path)
    return export_database(project.conn, tmp_path / "fhw.sqlite").path


@pytest.fixture
def researcher(tmp_path_factory):
    """A second, independent project standing in for the researcher's DB."""
    from types import SimpleNamespace

    from pds.core import db
    from pds.core.artefacts import ArtefactStore
    from pds.core.db import migrator
    from pds.core.db.repository import Repository

    project_dir = tmp_path_factory.mktemp("researcher")
    migrator.migrate(project_dir / "pds.sqlite")
    conn = db.connect(project_dir / "pds.sqlite")
    repo = Repository(conn)
    repo.ensure_local_source()
    yield SimpleNamespace(dir=project_dir, conn=conn, repo=repo, store=ArtefactStore(project_dir))
    conn.close()


def test_import_creates_imported_source_with_remapped_ids(researcher, export_file, tmp_path):
    # pre-existing local thesis occupies id 1, forcing a remap
    local_pdf = tmp_path / "own.pdf"
    local_pdf.write_bytes(b"%PDF-own")
    local = researcher.repo.add_thesis(local_pdf)

    stats = import_export(researcher.conn, export_file, name="FH Wedel CS 2026")
    assert stats == ImportStats(
        source_id=stats.source_id, name="FH Wedel CS 2026", theses=1, runs=2, metrics=2
    )

    source = researcher.conn.execute(
        "SELECT kind FROM sources WHERE id = ?", (stats.source_id,)
    ).fetchone()
    assert source["kind"] == "imported"

    imported = researcher.conn.execute(
        "SELECT id, source_id FROM theses WHERE source_id = ?", (stats.source_id,)
    ).fetchall()
    assert len(imported) == 1
    assert imported[0]["id"] != local.id  # remapped past the existing local id

    # metric values follow their remapped runs (current view sees them)
    row = researcher.conn.execute(
        "SELECT value_num FROM v_current_metrics WHERE source_id = ? AND metric_name = 'm'",
        (stats.source_id,),
    ).fetchone()
    assert row["value_num"] == 2.0


def test_imported_theses_are_not_planned(researcher, export_file):
    import_export(researcher.conn, export_file, name="FH Wedel CS 2026")
    runner = Runner(researcher.repo, researcher.store, ModuleRegistry([FakeExtract()]))
    assert runner.plan().theses == []  # kind='local' filter (US-RES-LOCAL-RERUN)


def test_duplicate_source_name_rejected(researcher, export_file):
    import_export(researcher.conn, export_file, name="FH Wedel CS 2026")
    with pytest.raises(ImportError_, match="already exists"):
        import_export(researcher.conn, export_file, name="FH Wedel CS 2026")
    # second import under a different name is fine (re-submission case)
    stats = import_export(researcher.conn, export_file, name="FH Wedel CS 2026 (v2)")
    assert stats.theses == 1


def test_rejects_non_export_file(researcher, tmp_path):
    bogus = tmp_path / "bogus.sqlite"
    bogus.write_bytes(b"")
    with pytest.raises(ImportError_, match="no export_info"):
        import_export(researcher.conn, bogus, name="X")
    with pytest.raises(ImportError_, match="not found"):
        import_export(researcher.conn, tmp_path / "missing.sqlite", name="X")
