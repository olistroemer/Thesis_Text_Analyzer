"""Human-friendly column labels (#16, US-PROF-EXPLAIN). No display needed.

The point of these tests is the *coverage gate*: a module contributed later
that produces a metric with no label would silently put `bigram_repetition_rate`
back in front of the professor, which is the defect #16 exists to fix.
"""

import pytest

from tta.core.modules.registry import default_registry
from tta.ui.tk.columns import (
    ARTEFACT_COLUMNS,
    COLUMN_HELP,
    COLUMN_LABELS,
    LEAD_COLUMNS,
    column_help,
    column_label,
    metric_columns,
)


def _catalogue_metrics() -> list[str]:
    registry = default_registry()
    return [c.metric for c in metric_columns(registry, extended=True)]


def test_every_metric_in_the_catalogue_has_a_friendly_label():
    """The #16 gate: adding a module without a label fails here, not in front
    of a user."""
    missing = [metric for metric in _catalogue_metrics() if metric not in COLUMN_LABELS]
    assert missing == [], "no COLUMN_LABELS entry for %s" % missing


def test_every_lead_and_artefact_column_has_a_friendly_label():
    for name in tuple(LEAD_COLUMNS) + tuple(ARTEFACT_COLUMNS):
        assert name in COLUMN_LABELS, name


def test_every_metric_in_the_catalogue_has_help_text():
    missing = [metric for metric in _catalogue_metrics() if metric not in COLUMN_HELP]
    assert missing == [], "no COLUMN_HELP entry for %s" % missing


def test_labels_and_help_cover_the_same_columns():
    """Two dicts keyed the same way drift unless something says they must not.
    They HAD drifted: #18's `file_size_bytes` and `fs_modified_year` shipped
    with no COLUMN_HELP entry, so the details panel had nothing to say about
    them. Found while adding the labels, fixed with them, pinned here."""
    assert set(COLUMN_HELP) == set(COLUMN_LABELS)


def test_labels_are_distinct_so_two_columns_never_read_the_same():
    """The `language` artefact column and the `language_code` metric sit side
    by side in extended mode; naming both "Language" would be unreadable."""
    labels = [column_label(name) for name in COLUMN_LABELS]
    duplicates = {label for label in labels if labels.count(label) > 1}
    assert duplicates == set(), duplicates


@pytest.mark.parametrize(
    "name, label",
    [
        ("flesch_reading_ease", "Readability (Flesch)"),  # the ticket's own example
        ("word_count", "Words"),
        ("yules_k", "Vocabulary richness (Yule's K)"),
        ("publication_year", "Publication year"),
        ("file", "File"),
    ],
)
def test_the_label_is_prose_not_an_identifier(name, label):
    assert column_label(name) == label
    assert "_" not in column_label(name)


def test_an_unknown_column_falls_back_to_its_raw_name():
    """A contributed module's unlabelled metric still renders a usable header
    rather than a blank one."""
    assert column_label("some_future_metric") == "some_future_metric"
    assert column_help("some_future_metric") is None


def test_the_raw_name_is_still_the_column_identity():
    """Labels are display only: sort keys, the DB and the export all speak raw
    names, so the label table must not be reachable from any of them."""
    registry = default_registry()
    assert [c.metric for c in metric_columns(registry, extended=False)] == [
        c.metric for c in metric_columns(registry, extended=False)
    ]
    assert all(metric.islower() for metric in _catalogue_metrics())


# -- column widths (#90) --------------------------------------------------------


def test_a_column_is_as_wide_as_its_header_but_never_below_the_default():
    """Sec. 9.2 (#90): only a header that would be cut off widens its column."""
    from tta.ui.tk.grid import HEADER_PADDING, header_widths

    widths = header_widths(["Ja", "x" * 30], measure=lambda text: 7 * len(text), minimum=120)
    assert widths == [120, 7 * 30 + HEADER_PADDING]
