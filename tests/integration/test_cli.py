"""Integration tests: exercise the CLI end to end (ADR-0003, SDD Sec. 5.2).

Uses click's CliRunner (in-process); the full pipeline test runs the
real multiprocessing runner over a generated PDF.
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


def test_version_json_lists_all_modules():
    result = invoke("version", "--format", "json")
    payload = json.loads(result.stdout)
    assert payload["app"] == "0.1.0"
    assert len(payload["modules"]) == 10
    assert payload["modules"]["mod_vocabulary"] == "0.2.0"


def test_db_init_creates_project(project_dir):
    assert (project_dir / "tta.sqlite").exists()
    result = invoke("-C", project_dir, "db", "migrate")
    assert "up to date" in result.stdout


def test_commands_without_project_exit_65(tmp_path):
    result = runner.invoke(cli, ["-C", str(tmp_path / "nowhere"), "list"])
    assert result.exit_code == 65
    result = runner.invoke(cli, ["-C", str(tmp_path / "nowhere"), "export"])
    assert result.exit_code == 65


def test_usage_error_exits_64(project_dir):
    result = runner.invoke(cli, ["-C", str(project_dir), "run", "--module", "mod_nope", "--dry-run"])
    assert result.exit_code == 64


def test_module_list_and_show():
    payload = json.loads(invoke("module", "list", "--format", "json").stdout)
    assert [m["name"] for m in payload][0] in ("mod_extract_pymupdf", "mod_count_images", "mod_extract_pdf_metadata")
    assert len(payload) == 10
    result = invoke("module", "show", "mod_vocabulary")
    assert "hapax_token_ratio" in result.stdout
    invoke("module", "show", "mod_nope", expect_exit=64)


def test_privacy_report_renders(project_dir):
    md = invoke("privacy", "report").stdout
    assert "## 5. What leaves your machine" in md
    assert "Your rights under GDPR" in md
    payload = json.loads(invoke("privacy", "report", "--format", "json").stdout)
    assert len(payload["modules"]) == 10


def test_help_lists_topics():
    result = invoke("help")
    assert "topic" in result.stdout  # no content yet: lists or says none installed
    invoke("help", "does_not_exist", expect_exit=65)


def test_run_sigint_cancels_skip_pending_and_exits_partial(project_dir, english_pdf, monkeypatch):
    """Ctrl-C during `tta run` installs a SIGINT handler that calls
    Runner.cancel() (skip-pending); the command then exits with the partial
    code and restores the previous handler (ADR-0003 / ADR-0013, #33)."""
    import signal

    from tta.core.runner import RunSummary, Runner

    cancel_calls: list[bool] = []
    real_cancel = Runner.cancel

    def spy_cancel(self):
        cancel_calls.append(True)
        return real_cancel(self)

    def fake_execute(self, plan):
        # Stand in for a real run: fire whatever handler the CLI installed
        # for SIGINT (as a Ctrl-C would), then return as if the in-flight
        # thesis finished and the pending ones were skipped.
        handler = signal.getsignal(signal.SIGINT)
        handler(signal.SIGINT, None)
        return RunSummary(theses_total=2, theses_completed=1, ok=1, cancelled=True)

    monkeypatch.setattr(Runner, "cancel", spy_cancel)
    monkeypatch.setattr(Runner, "execute", fake_execute)

    before = signal.getsignal(signal.SIGINT)
    result = runner.invoke(
        cli, ["-C", str(project_dir), "run", str(english_pdf), "--format", "json"]
    )

    assert result.exit_code == 1, result.output  # EX_PARTIAL
    assert cancel_calls, "the SIGINT handler did not call runner.cancel()"
    payload = json.loads(result.stdout)
    assert payload["cancelled"] is True
    assert payload["theses_completed"] == 1
    # the previous SIGINT handler is restored on the way out
    assert signal.getsignal(signal.SIGINT) is before


@pytest.mark.slow
def test_full_contribute_loop(project_dir, english_pdf, tmp_path):
    """The researcher's five-step loop, headless: add+run -> list -> export -> import."""
    # dry-run first: all ten modules planned
    result = invoke("-C", project_dir, "run", english_pdf, "--type", "master", "--dry-run")
    assert "10 (thesis x module) pairs planned" in result.stdout

    # run for real
    result = invoke(
        "-C", project_dir, "run", english_pdf, "--type", "master", "--format", "json"
    )
    summary = json.loads(result.stdout)
    assert summary["error"] == 0
    assert summary["ok"] == 10
    assert "[thesis 1]" in result.stderr  # progress went to stderr, not stdout

    # list shows the analysed thesis
    rows = json.loads(invoke("-C", project_dir, "list", "--format", "json").stdout)
    assert rows[0]["ok"] == 10 and rows[0]["missing"] == 0
    assert rows[0]["type"] == "master"

    # second run: nothing to do (pause/resume property)
    result = invoke("-C", project_dir, "run", "--dry-run")
    assert "0 (thesis x module) pairs planned" in result.stdout

    # export with default path
    result = invoke("-C", project_dir, "export")
    assert "exported 1 theses" in result.stdout
    exports = list((project_dir / "exports").glob("*.sqlite"))
    assert len(exports) == 1

    # import into a fresh researcher project
    research_dir = tmp_path / "research"
    invoke("-C", research_dir, "db", "init")
    result = invoke("-C", research_dir, "import", exports[0], "--name", "FH Wedel 2026")
    assert "1 theses" in result.stdout
    # imported data is read-only context: nothing planned
    result = invoke("-C", research_dir, "run", "--dry-run")
    assert "0 (thesis x module) pairs planned" in result.stdout
    # duplicate name -> data error
    result = runner.invoke(cli, ["-C", str(research_dir), "import", str(exports[0]), "--name", "FH Wedel 2026"])
    assert result.exit_code == 65
