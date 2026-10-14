"""Run-progress label and in-run cost accounting - no Tk widget (#54, #58).

``MainWindow._progress_text`` / ``_merged_costs`` / ``_thesis_ordinal`` are
called unbound against a tiny stub, so this runs headless: importing tkinter
needs no display, only instantiating ``Tk()`` does (ADR-0002 invariant 6).
"""

from tta.core import progress
from tta.ui.tk.main_window import MainWindow


class _Flag:
    """Stand-in for the ``tk.BooleanVar`` behind Extended mode."""

    def __init__(self, value: bool) -> None:
        self._value = value

    def get(self) -> bool:
        return self._value


class _Stub:
    def __init__(self, extended: bool = False) -> None:
        self._extended = _Flag(extended)
        self._run_costs: dict[str, tuple[float, float]] = {}
        self._run_obs: dict[str, list[tuple[float, float]]] = {}
        self._run_thesis_ordinals: dict[int, int] = {}
        self._run_theses_total = 0


def _est(**kwargs) -> progress.Progress:
    defaults = dict(
        fraction=0.5, eta_seconds=90.0, done=6, total=24, theses_done=1, theses_total=4
    )
    defaults.update(kwargs)
    return progress.Progress(**defaults)


def test_basic_mode_label_leads_with_theses_not_pairs():
    """#58: "(thesis x module) pairs" means nothing to the professor persona."""
    text = MainWindow._progress_text(_Stub(extended=False), _est(), 90.0)
    assert text == "thesis 1/4 - ~1m 30s left"
    assert "pair" not in text


def test_extended_mode_appends_the_pair_count():
    text = MainWindow._progress_text(_Stub(extended=True), _est(), 90.0)
    assert text == "thesis 1/4 - ~1m 30s left - 6/24 pairs"


def test_label_says_estimating_while_the_eta_is_unknown():
    assert MainWindow._progress_text(_Stub(), _est(eta_seconds=None), None) == (
        "thesis 1/4 - estimating..."
    )


def test_label_uses_the_damped_eta_not_the_raw_one():
    """The label renders the damped value the caller passes, so a raw estimate
    that jumps does not yank the number (#54)."""
    text = MainWindow._progress_text(_Stub(), _est(eta_seconds=600.0), 90.0)
    assert text == "thesis 1/4 - ~1m 30s left"


def test_label_is_empty_with_nothing_planned():
    assert MainWindow._progress_text(_Stub(), _est(total=0), 0.0) == ""


def test_label_falls_back_to_pairs_without_a_thesis_total():
    text = MainWindow._progress_text(_Stub(), _est(theses_total=0, theses_done=0), 30.0)
    assert text == "6/24 pairs - ~30s left"


def test_thesis_ordinal_replaces_the_raw_primary_key():
    """The status line printed ``thesis {thesis_id}`` - a DB primary key that
    reads like a counter without being one after any delete or dedup fold."""
    stub = _Stub()
    stub._run_thesis_ordinals = {7: 1, 3: 2, 9: 3}
    stub._run_theses_total = 3
    assert MainWindow._thesis_ordinal(stub, 3) == "2/3"
    # a thesis outside the plan (or no plan) degrades to a marked raw id
    assert MainWindow._thesis_ordinal(stub, 42) == "#42"


def test_merged_costs_blends_observations_into_history_by_weight():
    """#54: the old ``_merged_rates`` overwrote history with the in-run mean
    ms/byte the moment one pair landed."""
    stub = _Stub()
    stub._run_costs = {"mod_a": (100.0, 1.0)}
    stub._run_obs = {"mod_a": [(100.0, 400.0)]}  # one sample -> (400, 0)
    intercept, slope = MainWindow._merged_costs(stub)["mod_a"]
    assert 100.0 < intercept < 400.0  # history still pulls, it was not replaced
    assert 0.0 < slope < 1.0


class _RunStub(_Stub):
    """Enough run state for ``_advance_progress`` without a Tk widget."""

    def __init__(self) -> None:
        super().__init__()
        self._run_remaining = [(1, "mod_a"), (2, "mod_a")]
        self._run_in_flight = {}
        self._run_done = 0
        self._run_sizes = {1: 1000, 2: 1000}
        self._run_cold = {1}
        self._run_started = None
        self._progress_bar = None

    def _render_progress(self) -> None:
        pass


def test_a_fresh_workers_first_thesis_stays_out_of_the_in_run_fit():
    """#86: the first ``workers`` theses run on fresh workers and carry the
    library start-up inside their module timers; it is modelled separately,
    so their durations must not inflate the per-thesis fit."""
    from tta.core import events

    stub = _RunStub()
    MainWindow._advance_progress(stub, events.ModuleCompleted(1, "mod_a", "ok", 3000))
    assert stub._run_obs == {}  # cold: counted as done, not as a cost sample
    assert stub._run_done == 1
    MainWindow._advance_progress(stub, events.ModuleCompleted(2, "mod_a", "ok", 100))
    assert stub._run_obs == {"mod_a": [(1000.0, 100.0)]}


def test_start_up_term_counts_down_with_the_run():
    stub = _RunStub()
    assert MainWindow._startup_ahead_ms(stub, 50.0) == 0.0  # no run started
    stub._run_started = 100.0
    assert MainWindow._startup_ahead_ms(stub, 100.0) == progress.WORKER_STARTUP_MS
    assert MainWindow._startup_ahead_ms(stub, 101.0) == progress.WORKER_STARTUP_MS - 1000.0
    assert MainWindow._startup_ahead_ms(stub, 200.0) == 0.0


def test_merged_costs_leaves_unseen_modules_absent_for_the_prior():
    stub = _Stub()
    stub._run_costs = {"mod_a": (100.0, 1.0)}
    assert "mod_b" not in MainWindow._merged_costs(stub)
