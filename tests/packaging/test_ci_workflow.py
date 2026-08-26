"""The CI workflow's invariant gates (#3).

Issue #3 asked for a workflow that is "red on any boundary/test/coverage
failure". The boundary and test parts landed and CI is green on main; the
coverage gate was never wired up, and the display-gated GUI tests
self-skipped, which reads as a pass while covering nothing.

These tests assert the workflow still carries each gate, and - for coverage
- that the threshold in CI is the one SDD 10's QA-TEST specifies rather than
a number someone picked.
"""

import re

from tests.packaging.conftest import REPO_ROOT

SDD_PATH = REPO_ROOT / "docs" / "SDD.md"


def build_job(workflow_source):
    return workflow_source.split("build-linux:", 1)[0]


# ------------------------------------------------------------- triggers


def test_workflow_runs_on_push_and_pull_request(workflow_source):
    header = workflow_source.split("jobs:", 1)[0]
    assert re.search(r"^\s*push:", header, re.M)
    assert re.search(r"^\s*pull_request:", header, re.M)


# ------------------------------------------------------- the coverage gate


def sdd_coverage_targets():
    """(line, branch) from QA-TEST itself, so CI cannot drift from the SDD."""
    sdd = SDD_PATH.read_text(encoding="utf-8")
    documented = re.search(
        r"Coverage target:\s*(\d+)\s*%\s*line\s*/\s*(\d+)\s*%\s*branch", sdd
    )
    assert documented, "SDD QA-TEST no longer states a coverage target"
    return int(documented.group(1)), int(documented.group(2))


def test_coverage_gate_exists_and_is_scoped_to_core(workflow_source):
    """QA-TEST scopes the target to core/, not to the whole package."""
    test_job = build_job(workflow_source)
    assert "--cov=tta.core" in test_job
    assert "--cov-branch" in test_job
    assert "TTA_COV_LINE" in test_job and "TTA_COV_BRANCH" in test_job


def test_coverage_thresholds_are_the_ones_the_sdd_specifies(workflow_source):
    """SDD 10 QA-TEST states TWO targets: 85 % line / 70 % branch on core/.

    They are checked separately in CI on purpose. --cov-fail-under gates
    coverage.py's single combined line+branch rate, which is neither number:
    it can fail a suite that meets both stated targets and pass one that
    misses the branch target outright.
    """
    test_job = build_job(workflow_source)
    line_target, branch_target = sdd_coverage_targets()

    line = re.search(r'TTA_COV_LINE:\s*"(\d+)"', test_job)
    branch = re.search(r'TTA_COV_BRANCH:\s*"(\d+)"', test_job)
    assert line and branch, "the workflow declares no line/branch thresholds"
    assert int(line.group(1)) >= line_target, (
        "CI gates line coverage at %s %%, below QA-TEST's %d %%"
        % (line.group(1), line_target)
    )
    assert int(branch.group(1)) >= branch_target, (
        "CI gates branch coverage at %s %%, below QA-TEST's %d %%"
        % (branch.group(1), branch_target)
    )


def test_the_combined_cov_fail_under_shortcut_is_not_used(workflow_source):
    """Guards the reasoning above against a well-meaning simplification.

    Comments may name the flag - the step's own comment explains why it is
    not used - so only executable lines are inspected.
    """
    code = [
        line for line in workflow_source.splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert "--cov-fail-under" not in "\n".join(code)


def test_pytest_cov_is_installed_for_the_test_job(workflow_source):
    """Otherwise the --cov flags in CI are an unrecognised-argument error.

    Installed by the workflow rather than declared in the dev extra: how CI
    measures the suite is not a property of the package, and pyproject's
    extras are a heavily shared surface.
    """
    test_job = build_job(workflow_source)
    assert "pytest-cov" in test_job
    assert "pip install" in test_job


def test_coverage_artefacts_are_written_outside_the_checkout(workflow_source):
    """A coverage run must not leave .coverage in the working tree."""
    test_job = build_job(workflow_source)
    assert "COVERAGE_FILE" in test_job
    assert "runner.temp" in test_job
    assert "--cov-report=json:\"$RUNNER_TEMP" in test_job


# ---------------------------------------------------------- the test suite


def test_slow_tests_are_not_deselected(workflow_source):
    """#3 explicitly wants the slow-marked tests to run in CI."""
    assert "not slow" not in workflow_source
    assert "-m 'not slow'" not in workflow_source


def test_gui_tests_actually_run_under_xvfb(workflow_source):
    """They self-skip headless, so without this they never run at all."""
    test_job = build_job(workflow_source)
    assert "xvfb-run" in test_job
    assert "tests/ui" in test_job


def test_xvfb_and_tk_are_installed_for_the_test_job(workflow_source):
    test_job = build_job(workflow_source)
    assert "xvfb" in test_job
    assert "python3-tk" in test_job


# ------------------------------------------------- the boundary invariants


def test_both_boundary_directions_are_gated(workflow_source):
    """SDD 5.2 / ADR-0002 - the reason issue #3 exists."""
    assert re.search(r"grep -rn 'tta\\\.ui' tta/core tta/cli", workflow_source)
    assert re.search(r"grep -rn 'tta\\\.cli' tta/core tta/ui", workflow_source)


def test_the_retired_agpl_gate_has_not_come_back(workflow_source):
    """ADR-0017 removed it; #3 lists it as out of scope."""
    assert "import fitz" not in workflow_source
    assert "import pymupdf" not in workflow_source


def test_ascii_source_invariant_is_gated(workflow_source):
    assert "ADR-0018" in workflow_source
    assert "git ls-files" in workflow_source
