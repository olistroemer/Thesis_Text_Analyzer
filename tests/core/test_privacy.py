"""Privacy registry coverage gate (ADR-0009): this test IS the CI check.

A schema column, registered module, or artefact kind missing from
`core/privacy_metadata.py` fails here - statement and schema cannot drift.
"""

import json
import re

import pytest

from tta.core import artefact_kinds, i18n, privacy_metadata
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
    assert len(payload["modules"]) == 13  # +mod_extract_filesystem_metadata (#18)
    assert len(payload["artefact_kinds"]) == 4


# -- legal stubs, sections 6-7 (ADR-0009 "Legal stubs", #6) -------------------

STUBS = (privacy_metadata.RIGHTS_STUB, privacy_metadata.CONTROLLER_STUB)
#: The only addresses a stub may carry: the controller's, its data protection
#: officer's and the supervisory authority's. Never a project member's.
ALLOWED_EMAILS = {"info@fh-wedel.de", "ckrug@fh-wedel.de", "mail@datenschutzzentrum.de"}


@pytest.mark.parametrize("locale", i18n.SUPPORTED_LOCALES)
@pytest.mark.parametrize("filename", STUBS)
def test_every_supported_locale_has_its_own_stub(locale, filename):
    assert (privacy_metadata.legal_stub_root() / locale / filename).is_file()


@pytest.mark.parametrize("locale", i18n.SUPPORTED_LOCALES)
@pytest.mark.parametrize("filename", STUBS)
def test_no_stub_is_still_marked_as_a_draft(locale, filename):
    raw = (privacy_metadata.legal_stub_root() / locale / filename).read_text("utf-8")
    assert "DRAFT" not in raw.upper()
    assert "to be completed" not in raw


@pytest.mark.parametrize("locale", i18n.SUPPORTED_LOCALES)
def test_stubs_name_the_controller_its_dpo_and_the_complaint_right(locale):
    rights = privacy_metadata.load_legal_stub(privacy_metadata.RIGHTS_STUB, locale)
    controller = privacy_metadata.load_legal_stub(privacy_metadata.CONTROLLER_STUB, locale)
    assert "<!--" not in rights + controller  # maintainer comments are stripped
    for article in ("Art. 15", "Art. 16", "Art. 17", "Art. 18", "Art. 20", "Art. 21", "Art. 77"):
        assert article in rights
    assert "Fachhochschule Wedel gGmbH" in controller
    assert "ckrug@fh-wedel.de" in controller
    emails = set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", rights + controller))
    assert emails and emails <= ALLOWED_EMAILS


def test_the_stub_follows_the_locale():
    german = privacy_metadata.load_legal_stub(privacy_metadata.RIGHTS_STUB, "de")
    english = privacy_metadata.load_legal_stub(privacy_metadata.RIGHTS_STUB, "en")
    assert "DSGVO" in german and "DSGVO" not in english
    assert "GDPR" in english


def test_a_locale_without_stubs_falls_back_to_german(tmp_path, monkeypatch):
    (tmp_path / "de").mkdir()
    (tmp_path / "de" / "rights_stub.md").write_text("<!-- note -->\nGERMAN", "utf-8")
    monkeypatch.setattr(privacy_metadata, "legal_stub_root", lambda: tmp_path)
    assert privacy_metadata.load_legal_stub("rights_stub.md", "en") == "GERMAN"
    assert privacy_metadata.load_legal_stub("missing.md", "en") == ""


@pytest.mark.parametrize("locale", i18n.SUPPORTED_LOCALES)
def test_the_full_statement_carries_sections_6_and_7(locale):
    """The entry point both adapters use renders the legal sections too -
    the GUI used to render sections 1-5 only."""
    i18n.install(locale)
    try:
        statement = privacy_metadata.render_statement_md()
        heading_6 = "## " + i18n._("6. Your rights under GDPR")
        heading_7 = "## " + i18n._("7. Controller contact")
    finally:
        i18n.install("en")
    assert heading_6 in statement and heading_7 in statement
    assert statement.index(heading_6) < statement.index(heading_7)
    assert "Fachhochschule Wedel gGmbH" in statement.split(heading_7, 1)[1]
    assert "Art. 77" in statement.split(heading_6, 1)[1]
