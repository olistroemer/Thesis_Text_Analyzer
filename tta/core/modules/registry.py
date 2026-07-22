"""Module registry: validation at registration + topological order.

Registration checks (SDD Sec. 6.4, ADR-0005):
- declared artefact kinds must be in the documented vocabulary,
- module names are unique,
- exactly one producer per artefact kind (startup error otherwise),
- every consumed kind has a registered producer.
"""

from __future__ import annotations

from collections.abc import Iterable

from tta.core import artefact_kinds
from tta.core.modules.base import Module


class ModuleRegistry:
    def __init__(self, modules: Iterable[Module]):
        self._by_name: dict[str, Module] = {}
        self._producer_by_kind: dict[str, Module] = {}
        for module in modules:
            spec = module.spec
            if spec.name in self._by_name:
                raise ValueError(f"duplicate module name {spec.name!r}")
            artefact_kinds.validate_kinds(
                spec.consumes + spec.produces_artefacts, owner=spec.name
            )
            for kind in spec.produces_artefacts:
                other = self._producer_by_kind.get(kind)
                if other is not None:
                    raise ValueError(
                        f"two producers registered for artefact kind {kind!r}: "
                        f"{other.spec.name!r} and {spec.name!r} (ADR-0005: exactly one per kind)"
                    )
                self._producer_by_kind[kind] = module
            self._by_name[spec.name] = module
        for module in self._by_name.values():
            for kind in module.spec.consumes:
                if kind not in self._producer_by_kind:
                    raise ValueError(
                        f"module {module.spec.name!r} consumes {kind!r} but no producer is registered"
                    )
        self._topo: list[Module] = self._topological_order()

    def _topological_order(self) -> list[Module]:
        """Kahn's algorithm over producer->consumer edges; insertion order
        breaks ties so the result is deterministic."""
        modules = list(self._by_name.values())
        remaining_deps = {
            m.spec.name: {self._producer_by_kind[k].spec.name for k in m.spec.consumes}
            for m in modules
        }
        ordered: list[Module] = []
        ready = [m for m in modules if not remaining_deps[m.spec.name]]
        while ready:
            current = ready.pop(0)
            ordered.append(current)
            for m in modules:
                deps = remaining_deps[m.spec.name]
                if current.spec.name in deps:
                    deps.remove(current.spec.name)
                    if not deps:
                        ready.append(m)
        if len(ordered) != len(modules):
            cyclic = sorted(set(remaining_deps) - {m.spec.name for m in ordered})
            raise ValueError(f"artefact-kind dependency cycle involving {cyclic}")
        return ordered

    def get(self, name: str) -> Module:
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"no module registered as {name!r}") from None

    def names(self) -> list[str]:
        return [m.spec.name for m in self._topo]

    def producer_of(self, kind: str) -> Module:
        return self._producer_by_kind[kind]

    def in_topological_order(self, names: Iterable[str] | None = None) -> list[Module]:
        wanted = set(self.names() if names is None else names)
        unknown = wanted - set(self._by_name)
        if unknown:
            raise KeyError(f"unknown module(s): {sorted(unknown)}")
        return [m for m in self._topo if m.spec.name in wanted]


def default_registry() -> ModuleRegistry:
    """The MVP catalogue (SDD Sec. 7.1, ADR-0011)."""
    from tta.core.modules.check_extraction_quality import CheckExtractionQuality
    from tta.core.modules.classify_language import ClassifyLanguage
    from tta.core.modules.classify_thesis_type import ClassifyThesisType
    from tta.core.modules.count_images import CountImages
    from tta.core.modules.extract_pdf_metadata import ExtractPdfMetadata
    from tta.core.modules.extract_pymupdf import ExtractPymupdf
    from tta.core.modules.readability import Readability
    from tta.core.modules.redundancy import Redundancy
    from tta.core.modules.surface_counts import SurfaceCounts
    from tta.core.modules.tokenize import Tokenize
    from tta.core.modules.vocabulary import Vocabulary

    return ModuleRegistry(
        [
            ExtractPymupdf(),
            CheckExtractionQuality(),
            ClassifyLanguage(),
            ClassifyThesisType(),
            Tokenize(),
            SurfaceCounts(),
            Vocabulary(),
            Readability(),
            Redundancy(),
            CountImages(),
            ExtractPdfMetadata(),
        ]
    )
