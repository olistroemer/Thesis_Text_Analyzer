"""Privacy registry coverage gate (ADR-0009): this test IS the CI check.

A schema column, registered module, or artefact kind missing from
`core/privacy_metadata.py` fails here - statement and schema cannot drift.
"""

import json

from tta.core import artefact_kinds, privacy_metadata
from tta.core.export import export_database
from tta.core.modules.registry import default_registry


def schema_columns(conn):
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return {
        (table, r["name"])
        for table in tables
        for r in conn.execute(f"PRAGMA table_info({table})")
    }


def test_every_schema_column_has_a_registry_entry(project):
    in_schema = schema_columns(project.conn)
    in_registry = {(f.table, f.column) for f in privacy_metadata.FIELDS}
    assert in_schema - in_registry == set(), "schema columns missing from privacy registry"
    assert in_registry - in_schema == set(), "stale privacy registry entries"


def test_every_module_has_a_registry_entry():
    registered = set(default_registry().names())
    declared = {m.name for m in privacy_metadata.MODULES}
    assert registered == declared


def test_every_artefact_kind_has_a_registry_entry():
    declared = {k.kind for k in privacy_metadata.ARTEFACT_KINDS}
    assert declared == set(artefact_kinds.ALL_KINDS)
    # content/identifying kinds must never be marked exportable in MVP
    for k in privacy_metadata.ARTEFACT_KINDS:
        assert k.exported is False


def test_registry_exported_flags_match_export_reality(project, tmp_path):
    """Cross-check (ADR-0009): a column marked exported=False must not
    exist in an actual export file; one marked True must."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-x")
    project.repo.add_thesis(pdf)
    stats = export_database(project.conn, tmp_path / "export.sqlite")

    import sqlite3

    conn = sqlite3.connect(stats.path)
    conn.row_factory = sqlite3.Row
    exported_cols = schema_columns(conn)
    for f in privacy_metadata.FIELDS:
        if f.table in ("schema_version", "artefact_files"):
            continue  # whole table intentionally absent from exports
        assert ((f.table, f.column) in exported_cols) == f.exported, (
            f"{f.table}.{f.column}: registry says exported={f.exported}, export file disagrees"
        )


def test_markdown_report_renders_all_sections():
    report = privacy_metadata.render_report_md(rights_stub="RIGHTS", controller_stub="CONTACT")
    for heading in (
        "## 1. What we process",
        "## 2. Module-level processing",
        "## 3. Cached files",
        "## 4. Storage and retention",
        "## 5. What leaves your machine",
        "## 6. Your rights under GDPR",
        "## 7. Controller contact",
    ):
        assert heading in report
    assert "RIGHTS" in report and "CONTACT" in report
    assert "`theses.pdf_path`" in report


def test_json_report_is_machine_readable():
    payload = json.loads(privacy_metadata.render_report_json())
    assert {f["table"] for f in payload["fields"]} == {
        "schema_version", "sources", "theses", "module_runs", "metric_values", "artefact_files"
    }
    assert len(payload["modules"]) == 10
    assert len(payload["artefact_kinds"]) == 4
