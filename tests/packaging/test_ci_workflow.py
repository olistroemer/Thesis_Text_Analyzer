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

import pytest

from tests.packaging.conftest import REPO_ROOT, job, workflow_jobs

SDD_PATH = REPO_ROOT / "docs" / "SDD.md"


def build_job(workflow_source):
    """The test job. Named for history; it is `lint-and-test`."""
    return job(workflow_source, "lint-and-test")


def sdd_coverage_targets():
    """(line, branch) from QA-TEST itself, so CI cannot drift from the SDD."""
    sdd = SDD_PATH.read_text(encoding="utf-8")
    documented = re.search(
        r"Coverage target:\s*(\d+)\s*%\s*line\s*/\s*(\d+)\s*%\s*branch", sdd
    )
    assert documented, "SDD QA-TEST no longer states a coverage target"
    return int(documented.group(1)), int(documented.group(2))


# ------------------------------------------------------------- triggers


def test_workflow_runs_on_push_and_pull_request(workflow_source):
    header = workflow_source.split("jobs:", 1)[0]
    assert re.search(r"^\s*push:", header, re.M)
    assert re.search(r"^\s*pull_request:", header, re.M)


def test_the_workflow_parses_as_yaml(workflow_source):
    """A malformed workflow is a silently disabled workflow."""
    yaml = pytest.importorskip("yaml")
    parsed = yaml.safe_load(workflow_source)
    # PyYAML resolves the unquoted key `on` to True (YAML 1.1 booleans).
    triggers = parsed.get("on", parsed.get(True))
    assert triggers, "no triggers in the workflow"
    assert set(parsed["jobs"]) == {"lint-and-test", "build", "release"}


# ------------------------------------------------------- the coverage gate


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


# --------------------------------------------- the per-OS build matrix (#4)


def test_a_v_tag_triggers_the_workflow(workflow_source):
    """#4: "a tagged release produces working single-file binaries"."""
    header = workflow_source.split("jobs:", 1)[0]
    assert re.search(r'tags:\s*\["v\*"\]', header), (
        "no v* tag trigger, so a tagged release builds nothing"
    )


def test_every_target_os_in_adr_0014_has_a_matrix_entry(workflow_source):
    """ADR-0014: Windows, macOS (arm64 + amd64), Linux."""
    matrix = job(workflow_source, "build")
    for target in ("linux-x86_64", "windows-x86_64", "macos-arm64",
                   "macos-x86_64"):
        assert "target: %s" % target in matrix, "no %s matrix entry" % target
    # Match the os: lines exactly - a bare substring test also passed on a
    # comment that merely mentioned a retired runner, and "macos-15" is a
    # prefix of "macos-15-intel".
    runners = set(re.findall(r"^\s*os:\s*(\S+)\s*$", matrix, re.MULTILINE))
    for runner in ("ubuntu-latest", "windows-latest", "macos-15",
                   "macos-15-intel"):
        assert runner in runners, "no %s runner" % runner
    assert "macos-14" not in runners, "macos-14 is no longer accepted (ADR-0014)"


def test_windows_binaries_are_addressed_with_their_exe_suffix(workflow_source):
    matrix = job(workflow_source, "build")
    assert 'exe_suffix: ".exe"' in matrix
    assert "matrix.exe_suffix" in matrix


def test_one_platform_failure_does_not_hide_the_others(workflow_source):
    assert "fail-fast: false" in job(workflow_source, "build")


def test_every_matrix_ceiling_matches_its_adr_row(workflow_source):
    """Each target's size gate must be the number ADR-0014 documents."""
    from tests.packaging.conftest import ADR_PATH

    adr = ADR_PATH.read_text(encoding="utf-8")
    rows = dict(
        (label.strip(), int(mb))
        for label, mb in re.findall(
            r"^\|\s*(Linux x86_64|Windows x86_64|macOS arm64|macOS x86_64)\s*"
            r"\|\s*\*\*(\d+) MB\*\*",
            adr,
            re.M,
        )
    )
    assert len(rows) == 4, "ADR-0014's ceiling table lost a target: %s" % rows

    labels = {
        "linux-x86_64": "Linux x86_64",
        "windows-x86_64": "Windows x86_64",
        "macos-arm64": "macOS arm64",
        "macos-x86_64": "macOS x86_64",
    }
    matrix = job(workflow_source, "build")
    entries = re.findall(
        r"target:\s*(\S+).*?max_exe_bytes:\s*\"(\d+)\"", matrix, re.S
    )
    assert len(entries) == 4, entries
    for target, ceiling in entries:
        documented = rows[labels[target]] * 1024 * 1024
        assert int(ceiling) == documented, (
            "%s gates at %s bytes, ADR-0014 documents %d"
            % (target, ceiling, documented)
        )


def test_the_build_runs_on_every_push_not_only_on_tags(workflow_source):
    """A release path first exercised on tag day is a broken release path."""
    matrix = job(workflow_source, "build")
    assert "if:" not in matrix.split("steps:", 1)[0].replace(
        "if: runner.os", ""
    ), "the build job is conditional; it must run on every push"


# ------------------------------------ packaged-binary acceptance (#4, ADR-0014)


def test_the_frozen_cli_is_driven_end_to_end(workflow_source):
    """#4: "launch -> add PDFs -> run -> report -> export from the binary"."""
    matrix = job(workflow_source, "build")
    smoke = matrix.split("Smoke-test the CLI binary", 1)
    assert len(smoke) == 2, "no CLI smoke step"
    smoke = smoke[1]
    for command in ("version", "module\", \"list", "--help", "\"run\"",
                    "\"list\"", "\"export\""):
        assert command in smoke, "the CLI smoke never runs %s" % command
    assert "metric_values" in smoke, (
        "the smoke never inspects the export, so an empty file would pass"
    )
    assert '"run", "--format", "json"' in smoke, (
        "the smoke reads the localised summary line instead of the JSON"
    )
    assert 'summary["error"] != 0' in smoke, "the smoke tolerates module errors"
    # The human summary is German by default (ADR-0020): a text match on it
    # failed every target against binaries that had run cleanly.
    assert "0 errors" not in smoke


def test_the_frozen_gui_is_actually_launched(workflow_source):
    """The GUI stack is the one the CLI binary no longer carries at all."""
    matrix = job(workflow_source, "build")
    launch = matrix.split("Launch the GUI binary", 1)
    assert len(launch) == 2, "the GUI binary is never launched"
    launch = launch[1]
    assert "xvfb-run" in launch
    assert "124" in launch, "no timeout check, so a crash could read as a pass"
    # Actions runs `bash -e`: a bare `rc=$?` on the next line is never
    # reached, because the expected 124 has already aborted the step.
    assert "|| rc=$?" in launch, "bash -e aborts the step on the passing 124"
    assert "tta.sqlite" in launch, "no proof the app got as far as its project"
    assert "runner.os == 'Linux'" in launch


def test_the_smoke_runs_before_the_artifact_upload(workflow_source):
    """An unproven binary must never be published."""
    matrix = job(workflow_source, "build")
    assert matrix.index("Smoke-test the CLI binary") < matrix.index(
        "upload-artifact"
    )


def test_binaries_are_uploaded_only_for_tags_and_manual_runs(workflow_source):
    """ADR-0014 revision 2026-10-12: a push builds but never uploads; only
    tags and manual runs do. Introduced for the private repo's artefact quota;
    kept unchanged after the repository went public (note 2026-11-18)."""
    header = workflow_source.split("jobs:", 1)[0]
    assert "workflow_dispatch:" in header, "no manual way to fetch a binary"
    upload = job(workflow_source, "build").split("Upload binaries", 1)[1]
    condition = upload.split("uses:", 1)[0]
    assert "startsWith(github.ref, 'refs/tags/v')" in condition, (
        "the release job would find no artefacts to collect"
    )
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert "retention-days:" in upload


def test_only_the_gui_binary_is_uploaded(workflow_source):
    """ADR-0003 revision 2026-10-12: the CLI is frozen for the smoke only;
    its users run it from source, so it never reaches the release."""
    matrix = job(workflow_source, "build")
    upload = matrix.split("Upload binaries", 1)[1]
    assert "dist/tta-gui${{ matrix.exe_suffix }}" in upload
    assert "dist/tta${{ matrix.exe_suffix }}" not in upload
    assert "THIRD_PARTY_LICENSES.txt" in upload
    # ...while the CLI is still frozen and driven by the smoke.
    assert '--exe "tta$EXE_SUFFIX"' in matrix
    assert "CLI_EXE" in matrix.split("Smoke-test the CLI binary", 1)[1]


# ------------------------------------------------- the tagged release (#4)


def test_the_release_job_only_runs_for_v_tags(workflow_source):
    release = job(workflow_source, "release")
    assert "startsWith(github.ref, 'refs/tags/v')" in release
    assert "needs: build" in release


def test_the_release_collects_every_target_and_stays_a_draft(workflow_source):
    """The draft is the owner's final check before publishing (ADR-0014
    revision 2026-11-18; the #8 licence gate it once waited for is closed)."""
    release = job(workflow_source, "release")
    assert "download-artifact" in release
    assert "--draft" in release
    assert "contents: write" in release


def test_the_package_has_one_version():
    """pyproject.toml and tta.__version__ (what About, the report footer and
    exports show) must agree; the first release is 1.0.0 (ADR-0014)."""
    import tomllib

    import tta

    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["project"]["version"] == tta.__version__


def test_a_tag_must_name_the_package_version(workflow_source):
    """A v1.0.0 tag on 0.1.0 code would release binaries that call
    themselves 0.1.0 - checked on tags, before anything is frozen."""
    matrix = job(workflow_source, "build")
    step = matrix.split("name: Tag matches the package version", 1)[1]
    step = step.split("- name:", 1)[0]
    assert "if: startsWith(github.ref, 'refs/tags/v')" in step
    assert "tta.__version__" in step
    assert '"$GITHUB_REF_NAME" != "v$version"' in step
    assert "exit 1" in step
    assert "print(" not in step  # \r\n on Windows: see the step's comment
    assert matrix.index("Tag matches the package version") < matrix.index(
        "pyinstaller packaging/tta.spec"
    )


# ------------------------------------- the README screenshot (#94, ADR-0014)

SCREENSHOT_CONDITION = (
    "if: runner.os == 'Windows' && (startsWith(github.ref, 'refs/tags/v') "
    "|| github.event_name == 'workflow_dispatch')"
)
SCREENSHOT_STEPS = (
    "Display resolution for the README screenshot (Windows)",
    "README screenshot (Windows, non-blocking)",
)
README_SCREENSHOT = "app-hauptfenster-basis.png"


def _step(job_text, name):
    body = job_text.split("- name: " + name + "\n", 1)
    assert len(body) == 2, "no step %r" % name
    return body[1].split("- name:", 1)[0]


def test_the_screenshot_runs_on_windows_for_tags_and_manual_runs(workflow_source):
    """Same condition as the binary upload: every push is covered by the
    tool's smoke test in lint-and-test (windows); a manual run is the dry
    run before tagging."""
    matrix = job(workflow_source, "build")
    for name in SCREENSHOT_STEPS:
        assert SCREENSHOT_CONDITION in _step(matrix, name), name


def test_the_screenshot_never_fails_the_build(workflow_source):
    """The image is documentation: a capture the runner does not allow must
    not turn the job red or keep the release job from running."""
    matrix = job(workflow_source, "build")
    for name in SCREENSHOT_STEPS + ("Upload the README screenshot",):
        assert "continue-on-error: true" in _step(matrix, name), name
    capture = _step(matrix, "README screenshot (Windows, non-blocking)")
    assert "timeout-minutes:" in capture
    assert "::warning::" in capture
    assert "gh release upload" in capture  # the warning names the fallback


def test_the_screenshot_command_is_the_documented_one(workflow_source):
    """SDD 5.6.5 / ADR-0014 name this exact command, from source."""
    capture = _step(job(workflow_source, "build"),
                    "README screenshot (Windows, non-blocking)")
    assert ("python tools/screenshots.py --out screenshot "
            "--only app-hauptfenster-basis") in capture
    assert "id: screenshot" in capture
    assert 'echo "ok=true" >> "$GITHUB_OUTPUT"' in capture


def test_the_screenshot_comes_after_the_binary_upload(workflow_source):
    """The binaries reach the release whatever the capture does."""
    matrix = job(workflow_source, "build")
    upload = matrix.index("name: Upload binaries")
    for name in SCREENSHOT_STEPS + ("Upload the README screenshot",):
        assert upload < matrix.index("- name: " + name + "\n"), name


def test_only_a_checked_screenshot_is_uploaded(workflow_source):
    upload = _step(job(workflow_source, "build"), "Upload the README screenshot")
    assert "if: steps.screenshot.outputs.ok == 'true'" in upload
    assert "name: screenshot" in upload
    assert "path: screenshot/" + README_SCREENSHOT in upload
    assert "retention-days:" in upload


def test_the_release_attaches_the_screenshot_under_its_readme_name(workflow_source):
    """README links releases/latest/download/<this name>, so the collect loop
    must not suffix it with a target, and a missing image is a warning."""
    collect = _step(job(workflow_source, "release"), "Collect the release assets")
    assert '*.png)\n                  out="$name" ;;' in collect
    assert "[ ! -f upload/" + README_SCREENSHOT + " ]" in collect
    assert "::warning::" in collect
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert (
        "https://github.com/olistroemer/Thesis_Text_Analyzer/releases/latest/"
        "download/" + README_SCREENSHOT
    ) in readme


def _screenshot_check_script(workflow_source):
    """The PNG check embedded in the capture step, as CI runs it. Sliced from
    the text, not parsed: PyYAML is not a dependency, and a test that
    importorskips it never runs."""
    import textwrap

    capture = _step(job(workflow_source, "build"),
                    "README screenshot (Windows, non-blocking)")
    script = capture.split("<<'PY'\n", 1)[1].split("\n          PY\n", 1)[0]
    return textwrap.dedent(script)


@pytest.mark.parametrize(
    "size, pattern, accepted",
    [
        ((1402, 632), "varied", True),  # what the tool writes on a desktop
        ((1402, 632), "black", False),  # PrintWindow "succeeded" on nothing
        ((1020, 632), "varied", False),  # clamped to a 1024 px screen
    ],
)
def test_the_screenshot_check_rejects_a_bad_capture(
    workflow_source, tmp_path, size, pattern, accepted
):
    import importlib.util
    import subprocess
    import sys

    spec = importlib.util.spec_from_file_location(
        "tta_screenshots_ci_check", REPO_ROOT / "tools" / "screenshots.py"
    )
    tool = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = tool  # dataclasses resolve their module by name
    try:
        spec.loader.exec_module(tool)
        width, height = size
        if pattern == "black":
            bgra = b"\x00\x00\x00\xff" * (width * height)
        else:
            row = bytes(i % 251 for i in range(width * 4))
            bgra = row * height
        png = tmp_path / README_SCREENSHOT
        tool.write_png(png, width, height, bgra)
    finally:
        sys.modules.pop(spec.name, None)
    result = subprocess.run(
        [sys.executable, "-", str(png)],
        input=_screenshot_check_script(workflow_source),
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


def test_the_release_ships_the_licence_manifest_alongside(workflow_source):
    """A binary is not the only thing ADR-0014 says has to travel."""
    assert "THIRD_PARTY_LICENSES" in job(workflow_source, "release")


def test_only_the_release_job_can_write_to_the_repository(workflow_source):
    """Least privilege: the token is read-only everywhere else."""
    header = workflow_source.split("jobs:", 1)[0]
    assert "contents: read" in header
    for name, text in workflow_jobs(workflow_source).items():
        if name != "release":
            assert "contents: write" not in text, name


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


# ------------------------------------------ both development platforms (5.6.3)


def test_the_suite_is_gated_on_linux_and_native_windows(workflow_source):
    """SDD 5.6.3: native Windows is a development platform, so the suite,
    the coverage gate and the invariants run there too - not only the
    frozen-binary smoke of the build job."""
    test_job = build_job(workflow_source)
    assert "os: ubuntu-latest" in test_job
    assert "os: windows-latest" in test_job
    assert "runs-on: ${{ matrix.os }}" in test_job
    assert "fail-fast: false" in test_job
    # every step is one bash script on both legs, as in the build job
    assert "shell: bash" in test_job


def test_the_linux_only_steps_are_conditional(workflow_source):
    """apt-get and xvfb-run do not exist on the Windows runner."""
    test_job = build_job(workflow_source)
    for step in ("Install Tk and Xvfb (system)", "GUI tests under Xvfb"):
        body = test_job.split("name: " + step, 1)[1].split("- name:", 1)[0]
        assert "if: runner.os == 'Linux'" in body, step


def test_the_ascii_gate_runs_grep_in_a_utf8_locale(workflow_source):
    """Git bash on Windows starts in a locale where `grep -P` refuses to run;
    inside the step's `if`, that error reads as "no match" and the gate
    passes without having checked anything."""
    test_job = build_job(workflow_source)
    body = test_job.split("name: ASCII-source invariant", 1)[1].split("- name:", 1)[0]
    assert "LC_ALL: C.UTF-8" in body


# ------------------------------------------------ action runtimes (#35)

# The first major of each action whose action.yml declares
# `runs.using: node24` (checked with `gh api` against the action's repo,
# 2026-10-14). Anything older targets Node 20, which the runners deprecate:
# it is forced onto Node 24 and warns on every job.
FIRST_NODE24_MAJOR = {
    "actions/checkout": 5,
    "actions/setup-python": 6,
    "actions/upload-artifact": 6,
    "actions/download-artifact": 7,
}


def test_every_action_is_on_a_node24_major(workflow_source):
    """SDD 5.6.4: no action may target the deprecated Node 20 runtime."""
    uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)@v(\d+)\s*$",
                      workflow_source, re.M)
    assert uses, "the workflow uses no actions at all?"
    for action, major in uses:
        assert action in FIRST_NODE24_MAJOR, (
            "%s is not one of the vetted actions; check its runs.using and "
            "add it here (SDD 5.6.4)" % action
        )
        assert int(major) >= FIRST_NODE24_MAJOR[action], (
            "%s@v%s targets Node 20; use v%d or later"
            % (action, major, FIRST_NODE24_MAJOR[action])
        )


def test_the_release_collects_files_below_the_artefact_root(workflow_source):
    """upload-artifact roots a multi-path artefact at the paths' common
    ancestor, so the binary arrives as dist/... and the manifest as
    build/licenses/...: a one-level glob hands `cp` two directories (#35)."""
    release = job(workflow_source, "release")
    collect = release.split("name: Collect the release assets", 1)[1]
    assert 'find "$dir" -type f' in collect
    assert 'for path in "$dir"*' not in collect


def test_the_release_job_names_its_repository_for_gh(workflow_source):
    """Without a checkout `gh` has no git remote to read the repo from."""
    release = job(workflow_source, "release")
    if "actions/checkout" not in release:
        assert "GH_REPO: ${{ github.repository }}" in release
