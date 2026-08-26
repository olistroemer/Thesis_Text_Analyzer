"""In-process pub/sub for run progress (SDD Sec. 5.5, ADR-0013).

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
class HashingProgress:
    """The deferred-SHA-256 pass, which runs **before** ``RunStarted``.

    On a large corpus this is real work (ADR-0006 first-run hashing) and used to show
    up as a silent, mislabelled "Planning..." - ``plan()`` itself never hashes
    and never reads a file (#59). ``total`` counts the theses needing a hash;
    an adapter that ignores this event loses nothing but the display.
    """

    done: int
    total: int


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


#: ``ModuleCompleted.status`` for a planned pair that will not run in this run
#: (its worker timed out, died, or was abandoned on cancel). Carries
#: ``duration_ms=None`` and, unlike the other statuses, **no DB row**: the pair
#: stays ``missing`` and the next default run picks it up. Adapters retire it
#: from their remaining set like any other completion, which is the whole point
#: - without it a killed worker's independent modules leaked from the progress
#: accounting and the bar could never reach 100 % (#55, ADR-0013 failure policy).
MODULE_SKIPPED = "skipped"


@dataclass(frozen=True)
class ModuleCompleted:
    """One planned ``(thesis x module)`` pair reached a terminal state.

    Every pair in the ``RunStarted`` plan is followed by exactly one of these,
    whatever happens to its worker - adapters may rely on that to close their
    pair accounting.
    """

    thesis_id: int
    module_name: str
    status: str  # ok | na | error | skipped (MODULE_SKIPPED)
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
    abandoned: int = 0  # in flight when the cancel grace ran out (#57)


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
