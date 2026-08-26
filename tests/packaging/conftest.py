"""Shared helpers for the packaging/build-gate tests (ADR-0014).

These tests exercise the release *build contract* - the PyInstaller spec, the
CI workflow, and the build-gate checker - not application code. They are
here so that a regression of #52 (a 212 MB binary contaminated by undeclared
packages) is caught by the fast suite, without freezing a binary.
"""

import importlib.util
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "packaging" / "tta.spec"
CHECKER_PATH = REPO_ROOT / "packaging" / "check_build.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ADR_PATH = REPO_ROOT / "docs" / "adr" / "0014-distribution.md"


@pytest.fixture(scope="session")
def check_build():
    """packaging/check_build.py loaded by path.

    It cannot be imported as ``packaging.check_build``: the repo's
    ``packaging/`` directory is not a Python package and the name collides
    with the third-party ``packaging`` distribution.
    """
    spec = importlib.util.spec_from_file_location(
        "tta_check_build", CHECKER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AGPL_PATH = REPO_ROOT / "packaging" / "licenses" / "AGPL-3.0.txt"
GENERATOR_PATH = REPO_ROOT / "packaging" / "gen_third_party_licenses.py"


@pytest.fixture(scope="session")
def generator():
    """packaging/gen_third_party_licenses.py loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "tta_gen_third_party_licenses", GENERATOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def spec_source():
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture
def workflow_source():
    return WORKFLOW_PATH.read_text(encoding="utf-8")


# A job id at the workflow's job indent level. Slicing the file by these is
# enough for the assertions here and keeps the tests free of a YAML
# dependency; the one test that needs real parsing importorskips PyYAML.
_JOB_ID = re.compile(r"^  ([A-Za-z][\w-]*):$", re.M)


def workflow_jobs(source):
    """{job_id: that job's text}, so a job rename cannot silently pass.

    The old helpers split the file on the literal "build-linux:", which meant
    a renamed or removed job handed the assertions the *whole* file and they
    kept passing.
    """
    body = source.split("\njobs:\n", 1)[1]
    marks = [(m.start(), m.group(1)) for m in _JOB_ID.finditer(body)]
    jobs = {}
    for index, (start, name) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(body)
        jobs[name] = body[start:end]
    return jobs


def job(source, name):
    jobs = workflow_jobs(source)
    assert name in jobs, "no %r job in the workflow (have: %s)" % (
        name, ", ".join(sorted(jobs)),
    )
    return jobs[name]


def write_toc(path, entries, scripts=()):
    """Write a synthetic Analysis-NN.toc.

    Mirrors the real file: the repr of a tuple whose members include the
    collected TOC lists. The checker walks the structure rather than
    indexing it, so the exact arity does not matter.
    """
    payload = (
        list(scripts),
        [],
        [],
        [],
        {},
        [],
        [],
        False,
        {},
        0,
        [],
        [],
        "3.12.13",
        [(name.rsplit("/", 1)[-1], name, "PYSOURCE") for name in scripts],
        list(entries),
        [],
        [],
        [],
        [],
        [],
    )
    path.write_text(repr(payload), encoding="utf-8")
    return path
