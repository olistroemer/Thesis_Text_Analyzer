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


def _seed_thesis(project_dir, *, analysed: bool):
    """Add a thesis directly (fast), optionally with a cached run + artefact,
    so exclude/include can be exercised without a real multiprocessing run."""
    from tta.core import db
    from tta.core.artefacts import ArtefactStore
    from tta.core.db.repository import Repository

    pdf = project_dir / "seed.pdf"
    pdf.write_bytes(b"%PDF-seed content")
    conn = db.connect(project_dir / "tta.sqlite")
    repo = Repository(conn)
    thesis = repo.add_thesis(pdf)
    if analysed:
        store = ArtefactStore(project_dir)
        with repo.transaction():
            run_id = repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
            src = project_dir / "raw.txt"
            src.write_text("secret extracted text", encoding="utf-8")
            rel = store.store(thesis.id, run_id, "raw_text", src)
            repo.record_artefact(thesis.id, "raw_text", rel, run_id)
    conn.close()
    return thesis.id


def _state(project_dir, thesis_id):
    from tta.core import db

    conn = db.connect(project_dir / "tta.sqlite")
    excluded = conn.execute(
        "SELECT excluded FROM theses WHERE id = ?", (thesis_id,)
    ).fetchone()["excluded"]
    runs = conn.execute(
        "SELECT COUNT(*) AS n FROM module_runs WHERE thesis_id = ?", (thesis_id,)
    ).fetchone()["n"]
    conn.close()
    return excluded, runs


def test_version_json_lists_all_modules():
    result = invoke("version", "--format", "json")
    payload = json.loads(result.stdout)
    assert payload["app"] == "0.1.0"
    assert len(payload["modules"]) == 13  # ADR-0011 rev. 4 (#18)
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
    assert len(payload) == 13  # ADR-0011 rev. 4 (#18)
    result = invoke("module", "show", "mod_vocabulary")
    assert "hapax_token_ratio" in result.stdout
    invoke("module", "show", "mod_nope", expect_exit=64)


def test_privacy_report_renders(project_dir):
    md = invoke("privacy", "report").stdout
    assert "## 5. What leaves your machine" in md
    assert "Your rights under GDPR" in md
    payload = json.loads(invoke("privacy", "report", "--format", "json").stdout)
    assert len(payload["modules"]) == 13  # ADR-0011 rev. 4 (#18)


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


def test_exclude_yes_scrubs_analysis(project_dir):
    """`tta exclude <id> --yes` sets excluded=1 and scrubs the cached analysis
    (rows + on-disk artefacts) without prompting (ADR-0003, #11)."""
    thesis_id = _seed_thesis(project_dir, analysed=True)
    tree = project_dir / "artefacts" / str(thesis_id)
    assert tree.exists()

    result = invoke("-C", project_dir, "exclude", thesis_id, "--yes")
    assert "scrubbed" in result.stdout
    excluded, runs = _state(project_dir, thesis_id)
    assert excluded == 1 and runs == 0
    assert not tree.exists()  # PII artefacts gone from disk
    # list reflects the excluded flag
    rows = json.loads(invoke("-C", project_dir, "list", "--format", "json").stdout)
    assert rows[0]["excluded"] is True


def test_exclude_confirm_yes_and_no(project_dir):
    """Without --yes the scrub is gated by a confirmation prompt: 'y' proceeds,
    'n' aborts with no changes (ADR-0003, #11)."""
    thesis_id = _seed_thesis(project_dir, analysed=True)

    # decline: nothing changes, exits 0
    declined = runner.invoke(
        cli, ["-C", str(project_dir), "exclude", str(thesis_id)], input="n\n"
    )
    assert declined.exit_code == 0, declined.output
    assert "aborted" in declined.output
    excluded, runs = _state(project_dir, thesis_id)
    assert excluded == 0 and runs == 1  # untouched

    # confirm: scrub proceeds
    confirmed = runner.invoke(
        cli, ["-C", str(project_dir), "exclude", str(thesis_id)], input="y\n"
    )
    assert confirmed.exit_code == 0, confirmed.output
    excluded, runs = _state(project_dir, thesis_id)
    assert excluded == 1 and runs == 0


def test_exclude_before_run_needs_no_confirmation(project_dir):
    """A never-analysed thesis has nothing to scrub, so exclude just sets the
    flag with no prompt (#11)."""
    thesis_id = _seed_thesis(project_dir, analysed=False)
    result = invoke("-C", project_dir, "exclude", thesis_id)  # no input needed
    assert "excluded thesis" in result.stdout and "scrubbed" not in result.stdout
    excluded, runs = _state(project_dir, thesis_id)
    assert excluded == 1 and runs == 0


def test_exclude_scrub_disk_failure_is_surfaced(project_dir, monkeypatch):
    """If the on-disk artefact removal fails, exclude does not claim a clean
    scrub (#11 review): the DB analysis is still removed (excluded=1, rows gone,
    DB-first ordering), but a warning is emitted and it exits EX_PARTIAL."""
    thesis_id = _seed_thesis(project_dir, analysed=True)

    def _boom(self, tid):
        raise PermissionError("file is locked")

    monkeypatch.setattr("tta.core.artefacts.ArtefactStore.purge", _boom)

    result = invoke("-C", project_dir, "exclude", thesis_id, "--yes", expect_exit=1)
    # DB scrub still happened despite the disk failure
    excluded, runs = _state(project_dir, thesis_id)
    assert excluded == 1 and runs == 0
    # failure surfaced on stderr (rich word-wraps; normalise whitespace),
    # not a false "scrubbed" on stdout
    assert "could not be deleted" in " ".join(result.stderr.split())
    assert "scrubbed" not in result.stdout


def test_include_clears_the_flag(project_dir):
    thesis_id = _seed_thesis(project_dir, analysed=False)
    invoke("-C", project_dir, "exclude", thesis_id)
    assert _state(project_dir, thesis_id)[0] == 1
    invoke("-C", project_dir, "include", thesis_id)
    assert _state(project_dir, thesis_id)[0] == 0


def test_exclude_unknown_id_exits_65(project_dir):
    result = runner.invoke(cli, ["-C", str(project_dir), "exclude", "999", "--yes"])
    assert result.exit_code == 65
    result = runner.invoke(cli, ["-C", str(project_dir), "include", "999"])
    assert result.exit_code == 65


@pytest.mark.slow
def test_full_contribute_loop(project_dir, english_pdf, tmp_path):
    """The researcher's five-step loop, headless: add+run -> list -> export -> import."""
    # dry-run first: all catalogue modules planned (no --type: type is detected, #9)
    result = invoke("-C", project_dir, "run", english_pdf, "--dry-run")
    assert "13 (thesis x module) pairs planned" in result.stdout

    # run for real
    result = invoke("-C", project_dir, "run", english_pdf, "--format", "json")
    summary = json.loads(result.stdout)
    assert summary["error"] == 0
    assert summary["ok"] == 13  # ADR-0011 rev. 4 (#18)
    assert "[thesis 1]" in result.stderr  # progress went to stderr, not stdout

    # list shows the analysed thesis; type is the detected metric (unspecified
    # for this english prose fixture, which names no degree)
    rows = json.loads(invoke("-C", project_dir, "list", "--format", "json").stdout)
    assert rows[0]["ok"] == 13 and rows[0]["missing"] == 0
    assert rows[0]["type"] == "unspecified"

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


# -- report (#51) -----------------------------------------------------------


def test_report_writes_one_self_contained_html_file(project_dir):
    _seed_thesis(project_dir, analysed=True)
    result = invoke("-C", project_dir, "report")
    written = sorted((project_dir / "reports").glob("report-*.html"))
    assert len(written) == 1
    assert written[0].name in result.output.replace("\n", "")
    document = written[0].read_text("utf-8")
    assert document.startswith("<!DOCTYPE html>")
    assert document.endswith("</html>\n")
    # QA-PRIV: an offline app must not write a file that phones home
    assert "http://" not in document and "https://" not in document
    assert "<script" not in document
    # ...and no identifying value reaches it (Sec. 9.8.3)
    assert "seed.pdf" not in document


def test_report_out_overrides_the_default_path(project_dir, tmp_path):
    _seed_thesis(project_dir, analysed=True)
    target = tmp_path / "elsewhere" / "cohort.html"
    invoke("-C", project_dir, "report", "--out", target)
    assert "Cohort report" in target.read_text("utf-8")
    assert not (project_dir / "reports").exists()


def test_report_without_a_project_exits_65(tmp_path):
    invoke("-C", tmp_path / "nope", "report", expect_exit=65)


# -- run --open-report (#70) ------------------------------------------------


def _fake_execute(summary):
    return lambda self, plan: summary


def test_run_open_report_writes_and_opens_the_report(project_dir, english_pdf, monkeypatch):
    """--open-report is the explicit ask, so it may launch a browser; without
    the flag a CLI must never do so (Sec. 9.8.3, #70)."""
    import webbrowser

    from tta.core.runner import RunSummary, Runner

    monkeypatch.setattr(
        Runner, "execute", _fake_execute(RunSummary(theses_total=1, theses_completed=1, ok=1))
    )
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", opened.append)

    invoke("-C", project_dir, "run", english_pdf, "--open-report")
    written = sorted((project_dir / "reports").glob("report-*.html"))
    assert len(written) == 1
    assert opened == [written[0].as_uri()]

    opened.clear()
    invoke("-C", project_dir, "run")  # flag off by default
    assert opened == []


def test_run_open_report_is_suppressed_for_a_cancelled_run(project_dir, english_pdf, monkeypatch):
    import webbrowser

    from tta.core.runner import RunSummary, Runner

    monkeypatch.setattr(
        Runner,
        "execute",
        _fake_execute(RunSummary(theses_total=2, theses_completed=1, ok=1, cancelled=True)),
    )
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", opened.append)

    invoke("-C", project_dir, "run", english_pdf, "--open-report", expect_exit=1)
    assert opened == []
    assert not (project_dir / "reports").exists()
