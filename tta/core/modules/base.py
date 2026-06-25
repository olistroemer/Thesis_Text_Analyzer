"""Module contract - load-bearing public API (SDD Sec. 6.2, ADR-0004).

External researchers build modules against exactly this surface; for MVP
the git commit hash is the de-facto contract version (an explicit
``CONTRACT_VERSION`` constant is deferred, SDD Sec. 12).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tta.core.types import Thesis


@dataclass(frozen=True)
class ModuleSpec:
    """Static declaration of a module's identity and data flow.

    ``consumes`` / ``produces_artefacts`` hold artefact kinds from the
    documented vocabulary (``core/artefact_kinds.py``); they are validated
    at registration, not here. ``version`` must be bumped on any
    behaviour change so stale runs are detectable (QA-REPRO, ADR-0006).
    """

    name: str
    version: str
    consumes: tuple[str, ...] = ()
    produces_artefacts: tuple[str, ...] = ()
    produces_metrics: tuple[str, ...] = ()


@dataclass
class RunContext:
    """Everything a module may touch during one run (QA-TEST: trivially fakeable)."""

    thesis: Thesis
    artefacts: dict[str, Path]  # consumed artefacts by kind
    workdir: Path  # where to write produced artefacts


@dataclass
class RunResult:
    metrics: dict[str, Any] = field(default_factory=dict)
    artefacts: dict[str, Path] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Applicability:
    ok: bool
    reason: str | None = None


class NotApplicable(Exception):
    """Raised from ``run()`` when applicability depends on consumed artefact
    content (e.g. the detected language, SDD Sec. 7.2); the runner records an
    ``na`` outcome with the exception message as reason (SDD Sec. 6.3).

    ``applicable()`` remains the place for checks that need only the
    ``Thesis`` row, such as the file extension.
    """


class Module(ABC):
    """An analysis unit consuming artefacts and producing metrics/artefacts.

    Subclasses set the ``spec`` class attribute and implement ``run``.
    A module returning ``Applicability(ok=False)`` records an ``na``
    outcome that cascades to its dependents (SDD Sec. 6.3).
    """

    spec: ModuleSpec

    def applicable(self, thesis: Thesis) -> Applicability:
        return Applicability(ok=True)

    @abstractmethod
    def run(self, ctx: RunContext) -> RunResult: ...
