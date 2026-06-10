"""In-process pub/sub for run progress (SDD §5.5, ADR-0013).

The main process publishes; workers never do. Adapters subscribe and
marshal into their own event loops (GUI via ``root.after``, CLI via
direct stderr render).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunStarted:
    plan: Any  # RunPlan; typed loosely to avoid a runner import cycle


@dataclass(frozen=True)
class ThesisStarted:
    thesis_id: int


@dataclass(frozen=True)
class ModuleStarted:
    thesis_id: int
    module_name: str


@dataclass(frozen=True)
class ModuleCompleted:
    thesis_id: int
    module_name: str
    status: str  # ok | na | error
    duration_ms: int | None


@dataclass(frozen=True)
class ThesisCompleted:
    thesis_id: int
    summary: dict[str, int]  # status -> count


@dataclass(frozen=True)
class RunCompleted:
    summary: Any  # RunSummary


@dataclass(frozen=True)
class RunCancelled:
    completed: int  # theses finished before the cancel took effect
    skipped: int  # theses never started


class EventBus:
    """Synchronous in-process bus. Handler errors are logged, not raised:
    a broken adapter must not abort an analysis batch."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self._catch_all: list[Callable[[Any], None]] = []

    def subscribe(self, event_type: type, handler: Callable[[Any], None]) -> None:
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: Callable[[Any], None]) -> None:
        self._catch_all.append(handler)

    def publish(self, event: Any) -> None:
        for handler in self._handlers[type(event)] + self._catch_all:
            try:
                handler(event)
            except Exception:
                logger.exception("event handler %r failed on %r", handler, event)
