"""Pure, toolkit-free run-progress estimation (SDD Sec. 5.5, #39).

The GUI progress bar (and any CLI progress affordance) drive their display from
this module. It imports nothing from the ``tta/ui`` or ``tta/cli`` adapter
packages and needs no Tk display, so it is unit-testable in isolation (ADR-0002
boundary; hard invariant 3 of the gui-features lane).

The estimate is *size-weighted*: each module has a cost rate in milliseconds per
byte (from history via ``Repository.module_duration_stats`` and/or observed in
the current run), and the remaining time is the sum over the remaining
``(thesis x module)`` pairs of ``rate[module] * that thesis's size in bytes``.
Bigger remaining theses therefore lengthen the estimate, not merely more of them
- the user's explicit requirement.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    fraction: float  # 0.0..1.0, for a determinate progress bar
    eta_seconds: float | None  # None => not enough data yet ("estimating...")
    done: int
    total: int


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def estimate(
    done: int,
    total: int,
    remaining: Sequence[tuple[str, int]],
    rates: Mapping[str, float],
    elapsed_s: float = 0.0,
) -> Progress:
    """Return the determinate-bar fraction and a size-weighted ETA (#39).

    Args:
        done: ``(thesis x module)`` pairs completed so far in the run.
        total: total pairs planned for the run.
        remaining: the not-yet-done pairs, each ``(module_name, thesis_size_bytes)``.
        rates: per-module cost in ms per byte - history merged with in-run
            observations by the caller. A module missing here falls back to the
            mean of the known rates.
        elapsed_s: seconds elapsed since the run started. Used only as a
            last-resort count-proportional fallback when no size-weighted rate
            can yet be formed (see below).

    ETA rules:
        - No remaining pairs -> ``0.0`` seconds.
        - At least one positive rate is known -> size-weighted sum, with any
          module lacking its own rate using the mean of the known rates.
        - No rate anywhere yet (first run, before any pair of any module has
          produced an observation) -> a count-proportional estimate from
          ``elapsed_s`` once at least one pair has completed, else ``None`` so
          the caller shows "estimating..." while the bar still advances.
    """
    fraction = 0.0 if total <= 0 else max(0.0, min(1.0, done / total))
    if not remaining:
        return Progress(fraction=fraction, eta_seconds=0.0, done=done, total=total)

    positive = [r for r in rates.values() if r and r > 0]
    fallback_rate = _mean(positive)  # None until some rate is known

    if fallback_rate is not None:
        total_ms = 0.0
        for module, size in remaining:
            rate = rates.get(module)
            if not rate or rate <= 0:
                rate = fallback_rate
            total_ms += rate * max(size, 0)
        if total_ms > 0:
            return Progress(
                fraction=fraction, eta_seconds=total_ms / 1000.0, done=done, total=total
            )

    # No usable size-weighted rate yet (no history/observations, or every
    # remaining size is unknown): fall back to a count-proportional estimate
    # from the elapsed time, or None ("estimating...") before any pair is done.
    if done > 0 and elapsed_s > 0:
        return Progress(
            fraction=fraction,
            eta_seconds=elapsed_s * (len(remaining) / done),
            done=done,
            total=total,
        )
    return Progress(fraction=fraction, eta_seconds=None, done=done, total=total)


def format_eta(seconds: float | None) -> str:
    """Compact human ETA for a progress label; ``None`` -> 'estimating...'."""
    if seconds is None:
        return "estimating..."
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
