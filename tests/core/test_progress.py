"""Pure size-weighted progress/ETA estimator tests (tta.core.progress, #39).

No Tk: the estimator is toolkit-free by design (hard invariant 3), so this
exercises it directly with numbers.
"""

import pytest

from tta.core import progress


def test_fraction_is_done_over_total_and_clamped():
    assert progress.estimate(0, 4, [("m", 10)], {}).fraction == 0.0
    assert progress.estimate(2, 4, [("m", 10)], {"m": 1.0}).fraction == 0.5
    assert progress.estimate(4, 4, [], {}).fraction == 1.0
    # degenerate totals never divide by zero or exceed [0, 1]
    assert progress.estimate(0, 0, [], {}).fraction == 0.0
    assert progress.estimate(5, 4, [], {}).fraction == 1.0


def test_no_remaining_pairs_is_zero_eta():
    est = progress.estimate(4, 4, [], {"m": 2.0})
    assert est.eta_seconds == 0.0
    assert est.done == 4 and est.total == 4


def test_eta_is_size_weighted_sum_over_pairs():
    """ETA = sum(rate[module] * size) / 1000. Two pairs, one module at
    2 ms/byte: 100B + 50B -> (200 + 100) ms -> 0.3 s."""
    est = progress.estimate(
        done=1, total=3, remaining=[("mod_a", 100), ("mod_a", 50)], rates={"mod_a": 2.0}
    )
    assert est.eta_seconds == pytest.approx(0.3)


def test_bigger_remaining_theses_give_a_longer_eta():
    """The explicit requirement: size matters, not just the pair count."""
    rates = {"mod_a": 1.0}
    small = progress.estimate(1, 3, [("mod_a", 10), ("mod_a", 10)], rates).eta_seconds
    large = progress.estimate(1, 3, [("mod_a", 10), ("mod_a", 1000)], rates).eta_seconds
    assert large > small
    # same pair COUNT, only the size differs -> the estimate must differ
    assert small == pytest.approx((10 + 10) / 1000)
    assert large == pytest.approx((10 + 1000) / 1000)


def test_module_without_its_own_rate_uses_mean_of_known_rates():
    """A remaining module absent from `rates` borrows the mean of known rates."""
    rates = {"mod_a": 2.0, "mod_b": 4.0}  # mean 3.0 ms/byte
    est = progress.estimate(1, 2, [("mod_c", 100)], rates)  # mod_c unknown
    assert est.eta_seconds == pytest.approx(3.0 * 100 / 1000)


def test_before_any_data_no_eta_but_bar_still_advances():
    """First run, no history, nothing observed yet: fraction is real but ETA is
    None so the caller shows 'estimating...'."""
    est = progress.estimate(done=0, total=5, remaining=[("mod_a", 100)], rates={})
    assert est.eta_seconds is None
    assert est.fraction == 0.0


def test_observed_in_run_rate_enables_the_estimate():
    """Once a module's in-run rate is known (caller merges it into `rates`), the
    size-weighted ETA is produced for the remaining pairs."""
    est = progress.estimate(
        done=1, total=3, remaining=[("mod_a", 200), ("mod_a", 200)], rates={"mod_a": 0.5}
    )
    assert est.eta_seconds == pytest.approx((0.5 * 200 * 2) / 1000)


def test_count_proportional_elapsed_fallback_when_no_rates():
    """No rate anywhere but some pairs done and time elapsed: fall back to a
    count-proportional estimate from elapsed time (elapsed * remaining/done)."""
    est = progress.estimate(
        done=2, total=5, remaining=[("m", 0), ("m", 0), ("m", 0)], rates={}, elapsed_s=10.0
    )
    assert est.eta_seconds == pytest.approx(10.0 * 3 / 2)


def test_zero_sizes_with_known_rate_fall_through_to_elapsed():
    """Known rate but all remaining sizes are 0 -> size sum is 0, so use the
    elapsed count-proportional fallback rather than reporting 0 s left."""
    est = progress.estimate(
        done=1, total=3, remaining=[("m", 0), ("m", 0)], rates={"m": 2.0}, elapsed_s=6.0
    )
    assert est.eta_seconds == pytest.approx(6.0 * 2 / 1)


def test_format_eta():
    assert progress.format_eta(None) == "estimating..."
    assert progress.format_eta(0) == "0s"
    assert progress.format_eta(45.4) == "45s"
    assert progress.format_eta(80) == "1m 20s"
    assert progress.format_eta(3725) == "1h 02m"
