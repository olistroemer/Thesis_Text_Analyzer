"""`tta doctor` end to end (#42, ADR-0003).

Kept in its own module so the diagnostics command does not have to share a
file with the rest of the CLI suite.
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


def test_doctor_json_is_the_scripting_contract(project_dir):
    payload = json.loads(invoke("-C", project_dir, "doctor", "--format", "json").stdout)
    assert payload["status"] == "ok"
    assert payload["app"]["version"]
    assert payload["runtime"]["platform"]
    assert len(payload["modules"]) == 13  # ADR-0011 rev. 4
    assert payload["project"]["database"]["integrity_check"] == "ok"
    assert payload["config"]["ui_mode"] == "basic"
    assert {c["name"] for c in payload["checks"]} >= {
        "module_registry", "schema_version", "integrity_check",
        "nltk.punkt_tab[de]", "nltk.punkt_tab[en]", "langdetect", "textstat",
    }


def test_doctor_human_output_names_every_check(project_dir):
    out = invoke("-C", project_dir, "doctor").stdout
    assert "tta " in out
    assert "integrity ok" in out
    assert "[ok] integrity_check" in out  # the glyph survives rich markup
    assert "nltk.punkt_tab[en]" in out  # ... and so do bracketed check names
    assert "overall: ok" in out


def test_doctor_needs_no_project_and_creates_none(tmp_path):
    """A support command must work before `tta db init` (#42)."""
    empty = tmp_path / "empty"
    empty.mkdir()
    payload = json.loads(invoke("-C", empty, "doctor", "--format", "json").stdout)
    assert payload["status"] == "warn"
    assert list(empty.iterdir()) == []


def test_doctor_exits_1_when_a_check_fails(tmp_path):
    """`tta doctor >/dev/null || ...` must be usable in a script."""
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "tta.sqlite").write_bytes(b"not a database")
    result = invoke("-C", broken, "doctor", expect_exit=1)
    assert "failing checks:" in result.stderr


def test_doctor_reports_config_from_the_project_file(project_dir):
    (project_dir / "tta.toml").write_text(
        '[runner]\nworkers = 3\n\n[ui]\nmode = "extended"\n', encoding="utf-8"
    )
    payload = json.loads(invoke("-C", project_dir, "doctor", "--format", "json").stdout)
    assert payload["config"]["exists"] is True
    assert payload["config"]["workers"] == 3
    assert payload["config"]["ui_mode"] == "extended"
