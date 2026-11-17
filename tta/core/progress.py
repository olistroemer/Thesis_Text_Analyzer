"""Pure, toolkit-free run-progress estimation (SDD Sec. 5.5, #39, #54, #58).

The GUI progress bar (and any CLI progress affordance) drive their display from
this module. It imports nothing from the ``tta/ui`` or ``tta/cli`` adapter
packages and needs no Tk display, so it is unit-testable in isolation (ADR-0002
boundary).

Nothing here reads the clock. The caller passes wall-clock elapsed seconds (for
the in-flight pairs) and the runner's worker count in, so every function is a
deterministic function of its arguments.

The model, per SDD Sec. 5.5:

*   **Affine cost.** One ``(thesis x module)`` pair costs
    ``intercept_ms + slope_ms_per_byte * pdf_size_bytes``. Not a pure rate:
    part of the cost is constant per document and several modules are page-
    or token-driven rather than byte-driven. ``Repository.module_duration_stats``
    fits the pair from history; ``fit_cost`` is the maths.
*   **Priors.** A module with no history uses a per-module prior measured on
    a warm, reused worker (``prior_cost``, #86) - never the mean of whichever
    rates happen to be known already, which on a first run priced all eleven
    not-yet-reported modules at the extractor's rate (#54).
*   **Worker start-up.** Workers are long-lived (ADR-0013 rev. 3, #86), so the
    library start-up is a one-off per worker, not part of every thesis. The
    workers start in parallel, so ``estimate`` adds it once (``startup_ms``).
*   **Parallelism.** Theses run concurrently (up to ``workers``) while modules
    within a thesis are serial, so remaining cost is bucketed per thesis and the
    estimate is a makespan bound: the worker-count division or the longest
    single remaining thesis, whichever is larger.
*   **Countdown.** In-flight pairs are credited with the seconds already burned,
    so the estimate decays between events; ``damp_eta`` smooths successive
    estimates so the label reads as a countdown.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from tta.core.i18n import _

#: ``(intercept_ms, slope_ms_per_byte)`` - the affine cost of one module on one
#: thesis. ``intercept`` is the size-independent part (fixed per-document
#: setup); ``slope`` scales with the PDF's byte size.
CostModel = tuple[float, float]

#: Nominal size of a median thesis - the exp-86 sample's median PDF is 2.16 MB.
#: Only used to turn a per-module prior into a slope.
PRIOR_THESIS_BYTES = 2_000_000

#: Per-module prior cost in milliseconds, for modules with no recorded history
#: (#86). Measured, not budgeted: the mean ``duration_ms`` per module on a warm,
#: reused worker (exp-86 sample, 200 theses, 1 worker, i7-13700H, native
#: Windows, with #85's non-decoding ``mod_count_images``; the worker's first
#: thesis excluded), ~0.83 s per thesis in sum. A mean rather than a median
#: because an ETA sums expected costs and several modules have a long tail.
#: ADR-0015's budget table used to seed these; its figures are ceilings that
#: contained the per-thesis library start-up, so they overstated a first run's
#: estimate several times over. On slower hardware the in-run blend corrects a
#: prior within a few observations (``HISTORY_WEIGHT``).
MODULE_PRIOR_MS: dict[str, float] = {
    "mod_extract_pymupdf": 170.0,
    "mod_check_extraction_quality": 25.0,
    "mod_classify_language": 20.0,
    "mod_tokenize": 143.0,
    "mod_surface_counts": 52.0,
    "mod_vocabulary": 23.0,
    "mod_readability": 141.0,
    "mod_redundancy": 41.0,
    "mod_count_images": 110.0,
    "mod_extract_pdf_metadata": 93.0,
    "mod_determine_publication_year": 7.0,
    "mod_classify_thesis_type": 1.0,
    "mod_extract_filesystem_metadata": 1.0,
}

#: Prior for a module absent from the table (a newer or third-party module):
#: the order of magnitude of the cheap-to-middling entries above.
DEFAULT_PRIOR_MS = 100.0

#: One-off start-up of a worker process in milliseconds (#86): interpreter
#: spawn plus the library imports (nltk, textstat, langdetect, PyMuPDF) that a
#: long-lived worker pays once. Measured as the per-thesis wall-clock
#: difference between fresh and reused workers on the exp-86 sample at 1
#: worker (592.6 s against 173.4 s for 200 theses); the trial saw ~2.6 s.
WORKER_STARTUP_MS = 2100.0

#: Fraction of a prior attributed to the size-independent part. One number per
#: module is measured, not a split, so an even split is the neutral choice: at
#: ``PRIOR_THESIS_BYTES`` the prior reproduces the measured cost exactly, while
#: a thesis twice that size costs 1.5x rather than 2x.
PRIOR_INTERCEPT_SHARE = 0.5

#: Pseudo-count given to the history/prior model when blending in-run
#: observations (``blend_cost``): the in-run model needs this many samples
#: before it outweighs history. Small, because in-run observations come from
#: the very machine and corpus being estimated.
HISTORY_WEIGHT = 3.0

#: Share of a *rise* in the raw estimate that ``damp_eta`` lets through per
#: call. Falls are shown immediately.
RISE_FACTOR = 0.25


@dataclass(frozen=True)
class Progress:
    fraction: float  # 0.0..1.0, for a determinate progress bar
    eta_seconds: float | None  # None => not enough data yet ("estimating...")
    done: int  # (thesis x module) pairs completed
    total: int  # (thesis x module) pairs planned
    theses_done: int = 0  # primary readout for the label (#58)
    theses_total: int = 0


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def prior_cost(module: str) -> CostModel:
    """Per-module cost prior from the measured table (#54, #86).

    The prior is split ``PRIOR_INTERCEPT_SHARE`` constant / remainder
    size-proportional at ``PRIOR_THESIS_BYTES``, so a nominal thesis costs
    exactly the prior and larger theses cost proportionally more - but not
    linearly more, which matches the constant per-document overhead.
    """
    prior = MODULE_PRIOR_MS.get(module, DEFAULT_PRIOR_MS)
    intercept = prior * PRIOR_INTERCEPT_SHARE
    slope = (prior - intercept) / PRIOR_THESIS_BYTES
    return (intercept, slope)


def fit_cost(samples: Sequence[tuple[float, float]]) -> CostModel | None:
    """Least-squares ``(intercept_ms, slope_ms_per_byte)`` over observations.

    Args:
        samples: ``(pdf_size_bytes, duration_ms)`` pairs for ONE module.

    Returns ``None`` for no samples. Coefficients are never negative: a fit
    with a negative slope degrades to intercept-only (the mean duration) and
    one with a negative intercept to a line through the origin, because a
    module that gets cheaper on bigger PDFs, or costs negative time at zero
    bytes, is noise rather than signal.

    Observations at a **single distinct size** give intercept-only. One size
    carries no information about size dependence, and reading it as a rate is
    precisely how a single small thesis used to inflate the estimate for every
    large one still queued (#54).
    """
    points = [(max(float(size), 0.0), float(dur)) for size, dur in samples]
    if not points:
        return None
    if len({size for size, _ in points}) < 2:
        return (_mean(dur for _, dur in points), 0.0)
    n = float(len(points))
    sx = sum(size for size, _ in points)
    sy = sum(dur for _, dur in points)
    sxx = sum(size * size for size, _ in points)
    sxy = sum(size * dur for size, dur in points)
    denom = n * sxx - sx * sx
    if denom <= 0:  # defensive; distinct sizes >= 2 makes this unreachable
        return (_mean(dur for _, dur in points), 0.0)
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    if slope < 0:
        return (_mean(dur for _, dur in points), 0.0)
    if intercept < 0:
        return (0.0, sxy / sxx) if sxx > 0 else (_mean(dur for _, dur in points), 0.0)
    return (intercept, slope)


def blend_cost(
    base: CostModel | None,
    observed: CostModel | None,
    observed_n: int,
    *,
    history_weight: float = HISTORY_WEIGHT,
) -> CostModel | None:
    """Blend an in-run cost model into history/prior by sample weight (#54).

    The old code *overwrote* history with the in-run mean the moment a single
    pair completed, so one unrepresentative pair threw the whole estimate. Here
    the in-run model earns its weight: ``observed_n / (observed_n +
    history_weight)``. With no base, the observation is taken as-is.
    """
    if observed is None or observed_n <= 0:
        return base
    if base is None:
        return observed
    weight = observed_n / (observed_n + max(history_weight, 0.0))
    return (
        base[0] * (1.0 - weight) + observed[0] * weight,
        base[1] * (1.0 - weight) + observed[1] * weight,
    )


def pair_cost_ms(module: str, size_bytes: int, costs: Mapping[str, CostModel]) -> float:
    """Cost in ms of one ``(thesis x module)`` pair under ``costs``, falling back
    to this module's ADR-0015 prior when it has no usable model."""
    model = costs.get(module)
    size = max(float(size_bytes), 0.0)
    if model is not None:
        cost = model[0] + model[1] * size
        if cost > 0:
            return cost
    intercept, slope = prior_cost(module)
    return intercept + slope * size


def estimate(
    done: int,
    total: int,
    remaining: Sequence[tuple[int, str, int]],
    costs: Mapping[str, CostModel],
    *,
    in_flight: Mapping[tuple[int, str], float] | None = None,
    workers: int = 1,
    theses_total: int = 0,
    theses_done: int = 0,
    thesis_floors: Mapping[int, float] | None = None,
    startup_ms: float = 0.0,
) -> Progress:
    """Determinate-bar fraction plus a size-weighted, parallelism-aware ETA.

    Args:
        done: ``(thesis x module)`` pairs completed so far in the run.
        total: total pairs planned for the run.
        remaining: the not-yet-done pairs, each
            ``(thesis_id, module_name, thesis_size_bytes)``. The thesis id is
            required: modules within a thesis are serial, so cost has to be
            bucketed per thesis before parallelism is applied.
        costs: per-module ``(intercept_ms, slope_ms_per_byte)`` - history
            blended with in-run observations by the caller. A module missing
            here uses its ADR-0015 prior.
        in_flight: ``(thesis_id, module_name) -> seconds already elapsed`` for
            the pairs currently running. These pairs are still in ``remaining``;
            their contribution is reduced by the elapsed time (floored at zero),
            which is what makes the estimate decay between events.
        workers: the runner's concurrent-thesis count (``Runner.workers``).
        theses_total: theses planned for the run - ``len(plan.theses)`` (#58).
        thesis_floors: ``thesis_id -> minimum remaining ms`` for theses known
            to misbehave - in practice the longest timeout recorded against
            each (``Repository.thesis_cost_floors``, #56). A thesis that timed
            out contributes nothing to the cost fit, which uses successful runs
            only, so without this the next run under-estimates it exactly as
            badly. Applied per thesis, never per module: a hang is a property
            of the one document that hung.
        startup_ms: worker start-up still ahead of the run, in ms (#86). Long-
            lived workers pay the library start-up once each, and in parallel,
            so it is added **once** to the makespan rather than per thesis. The
            caller passes ``WORKER_STARTUP_MS`` minus the run's elapsed time,
            so the term counts down to zero early in the run.
        theses_done: theses the caller has *seen* complete. The estimator also
            derives completion from ``remaining``, and reports the larger of the
            two, so it stays correct on its own if a thesis is killed without
            its pairs ever reporting, and correct too if the caller counts
            nothing.

    ETA rules:
        - No remaining pairs -> ``0.0`` seconds.
        - No evidence at all (no ``costs``, nothing done, nothing in flight) ->
          ``None``, so the caller shows "estimating..." while the bar advances.
        - Otherwise the makespan bound over the remaining per-thesis costs:
          ``max(total / min(workers, remaining theses), largest thesis)``,
          plus the remaining one-off worker start-up (``startup_ms``).
    """
    in_flight = in_flight or {}
    fraction = 0.0 if total <= 0 else max(0.0, min(1.0, done / total))
    remaining_theses = {thesis_id for thesis_id, _, _ in remaining}

    theses_seen = max(theses_done, 0)
    if theses_total > 0:
        theses_seen = min(max(theses_seen, theses_total - len(remaining_theses)), theses_total)
    else:
        theses_seen = 0

    def _progress(eta: float | None) -> Progress:
        return Progress(
            fraction=fraction,
            eta_seconds=eta,
            done=done,
            total=total,
            theses_done=theses_seen,
            theses_total=max(theses_total, 0),
        )

    if not remaining:
        return _progress(0.0)
    if not costs and done <= 0 and not in_flight:
        return _progress(None)

    # Bucket remaining cost per thesis: modules within a thesis are serial
    # (runner.py), so a thesis's own bucket is a lower bound on the wall clock.
    per_thesis: dict[int, float] = {}
    for thesis_id, module, size in remaining:
        cost = pair_cost_ms(module, size, costs)
        credit = max(in_flight.get((thesis_id, module), 0.0), 0.0) * 1000.0
        per_thesis[thesis_id] = per_thesis.get(thesis_id, 0.0) + max(cost - credit, 0.0)

    # A thesis that previously timed out is floored at that timeout (#56): its
    # own history says it misbehaves, but the timed-out run is excluded from the
    # cost fit, so the model alone would price it as if nothing had happened.
    for thesis_id, floor_ms in (thesis_floors or {}).items():
        if thesis_id in per_thesis:
            per_thesis[thesis_id] = max(per_thesis[thesis_id], max(floor_ms, 0.0))

    divisor = max(1, min(max(workers, 1), len(per_thesis)))
    eta_ms = max(sum(per_thesis.values()) / divisor, max(per_thesis.values()))
    eta_ms += max(startup_ms, 0.0)
    return _progress(eta_ms / 1000.0)


def damp_eta(
    previous: float | None, current: float | None, *, rise_factor: float = RISE_FACTOR
) -> float | None:
    """Smooth successive estimates so the label reads as a countdown (#54).

    A *fall* is shown immediately - a countdown is allowed to drop. A *rise* is
    eased in at ``rise_factor`` of the gap per call, so a module landing with a
    dearer-than-expected cost nudges the number up over the next few poll ticks
    instead of yanking it. Called at the adapter's poll rate; at 100 ms ticks the
    default factor settles a jump in well under a second.
    """
    if current is None:
        return None
    if previous is None or current <= previous:
        return current
    factor = min(max(rise_factor, 0.0), 1.0)
    return previous + factor * (current - previous)


def format_eta(seconds: float | None) -> str:
    """Compact human ETA for a progress label; ``None`` -> 'estimating...'.

    The unit letters stay ASCII and untranslated - "5m 03s" reads the same in
    German - but the placeholder is prose and goes through the catalog."""
    if seconds is None:
        return _("estimating...")
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
