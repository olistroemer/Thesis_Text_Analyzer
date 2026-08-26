"""Cohort report: aggregation, chart maths, and the HTML document.

No Tk anywhere - the report left the Tk adapter in #51 (ADR-0016 rev. 2),
so `collect()` and the whole rendering path are testable headless (QA-TEST).
"""

import pytest

from tta.core import report


def _seed(project, filename="a.pdf", *, excluded=False, **metrics):
    """Add a thesis with one ok run carrying `metrics`. Returns its id."""
    pdf = project.dir / filename
    pdf.write_bytes(b"%PDF-" + filename.encode())
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics=metrics)
    if excluded:
        project.repo.set_excluded(thesis.id, True)
    return thesis.id


# -- collect() ---------------------------------------------------------------


def test_collect_over_an_empty_project_is_all_zeroes(project):
    data = report.collect(project.repo)
    assert (data.theses, data.excluded, data.garbled) == (0, 0, 0)
    assert data.median_words is None and data.year_range is None
    assert data.by_type == {} and data.notable == []


def test_collect_aggregates_the_local_cohort(project):
    _seed(project, "a.pdf", word_count=9000, publication_year=2021,
          thesis_type="bachelor", language_code="en", flesch_reading_ease=50.0)
    _seed(project, "b.pdf", word_count=21000, publication_year=2023,
          thesis_type="master", language_code="de", flesch_reading_ease=40.0)
    _seed(project, "c.pdf", word_count=15000, language_code="de")

    data = report.collect(project.repo)
    assert data.theses == 3
    assert data.by_type == {"bachelor": 1, "master": 1, "unspecified": 1}
    assert data.by_language == {"de": 2, "en": 1}
    assert data.median_words == 15000
    assert data.year_range == (2021, 2023)
    # c.pdf has no publication_year, so it is not on the time axis
    assert sorted(data.words_by_year) == [(2021, 9000, "bachelor"), (2023, 21000, "master")]
    assert data.words_by_type == {
        "bachelor": [9000], "master": [21000], "unspecified": [15000]
    }
    assert data.fre_by_language == {"en": [50.0], "de": [40.0]}


def test_collect_excludes_excluded_theses_but_counts_them(project):
    _seed(project, "keep.pdf", word_count=9000, thesis_type="bachelor")
    _seed(project, "drop.pdf", excluded=True, word_count=99000, thesis_type="master")

    data = report.collect(project.repo)
    assert (data.theses, data.excluded) == (1, 1)
    assert data.by_type == {"bachelor": 1}
    assert data.median_words == 9000


def test_collect_drops_garbled_theses_from_the_aggregates(project):
    _seed(project, "good.pdf", word_count=9000, extraction_quality="ok")
    _seed(project, "bad.pdf", word_count=1, extraction_quality="garbled")

    data = report.collect(project.repo)
    assert (data.theses, data.garbled) == (1, 1)
    assert data.median_words == 9000


def test_notable_needs_outliers_on_two_trustworthy_metrics(project):
    # a tight cohort of six, then one thesis far outside on two metrics and
    # another far outside on only one
    for index in range(6):
        _seed(project, f"n{index}.pdf", yules_k=100.0, avg_word_len=5.0, std_sentence_len=8.0)
    two = _seed(project, "two.pdf", yules_k=900.0, avg_word_len=40.0, std_sentence_len=8.0)
    _seed(project, "one.pdf", yules_k=900.0, avg_word_len=5.0, std_sentence_len=8.0)

    flagged = dict(report.collect(project.repo).notable)
    assert list(flagged) == [f"thesis {two}"]
    assert sorted(flagged[f"thesis {two}"]) == ["avg_word_len", "yules_k"]


def test_notable_identifies_theses_by_id_never_by_filename(project):
    """theses.pdf_filename is Category.IDENTIFYING and must not reach a
    written file (ADR-0016 rev. 2, SDD Sec. 9.8.3)."""
    for index in range(6):
        _seed(project, f"n{index}.pdf", yules_k=100.0, avg_word_len=5.0)
    outlier = _seed(project, "Mustermann_Erika_bachelor.pdf", yules_k=900.0, avg_word_len=40.0)

    data = report.collect(project.repo)
    assert data.notable == [(f"thesis {outlier}", ["avg_word_len", "yules_k"])]
    rendered = report.render_html(data)
    assert "Mustermann" not in rendered
    assert ".pdf" not in rendered


# -- box_stats ---------------------------------------------------------------


def test_box_stats_quartiles_whiskers_and_fliers():
    box = report.box_stats([1, 2, 3, 4, 5, 100])
    assert (box.q1, box.median, box.q3) == (2.25, 3.5, 4.75)
    # fence is 4.75 + 1.5 * 2.5 = 8.5, so the whisker stops at the real datum 5
    assert (box.whisker_lo, box.whisker_hi) == (1.0, 5.0)
    assert box.fliers == (100.0,)


def test_box_stats_without_fliers_reaches_the_extremes():
    box = report.box_stats([10, 20, 30, 40])
    assert box.fliers == ()
    assert (box.whisker_lo, box.whisker_hi) == (10.0, 40.0)


def test_box_stats_degenerate_inputs():
    assert report.box_stats([]) is None
    single = report.box_stats([7])
    assert (single.q1, single.median, single.q3) == (7.0, 7.0, 7.0)
    assert (single.whisker_lo, single.whisker_hi, single.fliers) == (7.0, 7.0, ())


def test_box_stats_matches_matplotlib():
    """Equivalence with the implementation this replaced (#51). Skipped once
    matplotlib is dropped from the environment."""
    cbook = pytest.importorskip("matplotlib.cbook")
    series = [3, 5, 5, 6, 7, 8, 8, 9, 12, 40, -20]
    theirs = cbook.boxplot_stats(series)[0]
    ours = report.box_stats(series)
    assert (ours.q1, ours.median, ours.q3) == pytest.approx(
        (theirs["q1"], theirs["med"], theirs["q3"])
    )
    assert (ours.whisker_lo, ours.whisker_hi) == pytest.approx(
        (theirs["whislo"], theirs["whishi"])
    )
    assert sorted(ours.fliers) == pytest.approx(sorted(theirs["fliers"]))


# -- histogram ---------------------------------------------------------------


def test_histogram_bins_the_range_with_a_closed_last_bin():
    edges, counts = report.histogram([1, 2, 3, 4, 5], bins=2)
    assert edges == [1.0, 3.0, 5.0]
    assert counts == [2, 3]  # 5 lands in the last bin, which is closed
    assert sum(counts) == 5


def test_histogram_shared_span_lines_overlays_up():
    edges, _ = report.histogram([0, 100], bins=4)
    _, low = report.histogram([1, 2], bins=4, span=(edges[0], edges[-1]))
    _, high = report.histogram([99], bins=4, span=(edges[0], edges[-1]))
    assert low == [2, 0, 0, 0]
    assert high == [0, 0, 0, 1]


def test_histogram_degenerate_inputs():
    assert report.histogram([]) == ([], [])
    assert report.histogram([5], bins=0) == ([], [])
    edges, counts = report.histogram([5, 5, 5], bins=2)
    assert edges == [4.5, 5.0, 5.5]  # numpy widens an all-equal series
    assert counts == [0, 3]


def test_histogram_matches_numpy():
    numpy = pytest.importorskip("numpy")
    series = [0.5, 1.25, 1.25, 3.0, 7.75, 9.0, 9.0, 12.5]
    counts, edges = numpy.histogram(series, bins=report.HIST_BINS)
    ours_edges, ours_counts = report.histogram(series, bins=report.HIST_BINS)
    assert ours_counts == list(counts)
    assert ours_edges == pytest.approx(list(edges))


# -- render_html -------------------------------------------------------------


def _rendered(project):
    return report.render_html(report.collect(project.repo))


def test_render_html_makes_no_external_request(project):
    """QA-PRIV: the app is offline, so the report it writes must be one
    self-contained file - no CDN, no web font, no remote image."""
    _seed(project, "a.pdf", word_count=9000, publication_year=2021,
          thesis_type="bachelor", language_code="en", flesch_reading_ease=50.0)
    out = _rendered(project)
    assert "http://" not in out
    assert "https://" not in out
    assert "<script" not in out
    assert "src=" not in out and "@import" not in out
    # everything a browser needs is in the one string
    assert out.startswith("<!DOCTYPE html>")
    assert "<style>" in out and out.count("</html>") == 1


def test_render_html_draws_four_inline_charts(project):
    for index in range(6):
        _seed(project, f"t{index}.pdf", word_count=9000 + index * 500,
              publication_year=2018 + index, thesis_type="bachelor",
              language_code="de", flesch_reading_ease=40.0 + index)
    out = _rendered(project)
    assert out.count("<svg") == 4
    assert 'class="dot' in out and 'class="box' in out
    assert 'class="hbar' in out and 'class="bar' in out
    assert 'class="trend"' in out  # >= 5 dated theses (Sec. 9.8.3)
    assert "publication year" in out and "Flesch reading ease" in out


def test_render_html_omits_the_trend_line_below_five_points(project):
    for index in range(3):
        _seed(project, f"t{index}.pdf", word_count=9000, publication_year=2020 + index)
    assert 'class="trend"' not in _rendered(project)


def test_render_html_renders_an_empty_cohort_without_crashing(project):
    out = _rendered(project)
    assert out.count("<svg") == 0
    assert out.count('class="empty"') == 5  # four charts plus notable theses
    assert out.endswith("</html>\n")


def test_render_html_reports_the_garbled_caption(project):
    _seed(project, "good.pdf", word_count=9000)
    _seed(project, "bad.pdf", extraction_quality="garbled")
    assert "garbled text extraction" in _rendered(project)


def test_render_html_escapes_metric_values(project):
    _seed(project, "a.pdf", word_count=100, language_code="<img>", thesis_type="a&b")
    out = _rendered(project)
    assert "<img>" not in out
    assert "&lt;img&gt;" in out and "a&amp;b" in out


def test_render_html_folds_categorical_series_past_the_colour_cap(project):
    """Categorical hues are assigned in fixed order and never cycled: a
    fourth overlay series folds into one neutral "other"."""
    for index, code in enumerate(("de", "en", "fr", "it", "es")):
        _seed(project, f"{code}.pdf", language_code=code, flesch_reading_ease=40.0 + index)
    out = _rendered(project)
    assert "other (2 more)" in out
    assert 'class="hbar s4' not in out


def test_render_html_timestamp_is_injectable(project):
    from datetime import datetime

    out = report.render_html(report.collect(project.repo), datetime(2026, 8, 26, 9, 5))
    assert "2026-08-26 09:05" in out


# -- default_report_path -----------------------------------------------------


def test_default_report_path_is_dated_and_under_reports(tmp_path):
    from datetime import date

    path = report.default_report_path(tmp_path, date(2026, 8, 26))
    assert path == tmp_path / "reports" / "report-2026-08-26.html"
    # pure: nothing is created on disk (ADR-0002 - core does no I/O)
    assert not path.parent.exists()
