"""ModuleRegistry tests (ADR-0005 single-producer rule, topo order)."""

import pytest

from tta.core import artefact_kinds
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult
from tta.core.modules.registry import ModuleRegistry, default_registry


def make_module(name, consumes=(), produces=()):
    class _M(Module):
        spec = ModuleSpec(
            name=name, version="1.0.0", consumes=consumes, produces_artefacts=produces
        )

        def run(self, ctx: RunContext) -> RunResult:
            return RunResult()

    return _M()


def test_rejects_two_producers_for_one_kind():
    with pytest.raises(ValueError, match="two producers.*raw_text"):
        ModuleRegistry(
            [
                make_module("mod_a", produces=(artefact_kinds.RAW_TEXT,)),
                make_module("mod_b", produces=(artefact_kinds.RAW_TEXT,)),
            ]
        )


def test_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown artefact kind"):
        ModuleRegistry([make_module("mod_a", produces=("embeddings",))])


def test_rejects_consumer_without_producer():
    with pytest.raises(ValueError, match="no producer"):
        ModuleRegistry([make_module("mod_a", consumes=(artefact_kinds.RAW_TEXT,))])


def test_rejects_duplicate_names():
    with pytest.raises(ValueError, match="duplicate module name"):
        ModuleRegistry([make_module("mod_a"), make_module("mod_a")])


def test_topological_order():
    registry = ModuleRegistry(
        [
            make_module(
                "mod_tok",
                consumes=(artefact_kinds.RAW_TEXT,),
                produces=(artefact_kinds.TOKENS,),
            ),
            make_module("mod_counts", consumes=(artefact_kinds.TOKENS,)),
            make_module("mod_extract", produces=(artefact_kinds.RAW_TEXT,)),
        ]
    )
    names = [m.spec.name for m in registry.in_topological_order()]
    assert names.index("mod_extract") < names.index("mod_tok") < names.index("mod_counts")


def test_subset_keeps_topo_order_and_rejects_unknown():
    registry = default_registry()
    subset = registry.in_topological_order(["mod_tokenize", "mod_extract_pymupdf"])
    assert [m.spec.name for m in subset] == ["mod_extract_pymupdf", "mod_tokenize"]
    with pytest.raises(KeyError, match="unknown module"):
        registry.in_topological_order(["mod_nope"])


def test_default_registry_matches_catalogue():
    registry = default_registry()
    assert len(registry.names()) == 10  # SDD §7.1 / ADR-0011
    names = registry.names()
    # DAG constraints from SDD §5.3
    assert names.index("mod_extract_pymupdf") < names.index("mod_classify_language")
    assert names.index("mod_classify_language") < names.index("mod_tokenize")
    assert names.index("mod_tokenize") < names.index("mod_surface_counts")
    # 26 metrics across the catalogue (ADR-0011 rev. 2)
    metric_count = sum(len(m.spec.produces_metrics) for m in registry.in_topological_order())
    assert metric_count == 26
