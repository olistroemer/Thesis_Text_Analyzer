"""Reference aggregates (ADR-0025): statistics, threshold, buckets, format,
the highlight rule, and the shipped file itself."""

import json
import statistics

import pytest

from tta.core import reference
from tta.core.reference import ALL, ReferenceThesis


def _thesis(value, *, thesis_type="bachelor", language="de", field="300", year=2015,
            metric="word_count"):
    return ReferenceThesis(thesis_type, language, field, year, {metric: float(value)})


def _build(theses, **kwargs):
    return reference.build_aggregates(
        theses, status="interim", source="test", generated="2026-11-18",
        generator="test", **kwargs,
    )


def _rows(document):
    return {(r["type"], r["language"], r["field"], r["year"]): r["values"]
            for r in document["rows"]}


# -- statistics ---------------------------------------------------------------


def test_quantile_matches_statistics_inclusive():
    series = sorted([3.0, 5.0, 5.0, 6.0, 7.0, 8.0, 8.0, 9.0, 12.0, 40.0, -20.0])
    q1, median, q3 = statistics.quantiles(series, n=4, method="inclusive")
    cuts = statistics.quantiles(series, n=20, method="inclusive")
    assert reference.quantile(series, 0.25) == pytest.approx(q1)
    assert reference.quantile(series, 0.5) == pytest.approx(median)
    assert reference.quantile(series, 0.75) == pytest.approx(q3)
    assert reference.quantile(series, 0.05) == pytest.approx(cuts[0])
    assert reference.quantile(series, 0.95) == pytest.approx(cuts[-1])


def test_quantile_matches_numpy():
    numpy = pytest.importorskip("numpy")
    series = sorted([0.5, 1.25, 1.25, 3.0, 7.75, 9.0, 9.0, 12.5, 30.0, 31.0])
    for fraction in (0.05, 0.25, 0.5, 0.75, 0.95):
        assert reference.quantile(series, fraction) == pytest.approx(
            float(numpy.quantile(series, fraction))
        )


def test_summarise_gives_the_six_statistics_in_order():
    values = list(range(1, 21))  # 1..20
    mean, median, p05, p25, p75, p95 = reference.summarise(values)
    assert mean == 10.5 and median == 10.5
    assert (p05, p25, p75, p95) == (1.95, 5.75, 15.25, 19.05)


def test_summarise_rounds_to_four_significant_digits():
    assert reference.summarise([23456.0] * 3)[0] == 23460.0


# -- buckets and threshold ------------------------------------------------------


def test_threshold_drops_small_buckets_but_their_theses_still_count_upward():
    """10 theses in field 300, 5 in field 500: the 500 bucket is dropped, yet
    all 15 count in 'all fields' of bachelor/de and in the yearly summary."""
    theses = [_thesis(100 + i, field="300") for i in range(10)]
    theses += [_thesis(1000 + i, field="500") for i in range(5)]
    rows = _rows(_build(theses))
    assert ("bachelor", "de", "300", 2015) in rows
    assert ("bachelor", "de", "500", 2015) not in rows
    pooled = rows[("bachelor", "de", ALL, 2015)]["word_count"]
    summary = rows[(ALL, ALL, ALL, 2015)]["word_count"]
    expected = reference.summarise([100 + i for i in range(10)] + [1000 + i for i in range(5)])
    assert pooled == expected and summary == expected


def test_exactly_ten_theses_is_enough_nine_is_not():
    rows = _rows(_build([_thesis(i, field="300") for i in range(10)]))
    assert ("bachelor", "de", "300", 2015) in rows
    rows = _rows(_build([_thesis(i, field="300") for i in range(9)]))
    assert rows == {}


def test_threshold_is_per_metric():
    theses = [_thesis(i) for i in range(10)]
    for thesis in theses[:4]:
        thesis.metrics["yules_k"] = 100.0
    values = _rows(_build(theses))[("bachelor", "de", "300", 2015)]
    assert "word_count" in values and "yules_k" not in values


def test_unknown_field_only_counts_in_all_fields():
    theses = [_thesis(i, field=None) for i in range(12)]
    rows = _rows(_build(theses))
    assert set(rows) == {("bachelor", "de", ALL, 2015), (ALL, ALL, ALL, 2015)}
    assert all(key[2] in reference.FIELDS + (ALL,) for key in rows)


def test_other_languages_count_only_in_the_yearly_summary():
    theses = [_thesis(i, language=None) for i in range(10)]
    assert set(_rows(_build(theses))) == {(ALL, ALL, ALL, 2015)}


def test_the_document_carries_no_counts():
    document = _build([_thesis(i) for i in range(25)])
    text = reference.dump_aggregates(document)
    for word in ('"n"', '"count"', '"n_theses"', '"size"'):
        assert word not in text
    for row in document["rows"]:
        assert set(row) == {"type", "language", "field", "year", "values"}
        for values in row["values"].values():
            assert len(values) == len(reference.STATS)


def test_dump_is_valid_deterministic_json():
    document = _build([_thesis(i) for i in range(10)])
    text = reference.dump_aggregates(document)
    assert json.loads(text) == document
    assert reference.dump_aggregates(document) == text
    assert text.isascii()


def test_status_must_be_interim_or_release():
    with pytest.raises(ValueError):
        reference.build_aggregates([], status="draft", source="", generated="", generator="")


# -- population and derived metrics -------------------------------------------


@pytest.mark.parametrize(
    "values,expected",
    [
        ({"thesis_type": "bachelor", "publication_year": 2010, "language_code": "de"},
         ("bachelor", "de", 2010)),
        ({"thesis_type": "master", "publication_year": 2025.0, "language_code": "fr"},
         ("master", None, 2025)),
        ({"thesis_type": "diploma", "publication_year": 2010, "language_code": "de"}, None),
        ({"thesis_type": "bachelor", "publication_year": 2002, "language_code": "de"}, None),
        ({"thesis_type": "bachelor", "publication_year": 2026, "language_code": "de"}, None),
        ({"thesis_type": "bachelor", "language_code": "de"}, None),
    ],
)
def test_reference_split(values, expected):
    assert reference.reference_split(values) == expected


def test_derive_metrics_adds_the_ratios():
    derived = reference.derive_metrics(
        {"word_count": 20000, "n_pages": 80, "n_images": 8, "file_size_bytes": 4_000_000,
         "thesis_type": "bachelor", "yules_k": None}
    )
    assert derived["word_count"] == 20000.0
    assert derived["file_size_mb"] == 4.0
    assert derived["words_per_page"] == 250.0
    assert derived["images_per_page"] == 0.1
    assert derived["kb_per_page"] == 50.0
    assert "yules_k" not in derived and "thesis_type" not in derived


def test_derive_metrics_skips_ratios_without_pages():
    derived = reference.derive_metrics({"word_count": 100, "n_pages": 0})
    assert "words_per_page" not in derived


def test_every_catalogue_metric_has_a_label():
    assert set(reference.METRIC_LABELS) == set(reference.METRICS)
    assert set(reference.DERIVED) <= set(reference.METRICS)


# -- highlight rule -----------------------------------------------------------


STATS = {"p05": 10.0, "p25": 20.0, "median": 25.0, "p75": 30.0, "p95": 40.0, "mean": 25.0}


@pytest.mark.parametrize(
    "value,level",
    [
        (25.0, 0),
        (20.0, 0), (30.0, 0),          # IQR edges are inside
        (19.999, 1), (30.001, 1),
        (10.0, 1), (40.0, 1),          # 5-95 edges are inside
        (9.999, 2), (40.001, 2),
    ],
)
def test_band_level_at_the_percentile_edges(value, level):
    assert reference.band_level(value, STATS) == level


# -- the Reference wrapper and the shipped file ---------------------------------


def test_reference_lookup():
    ref = reference.Reference(_build([_thesis(i, field="300") for i in range(10)]))
    stats = ref.stats("bachelor", "de", "300", 2015, "word_count")
    assert stats["median"] == 4.5 and set(stats) == set(reference.STATS)
    assert ref.stats("bachelor", "de", "300", 2016, "word_count") is None
    assert ref.fields == ["300"]


def test_reference_rejects_a_foreign_document():
    with pytest.raises(ValueError):
        reference.Reference({"format": "something else"})


def test_the_shipped_file_loads_and_keeps_the_rules():
    ref = reference.load_shipped()
    assert ref is not None, "tta/core/report_assets/reference_aggregates.json is missing"
    document = ref.document
    assert document["status"] in ("interim", "release")
    assert document["min_theses"] == reference.MIN_THESES
    assert tuple(document["years"]) == reference.YEARS
    for key, values in ref.rows.items():
        thesis_type, language, field_code, year = key
        assert reference.YEARS[0] <= year <= reference.YEARS[1]
        if thesis_type == ALL:
            assert (language, field_code) == (ALL, ALL)
        else:
            assert thesis_type in ("bachelor", "master")
            assert language in reference.LANGUAGES
            assert field_code == ALL or field_code in reference.FIELDS
        assert set(values) <= set(reference.METRICS)
        for stats in values.values():
            mean, median, p05, p25, p75, p95 = stats
            assert p05 <= p25 <= median <= p75 <= p95
    # no counts anywhere in the shipped data
    for row in document["rows"]:
        assert set(row) == {"type", "language", "field", "year", "values"}
