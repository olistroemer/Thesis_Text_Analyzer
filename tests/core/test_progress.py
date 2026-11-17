"""Pure progress/ETA estimator tests (tta.core.progress; #39, #54, #58).

No Tk: the estimator is toolkit-free by design (ADR-0002), so this exercises it
directly with numbers. It also never reads the clock - wall-clock elapsed and
the worker count are arguments - so every case below is deterministic.
"""

import pytest

from tta.core import progress

NOMINAL = progress.PRIOR_THESIS_BYTES


def _flat(module: str, ms: float) -> tuple[float, float]:
    """A size-independent cost model of ``ms`` per pair, for readable maths."""
    return (ms, 0.0)


# -- fraction and terminal states -------------------------------------------


def test_fraction_is_done_over_total_and_clamped():
    assert progress.estimate(0, 4, [(1, "m", 10)], {}).fraction == 0.0
    assert progress.estimate(2, 4, [(1, "m", 10)], {"m": _flat("m", 1)}).fraction == 0.5
    assert progress.estimate(4, 4, [], {}).fraction == 1.0
    # degenerate totals never divide by zero or exceed [0, 1]
    assert progress.estimate(0, 0, [], {}).fraction == 0.0
    assert progress.estimate(5, 4, [], {}).fraction == 1.0


def test_no_remaining_pairs_is_zero_eta():
    est = progress.estimate(4, 4, [], {"m": _flat("m", 2000)})
    assert est.eta_seconds == 0.0
    assert est.done == 4 and est.total == 4


def test_before_any_evidence_no_eta_but_bar_still_advances():
    """No history, nothing done, nothing running: the fraction is real but the
    ETA is None so the caller shows 'estimating...'."""
    est = progress.estimate(done=0, total=5, remaining=[(1, "mod_a", 100)], costs={})
    assert est.eta_seconds is None
    assert est.fraction == 0.0


def test_a_pair_in_flight_is_enough_evidence_for_a_prior_estimate():
    """Once the run is actually running, the measured priors give a number - the
    label does not sit on 'estimating...' waiting for the first completion."""
    est = progress.estimate(
        0, 5, [(1, "mod_tokenize", NOMINAL)], {}, in_flight={(1, "mod_tokenize"): 0.0}
    )
    assert est.eta_seconds == pytest.approx(progress.MODULE_PRIOR_MS["mod_tokenize"] / 1000)


# -- affine cost model (#54 defect 3) ---------------------------------------


def test_eta_uses_intercept_plus_slope_not_a_pure_rate():
    """cost = intercept_ms + slope*size. Two pairs, one module at
    (100 ms + 2 ms/byte): 100B -> 300 ms, 50B -> 200 ms, serial -> 0.5 s."""
    est = progress.estimate(
        done=1,
        total=3,
        remaining=[(1, "mod_a", 100), (1, "mod_a", 50)],
        costs={"mod_a": (100.0, 2.0)},
    )
    assert est.eta_seconds == pytest.approx(0.5)


def test_bigger_remaining_theses_give_a_longer_eta():
    """The explicit #39 requirement: size matters, not just the pair count."""
    costs = {"mod_a": (0.0, 1.0)}  # 1 ms/byte, no constant part
    pairs_small = [(1, "mod_a", 10), (2, "mod_a", 10)]
    pairs_large = [(1, "mod_a", 10), (2, "mod_a", 1000)]
    small = progress.estimate(1, 3, pairs_small, costs, workers=1).eta_seconds
    large = progress.estimate(1, 3, pairs_large, costs, workers=1).eta_seconds
    assert large > small
    # same pair COUNT, only the size differs -> the estimate must differ
    assert small == pytest.approx((10 + 10) / 1000)
    assert large == pytest.approx((10 + 1000) / 1000)
    # on two workers the big thesis is the critical path, the small one is free
    assert progress.estimate(1, 3, pairs_large, costs, workers=2).eta_seconds == pytest.approx(1.0)


def test_unknown_module_uses_its_own_prior_not_the_mean_of_known_rates():
    """#54 defect 3: on a first run only the extractor has reported, and the old
    mean-of-known-rates fallback priced every other module at the extractor's
    rate - the visible 'grossly inflated' ETA. Each module gets its own
    measured prior instead (#86)."""
    extractor = {"mod_extract_pymupdf": (0.0, 6000.0 / NOMINAL)}  # 6 s at nominal size
    est = progress.estimate(1, 2, [(1, "mod_surface_counts", NOMINAL)], extractor)
    assert est.eta_seconds == pytest.approx(
        progress.MODULE_PRIOR_MS["mod_surface_counts"] / 1000
    )
    assert est.eta_seconds < 6.0  # not priced at the extractor's rate


def test_zero_or_degenerate_cost_model_falls_back_to_the_prior():
    """A model that prices a pair at zero is unusable; the prior is used."""
    est = progress.estimate(1, 2, [(1, "mod_tokenize", 0)], {"mod_tokenize": (0.0, 0.0)})
    assert est.eta_seconds == pytest.approx(progress.prior_cost("mod_tokenize")[0] / 1000)


def test_prior_cost_reproduces_the_measured_prior_at_nominal_size():
    intercept, slope = progress.prior_cost("mod_tokenize")
    assert intercept + slope * NOMINAL == pytest.approx(progress.MODULE_PRIOR_MS["mod_tokenize"])
    assert intercept > 0 and slope > 0  # split, so a huge PDF is not free either
    # a module absent from the table gets the documented default
    unknown = progress.prior_cost("mod_not_in_the_table")
    assert unknown[0] + unknown[1] * NOMINAL == pytest.approx(progress.DEFAULT_PRIOR_MS)


def test_priors_cover_the_catalogue_and_describe_a_warm_worker():
    """#86: the priors are a reused worker's per-thesis cost (~0.83 s in sum
    on the reference machine), no longer ADR-0015's ceilings (15 s), which
    contained the per-thesis library start-up."""
    from tta.core.modules.registry import default_registry

    names = {m.spec.name for m in default_registry().in_topological_order(None)}
    assert names <= set(progress.MODULE_PRIOR_MS)
    assert 500.0 < sum(progress.MODULE_PRIOR_MS.values()) < 2000.0


def test_worker_start_up_is_added_once_not_per_thesis():
    """Long-lived workers pay the library start-up once each, in parallel
    (#86): the makespan grows by the start-up once, whatever the worker or
    thesis count, and not at all once it is spent."""
    costs = {"mod_a": (1000.0, 0.0)}
    remaining = [(tid, "mod_a", NOMINAL) for tid in range(1, 9)]  # 8 theses x 1 s
    base = progress.estimate(0, 8, remaining, costs, workers=4)
    started = progress.estimate(
        0, 8, remaining, costs, workers=4, startup_ms=progress.WORKER_STARTUP_MS
    )
    assert base.eta_seconds == pytest.approx(2.0)
    assert started.eta_seconds == pytest.approx(2.0 + progress.WORKER_STARTUP_MS / 1000)
    spent = progress.estimate(0, 8, remaining, costs, workers=4, startup_ms=-5.0)
    assert spent.eta_seconds == pytest.approx(2.0)
    # nothing left: no start-up is owed either
    assert progress.estimate(8, 8, [], costs, startup_ms=2600.0).eta_seconds == 0.0


# -- parallelism (#54 defect 2) ---------------------------------------------


def test_eta_divides_remaining_work_by_the_worker_count():
    """Four independent theses of 1 s each finish in ~1 s on four workers, not
    4 s. The old estimator summed every remaining pair serially and so ran ~N x
    too high at the start of a batch."""
    remaining = [(tid, "mod_a", 0) for tid in (1, 2, 3, 4)]
    costs = {"mod_a": _flat("mod_a", 1000)}
    assert progress.estimate(0, 4, remaining, costs, workers=1).eta_seconds == pytest.approx(4.0)
    assert progress.estimate(0, 4, remaining, costs, workers=4).eta_seconds == pytest.approx(1.0)
    assert progress.estimate(0, 4, remaining, costs, workers=8).eta_seconds == pytest.approx(1.0)


def test_tail_of_a_run_does_not_underestimate():
    """One thesis left on eight workers still takes its own full time: the
    divisor is min(workers, remaining theses), not workers flat."""
    est = progress.estimate(
        3, 4, [(7, "mod_a", 0)], {"mod_a": _flat("mod_a", 1000)}, workers=8
    )
    assert est.eta_seconds == pytest.approx(1.0)


def test_a_single_long_thesis_sets_the_critical_path_floor():
    """Modules within a thesis are serial, so the run cannot finish before the
    longest remaining thesis does, however many workers are idle."""
    remaining = [(1, "mod_a", 0), (1, "mod_a", 0), (1, "mod_a", 0), (1, "mod_a", 0)]
    remaining.append((2, "mod_b", 0))
    costs = {"mod_a": _flat("mod_a", 1000), "mod_b": _flat("mod_b", 100)}
    est = progress.estimate(0, 5, remaining, costs, workers=4)
    # total 4100 ms / min(4, 2 theses) = 2050 ms, but thesis 1 alone needs 4 s
    assert est.eta_seconds == pytest.approx(4.0)


# -- it counts down (#54 defect 1) -----------------------------------------


def test_in_flight_elapsed_is_credited_against_the_pairs_cost():
    remaining = [(1, "mod_a", 0)]
    costs = {"mod_a": _flat("mod_a", 1000)}
    fresh = progress.estimate(0, 1, remaining, costs, in_flight={(1, "mod_a"): 0.0})
    part = progress.estimate(0, 1, remaining, costs, in_flight={(1, "mod_a"): 0.4})
    assert fresh.eta_seconds == pytest.approx(1.0)
    assert part.eta_seconds == pytest.approx(0.6)


def test_in_flight_credit_is_floored_at_the_pairs_own_cost():
    """A pair overrunning its estimate must not drive the ETA negative, nor
    subtract from the other theses' remaining work."""
    est = progress.estimate(
        0,
        2,
        [(1, "mod_a", 0), (2, "mod_a", 0)],
        {"mod_a": _flat("mod_a", 1000)},
        in_flight={(1, "mod_a"): 60.0},
        workers=1,
    )
    assert est.eta_seconds == pytest.approx(1.0)  # thesis 1 floored at 0, thesis 2 unchanged


def test_the_estimate_strictly_decays_between_events():
    """The defect: the ETA was a function of the remaining pair set only, so it
    was frozen between ModuleCompleted events and could not count down."""
    remaining = [(1, "mod_a", 0), (2, "mod_a", 0)]
    costs = {"mod_a": _flat("mod_a", 5000)}
    etas = [
        progress.estimate(
            0, 2, remaining, costs, in_flight={(1, "mod_a"): t, (2, "mod_a"): t}, workers=2
        ).eta_seconds
        for t in (0.0, 1.0, 2.0, 3.0)
    ]
    assert etas == sorted(etas, reverse=True)
    assert etas[0] > etas[-1]


def test_damp_eta_shows_falls_at_once_and_eases_rises():
    assert progress.damp_eta(None, 30.0) == 30.0
    assert progress.damp_eta(30.0, None) is None
    assert progress.damp_eta(30.0, 20.0) == 20.0  # a countdown may drop freely
    assert progress.damp_eta(30.0, 50.0, rise_factor=0.25) == pytest.approx(35.0)
    assert progress.damp_eta(30.0, 50.0, rise_factor=1.0) == pytest.approx(50.0)


def test_damp_eta_converges_on_a_rise():
    value = 10.0
    for _ in range(40):
        value = progress.damp_eta(value, 20.0)
    assert value == pytest.approx(20.0, abs=0.01)


# -- fitting and blending cost models (#54 defect 3) -----------------------


def test_fit_cost_recovers_a_clean_affine_line():
    model = progress.fit_cost([(100, 300.0), (200, 500.0), (400, 900.0)])
    assert model[0] == pytest.approx(100.0)
    assert model[1] == pytest.approx(2.0)


def test_fit_cost_with_no_samples_is_none():
    assert progress.fit_cost([]) is None


def test_fit_cost_with_one_distinct_size_is_intercept_only():
    """One size says nothing about size dependence. Reading it as a rate is how
    a single small thesis inflated every large one still queued (#54)."""
    assert progress.fit_cost([(100, 200.0)]) == pytest.approx((200.0, 0.0))
    assert progress.fit_cost([(100, 200.0), (100, 400.0)]) == pytest.approx((300.0, 0.0))


def test_fit_cost_never_returns_negative_coefficients():
    # cheaper on a bigger PDF -> noise; degrade to a constant
    assert progress.fit_cost([(100, 500.0), (200, 100.0)]) == pytest.approx((300.0, 0.0))
    # a fit implying negative cost at zero bytes -> line through the origin
    intercept, slope = progress.fit_cost([(100, 200.0), (50, 50.0)])
    assert intercept == 0.0
    assert slope == pytest.approx(1.8)


def test_blend_cost_weights_in_run_observations_against_history():
    """The old code overwrote history with the in-run mean as soon as one pair
    landed; now the observation has to earn its weight."""
    blended = progress.blend_cost((100.0, 1.0), (200.0, 2.0), 3, history_weight=3.0)
    assert blended == pytest.approx((150.0, 1.5))  # weight 3/(3+3) = 0.5
    one = progress.blend_cost((100.0, 1.0), (200.0, 2.0), 1, history_weight=3.0)
    assert one[0] == pytest.approx(125.0)  # weight 1/4: history still dominates


def test_blend_cost_degenerate_inputs():
    assert progress.blend_cost((1.0, 2.0), None, 0) == (1.0, 2.0)
    assert progress.blend_cost((1.0, 2.0), (9.0, 9.0), 0) == (1.0, 2.0)
    assert progress.blend_cost(None, (9.0, 9.0), 2) == (9.0, 9.0)
    assert progress.blend_cost(None, None, 2) is None


# -- n/N theses (#58) ------------------------------------------------------


def test_theses_done_is_derived_from_the_remaining_pairs():
    """Self-sufficient: the estimator needs no thesis-completion event to know
    how many theses are done."""
    est = progress.estimate(
        4, 9, [(2, "mod_a", 0), (2, "mod_b", 0), (3, "mod_a", 0)], {}, theses_total=3
    )
    assert (est.theses_done, est.theses_total) == (1, 3)


def test_theses_done_takes_the_callers_count_when_it_is_ahead():
    """A thesis killed without its pairs ever reporting would leave the derived
    count stuck; the caller's ThesisCompleted tally wins in that case."""
    est = progress.estimate(
        2, 9, [(2, "mod_a", 0), (3, "mod_a", 0)], {}, theses_total=3, theses_done=2
    )
    assert est.theses_done == 2


def test_theses_done_is_clamped_to_the_total():
    est = progress.estimate(9, 9, [], {}, theses_total=3, theses_done=99)
    assert (est.theses_done, est.theses_total) == (3, 3)


def test_theses_counts_default_to_zero_when_the_caller_gives_no_total():
    est = progress.estimate(1, 2, [(1, "mod_a", 0)], {}, theses_done=5)
    assert (est.theses_done, est.theses_total) == (0, 0)


def test_all_theses_done_when_nothing_remains():
    est = progress.estimate(9, 9, [], {}, theses_total=4)
    assert (est.theses_done, est.theses_total) == (4, 4)


# -- formatting ------------------------------------------------------------


def test_format_eta():
    assert progress.format_eta(None) == "estimating..."
    assert progress.format_eta(0) == "0s"
    assert progress.format_eta(45.4) == "45s"
    assert progress.format_eta(80) == "1m 20s"
    assert progress.format_eta(3725) == "1h 02m"


def test_a_timed_out_thesis_is_floored_at_its_timeout():
    """#56: a thesis that timed out is not estimated as if it had not.

    The timed-out run is excluded from the cost fit (successful runs only), so
    without a floor the model prices this thesis at its cheap nominal cost and
    under-estimates it exactly as badly as the run before.
    """
    remaining = [(1, "mod_a", 1_000), (2, "mod_a", 1_000)]
    costs = {"mod_a": (100.0, 0.0)}  # 100 ms per pair

    plain = progress.estimate(0, 2, remaining, costs, workers=1)
    floored = progress.estimate(
        0, 2, remaining, costs, workers=1, thesis_floors={1: 300_000.0}
    )

    assert plain.eta_seconds == pytest.approx(0.2)  # 2 x 100 ms, serial
    # thesis 1 is floored at 300 s, which then dominates the makespan bound
    assert floored.eta_seconds == pytest.approx(300.1)


def test_the_floor_is_per_thesis_not_per_module():
    """The floor must not leak onto other theses running the same module."""
    remaining = [(1, "mod_a", 1_000), (2, "mod_a", 1_000)]
    costs = {"mod_a": (100.0, 0.0)}
    est = progress.estimate(
        0, 2, remaining, costs, workers=2, thesis_floors={1: 60_000.0}
    )
    # thesis 2 keeps its 100 ms; the makespan is thesis 1's floor, not 2 x 60 s
    assert est.eta_seconds == pytest.approx(60.0)


def test_a_floor_below_the_modelled_cost_changes_nothing():
    remaining = [(1, "mod_a", 1_000)]
    costs = {"mod_a": (5_000.0, 0.0)}
    est = progress.estimate(0, 1, remaining, costs, thesis_floors={1: 10.0})
    assert est.eta_seconds == pytest.approx(5.0)


def test_a_floor_for_a_finished_thesis_is_ignored():
    """Only theses with remaining work can be floored."""
    remaining = [(2, "mod_a", 1_000)]
    costs = {"mod_a": (100.0, 0.0)}
    est = progress.estimate(1, 2, remaining, costs, thesis_floors={1: 300_000.0})
    assert est.eta_seconds == pytest.approx(0.1)
