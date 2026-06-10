"""Contract tests for core.modules.base (SDD §6.2, ADR-0004)."""

import dataclasses
from pathlib import Path

import pytest

from pds.core.modules.base import Applicability, Module, ModuleSpec, RunContext, RunResult
from pds.core.types import Thesis


def make_thesis(**overrides):
    defaults = dict(
        id=None,
        pdf_sha256="0" * 64,
        pdf_path="/tmp/some.pdf",
        pdf_filename="some.pdf",
    )
    defaults.update(overrides)
    return Thesis(**defaults)


class NoopModule(Module):
    spec = ModuleSpec(name="mod_noop", version="1.0.0")

    def run(self, ctx: RunContext) -> RunResult:
        return RunResult()


def test_module_spec_is_frozen():
    spec = ModuleSpec(name="mod_x", version="1.0.0")
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "mod_y"


def test_module_spec_defaults_are_empty():
    spec = ModuleSpec(name="mod_x", version="1.0.0")
    assert spec.consumes == ()
    assert spec.produces_artefacts == ()
    assert spec.produces_metrics == ()


def test_module_without_run_is_abstract():
    class Incomplete(Module):
        spec = ModuleSpec(name="mod_incomplete", version="1.0.0")

    with pytest.raises(TypeError):
        Incomplete()


def test_default_applicability_is_ok():
    result = NoopModule().applicable(make_thesis())
    assert result == Applicability(ok=True, reason=None)


def test_run_result_defaults_are_independent():
    a, b = RunResult(), RunResult()
    a.metrics["x"] = 1
    assert b.metrics == {}
    assert a.artefacts == {} and a.notes == {}


def test_run_context_is_plain_data(tmp_path):
    ctx = RunContext(thesis=make_thesis(), artefacts={"raw_text": Path("t.txt")}, workdir=tmp_path)
    assert ctx.artefacts["raw_text"] == Path("t.txt")
    assert ctx.workdir == tmp_path
