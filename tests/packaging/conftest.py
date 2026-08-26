"""Shared helpers for the packaging/build-gate tests (ADR-0014).

These tests exercise the release *build contract* - the PyInstaller spec, the
CI workflow, and the build-gate checker - not application code. They are
here so that a regression of #52 (a 212 MB binary contaminated by undeclared
packages) is caught by the fast suite, without freezing a binary.
"""

import importlib.util
import pathlib

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


@pytest.fixture
def spec_source():
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture
def workflow_source():
    return WORKFLOW_PATH.read_text(encoding="utf-8")


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
