"""The release build contract: packaging/tta.spec and the CI workflow (#52).

The gates in ADR-0014 only work if the spec and the workflow keep carrying
them. These tests read both files and assert the invariants that a
well-meaning edit could quietly undo - so the fast suite catches it, without
freezing a 110 MB binary.
"""

import ast
import os
import re
import subprocess
import sys

from tests.packaging.conftest import ADR_PATH, REPO_ROOT, SPEC_PATH, job

FORBIDDEN = ("pandas", "numba", "llvmlite", "scipy")
GUI_ONLY = ("matplotlib", "tksheet", "tkinter")


def analysis_calls(source):
    """Map the spec's ``Analysis(...)`` calls by assigned variable name."""
    tree = ast.parse(source)
    calls = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Analysis"
        ):
            target = node.targets[0]
            if isinstance(target, ast.Name):
                calls[target.id] = value
    return calls


def kwarg(call, name):
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def list_literal(source, name):
    """The value of a top-level ``name = [...]`` (or ``a + [...]``) in the spec."""
    namespace = {}
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                namespace[node.targets[0].id] = eval(  # noqa: S307 - spec literals
                    compile(ast.Expression(node.value), "<spec>", "eval"),
                    {},
                    dict(namespace),
                )
            except Exception:
                continue
    return namespace[name]


# --------------------------------------------------------- the spec's gates


def test_both_analysis_calls_exclude_the_undeclared_numeric_stack(spec_source):
    """#52: excludes were [] on both, so pymupdf/nltk dragged the stack in."""
    calls = analysis_calls(spec_source)
    assert set(calls) == {"cli_a", "gui_a"}, "expected exactly two Analysis calls"
    excludes = {
        "cli_a": list_literal(spec_source, "CLI_EXCLUDES"),
        "gui_a": list_literal(spec_source, "EXCLUDES"),
    }
    for name, call in calls.items():
        node = kwarg(call, "excludes")
        assert isinstance(node, ast.Name), (
            "%s must pass a named excludes list, not an inline literal" % name
        )
        assert node.id in ("EXCLUDES", "CLI_EXCLUDES")
        for package in FORBIDDEN:
            assert package in excludes[name], (
                "%s does not exclude %r" % (name, package)
            )


def test_the_cli_graph_excludes_the_gui_stack(spec_source):
    """The CLI cannot reach matplotlib/tksheet/tkinter; it must not carry them.

    nltk imports matplotlib from inside method bodies, so removing it from
    hiddenimports is not sufficient - the exclude is what does the work.
    """
    cli_excludes = list_literal(spec_source, "CLI_EXCLUDES")
    for package in GUI_ONLY:
        assert package in cli_excludes


def test_the_gui_graph_does_not_exclude_what_it_needs(spec_source):
    """Excluding matplotlib globally would break the report view (ADR-0016)."""
    gui_excludes = list_literal(spec_source, "EXCLUDES")
    for package in GUI_ONLY:
        assert package not in gui_excludes


def test_hiddenimports_are_scoped_per_binary(spec_source):
    """Sharing one list is why the CLI binary was larger than the GUI (#52)."""
    calls = analysis_calls(spec_source)
    cli_node = kwarg(calls["cli_a"], "hiddenimports")
    gui_node = kwarg(calls["gui_a"], "hiddenimports")
    assert isinstance(cli_node, ast.Name) and isinstance(gui_node, ast.Name)
    assert cli_node.id != gui_node.id, (
        "both Analysis calls share one hiddenimports list"
    )

    shared = list_literal(spec_source, "shared_hiddenimports")
    gui = list_literal(spec_source, "gui_hiddenimports")
    for package in GUI_ONLY:
        assert package not in shared, "%r must not be a shared hidden import" % package
        assert package in gui, "%r must stay a GUI hidden import" % package
    # The GUI still needs everything the CLI needs.
    assert set(shared) <= set(gui)


def test_shared_hiddenimports_still_cover_the_analysis_modules(spec_source):
    """These are the imports PyInstaller's static analysis actually misses."""
    shared = list_literal(spec_source, "shared_hiddenimports")
    for package in ("langdetect", "textstat", "pypdf", "fitz"):
        assert package in shared


def test_spec_is_ascii_like_the_rest_of_the_source(spec_source):
    """ADR-0018 greps *.py only; the spec is Python and should match it."""
    assert spec_source.isascii()


# ------------------------------------------- the clean-environment gate itself


def _run_spec(user_site):
    """Execute the spec's prologue with ``site.ENABLE_USER_SITE`` forced.

    The spec raises SystemExit from its clean-environment guard before it
    touches SPECPATH or nltk, so executing it standalone is enough to
    observe the guard - and to observe that it does NOT fire when the user
    site is off (it then fails later, on the undefined SPECPATH).

    The flag is set in-process rather than through the environment on
    purpose. There is no way to switch the user site back ON from outside
    the interpreter (PYTHONNOUSERSITE only turns it off), and the host
    interpreter's own value varies: a conda env and a bare system Python
    report True, while a plain ``python -m venv`` reports False. Driving the
    flag directly makes both directions testable from any environment - the
    negative case is what the *build* environment ADR-0014 recommends
    actually looks like.
    """
    preamble = "import site; site.ENABLE_USER_SITE = %r; " % bool(user_site)
    proc = subprocess.run(
        [sys.executable, "-c",
         preamble + "exec(compile(open(%r).read(), %r, 'exec'))"
         % (str(SPEC_PATH), str(SPEC_PATH))],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={k: v for k, v in os.environ.items() if k != "PYTHONNOUSERSITE"},
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_spec_refuses_to_build_when_the_user_site_is_live():
    """The #52 root cause: llvmlite and numba came from ~/.local."""
    rc, output = _run_spec(user_site=True)
    assert rc != 0
    assert "refusing to build" in output
    assert "PYTHONNOUSERSITE=1" in output


def test_spec_gets_past_the_guard_with_the_user_site_disabled():
    """Proof the guard is not simply always-on."""
    rc, output = _run_spec(user_site=False)
    assert "refusing to build" not in output
    # It still fails: SPECPATH is only defined when PyInstaller execs the spec.
    assert "SPECPATH" in output


def test_pythonnousersite_is_what_the_fix_message_says_it_is():
    """The guard's advice must actually satisfy the guard.

    Separated from the two tests above because this one asserts a property of
    CPython, not of the spec: PYTHONNOUSERSITE=1 disables the user site in
    any interpreter, which is why ADR-0014 mandates it for release builds
    (and why the workflow sets it for the whole build job).
    """
    env = dict(os.environ, PYTHONNOUSERSITE="1")
    proc = subprocess.run(
        [sys.executable, "-c", "import site; print(site.ENABLE_USER_SITE)"],
        capture_output=True, text=True, env=env,
    )
    assert proc.stdout.strip() == "False", proc.stdout + proc.stderr


# ----------------------------------------------------------- the CI workflow


def test_build_job_disables_the_user_site(workflow_source):
    build_job = job(workflow_source, "build")
    assert re.search(r'PYTHONNOUSERSITE:\s*"1"', build_job), (
        "the build job must set PYTHONNOUSERSITE=1 (ADR-0014)"
    )


def test_the_user_site_is_disabled_for_every_matrix_target(workflow_source):
    """It is job-level env, so it must sit outside the per-target entries.

    A per-step or per-target setting is the version of this that ships a
    contaminated Windows binary while Linux stays clean.
    """
    build_job = job(workflow_source, "build")
    env_block = build_job.split("\n    env:\n", 1)
    assert len(env_block) == 2, "the build job has no job-level env block"
    assert re.search(
        r'PYTHONNOUSERSITE:\s*"1"', env_block[1].split("\n    ", 1)[0]
    ), "PYTHONNOUSERSITE is not set at job level"


def test_build_job_runs_the_build_gates(workflow_source):
    assert "packaging/check_build.py" in workflow_source
    assert "--max-bytes" in workflow_source


def test_the_size_gate_is_wired_to_the_matrix_ceiling(workflow_source):
    """Every target's gate reads its own ceiling from the matrix.

    The per-target numbers are cross-checked against ADR-0014's table in
    tests/packaging/test_ci_workflow.py; this asserts the plumbing.
    """
    build_job = job(workflow_source, "build")
    assert "TTA_MAX_EXE_BYTES: ${{ matrix.max_exe_bytes }}" in build_job
    assert '--max-bytes "$TTA_MAX_EXE_BYTES"' in build_job


def test_the_linux_ceiling_still_matches_the_adr(workflow_source):
    """The one measured row, kept honest here as well as per-target."""
    adr = ADR_PATH.read_text(encoding="utf-8")
    documented = re.search(r"\|\s*Linux x86_64\s*\|\s*\*\*(\d+) MB\*\*", adr)
    assert documented, "ADR-0014 has no Linux size-gate row"
    expected = int(documented.group(1)) * 1024 * 1024
    build_job = job(workflow_source, "build")
    linux = re.search(
        r"target:\s*linux-x86_64.*?max_exe_bytes:\s*\"(\d+)\"",
        build_job,
        re.S,
    )
    assert linux, "no linux-x86_64 matrix entry with a ceiling"
    assert int(linux.group(1)) == expected, (
        "workflow ceiling %s bytes disagrees with ADR-0014's %s MB"
        % (linux.group(1), documented.group(1))
    )


def test_gate_runs_before_the_artifact_upload(workflow_source):
    """A binary that fails the gate must never be published."""
    gate = workflow_source.index("packaging/check_build.py")
    upload = workflow_source.index("upload-artifact")
    assert gate < upload


def test_boundary_and_ascii_invariants_are_still_enforced(workflow_source):
    """Issue #3's gates - the reason this workflow exists."""
    assert re.search(r"grep -rn 'tta\\\.ui' tta/core tta/cli", workflow_source)
    assert re.search(r"grep -rn 'tta\\\.cli' tta/core tta/ui", workflow_source)
    assert "ADR-0018" in workflow_source
