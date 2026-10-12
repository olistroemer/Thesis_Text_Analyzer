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
    report = privacy_metadata.render_report_md(rights_stub="RIGHTS", contact_stub="CONTACT")
    for heading in (
        "## In brief",
        "## 1. What we process",
        "## 2. Module-level processing",
        "## 3. Cached files",
        "## 4. Storage and retention",
        "## 5. What leaves your machine",
        "## 6. Responsibility and your rights under GDPR",
        "## 7. Publisher and contact",
    ):
        assert heading in report
    assert report.index("## In brief") < report.index("## 1. What we process")
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

STUBS = (privacy_metadata.RIGHTS_STUB, privacy_metadata.CONTACT_STUB)
#: The only address a stub may carry: the publisher's. Never a person's -
#: the data protection officer is reached via the privacy-policy page
#: (DPO_CONTACT_PAGE) - and no supervisory authority's: naming one would
#: imply FH Wedel processes the data.
ALLOWED_EMAILS = {"info@fh-wedel.de"}
DPO_CONTACT_PAGE = "https://www.fh-wedel.de/datenschutzrichtlinien/"
#: Words that would make FH Wedel the controller (ADR-0009 role split).
CONTROLLER_WORDS = {"de": "Verantwortlicher", "en": "controller"}


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
def test_stubs_name_publisher_and_contact_but_no_controller(locale):
    """ADR-0009 role split: FH Wedel publishes the software and offers a
    contact; it is not the controller of the local processing, so the stubs
    neither call it that nor list Art. 15-21 as rights against it."""
    rights = privacy_metadata.load_legal_stub(privacy_metadata.RIGHTS_STUB, locale)
    contact = privacy_metadata.load_legal_stub(privacy_metadata.CONTACT_STUB, locale)
    assert "<!--" not in rights + contact  # maintainer comments are stripped
    assert CONTROLLER_WORDS[locale] not in rights + contact
    for article in ("Art. 15", "Art. 16", "Art. 17", "Art. 18", "Art. 20", "Art. 21"):
        assert article not in rights + contact
    assert "Art. 77" in rights  # the complaint right, stated generically
    assert "ULD" not in rights and "datenschutzzentrum" not in rights
    assert "Fachhochschule Wedel gGmbH" in contact
    assert DPO_CONTACT_PAGE in contact
    emails = set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", rights + contact))
    assert emails and emails <= ALLOWED_EMAILS


@pytest.mark.parametrize("locale", i18n.SUPPORTED_LOCALES)
def test_section_6_makes_no_promise_about_using_the_hash(locale):
    """ADR-0009 (owner decision 2026-10-12): a promise not to identify
    authors through the hash would imply that it were possible. The stub
    states the hash's purpose and the residual, nothing about intent."""
    rights = privacy_metadata.load_legal_stub(privacy_metadata.RIGHTS_STUB, locale)
    for phrase in ("Verfasser", "identify authors", "verpflichtet", "obliged"):
        assert phrase not in rights


@pytest.mark.parametrize("locale", i18n.SUPPORTED_LOCALES)
def test_the_fingerprint_the_stub_names_is_the_exported_content_hash(locale):
    """Section 6 explains the export's only per-thesis key; it must name the
    column the registry actually exports as a content hash."""
    rights = privacy_metadata.load_legal_stub(privacy_metadata.RIGHTS_STUB, locale)
    hashes = [
        f"`{f.table}.{f.column}`"
        for f in privacy_metadata.FIELDS
        if f.exported and f.category is privacy_metadata.Category.CONTENT_HASH
    ]
    assert hashes == ["`theses.pdf_sha256`"]
    assert hashes[0] in rights


# -- the plain-language summary (ADR-0009 rev. 2026-10-12) --------------------


def _exported_bullets(report):
    section_5 = report.split("## 5. What leaves your machine", 1)[1].split("\n## ", 1)[0]
    return [line for line in section_5.splitlines() if line.startswith("- `")]


def test_the_summary_follows_the_registry():
    report = privacy_metadata.render_report_md()
    summary = report.split("## In brief", 1)[1].split("## 1.", 1)[0]
    assert privacy_metadata.export_is_free_of_identifying_values()
    assert "no personal names, no file names or paths" in summary
    count = len(_exported_bullets(report))
    assert f"({count} values, listed in section 5)" in summary
    assert "`theses.pdf_sha256`" in summary
    assert "recognise duplicates" in summary
    assert "sends nothing anywhere by itself" in summary


def test_the_summary_drops_its_claim_if_an_identifying_value_were_exported(monkeypatch):
    """The strongest sentence is conditional, not hard-coded: flip one
    identifying field to exported and it must disappear."""
    fields = tuple(
        privacy_metadata.Field(f.table, f.column, f.category, f.purpose, True)
        if (f.table, f.column) == ("theses", "pdf_filename")
        else f
        for f in privacy_metadata.FIELDS
    )
    monkeypatch.setattr(privacy_metadata, "FIELDS", fields)
    assert not privacy_metadata.export_is_free_of_identifying_values()
    summary = "\n".join(privacy_metadata.summary_lines())
    assert "no personal names" not in summary
    assert "values listed in section 5" in summary


def test_the_summary_drops_its_claim_if_an_artefact_were_exported(monkeypatch):
    kinds = tuple(
        privacy_metadata.ArtefactKindEntry(k.kind, k.category, k.description, True)
        if k.kind == "raw_text"
        else k
        for k in privacy_metadata.ARTEFACT_KINDS
    )
    monkeypatch.setattr(privacy_metadata, "ARTEFACT_KINDS", kinds)
    assert not privacy_metadata.export_is_free_of_identifying_values()


def test_the_hash_purpose_says_deduplication_only():
    (field,) = [f for f in privacy_metadata.FIELDS if f.column == "pdf_sha256"]
    assert "only to recognise duplicate copies" in field.purpose
    assert "never to identify authors" in field.purpose


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
        heading_6 = "## " + i18n._("6. Responsibility and your rights under GDPR")
        heading_7 = "## " + i18n._("7. Publisher and contact")
    finally:
        i18n.install("en")
    assert heading_6 in statement and heading_7 in statement
    assert statement.index(heading_6) < statement.index(heading_7)
    assert "Fachhochschule Wedel gGmbH" in statement.split(heading_7, 1)[1]
    assert "Art. 77" in statement.split(heading_6, 1)[1]
