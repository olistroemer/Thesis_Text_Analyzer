"""The professor report: aggregation, comparison levels, and the HTML document.

No Tk anywhere - the report left the Tk adapter in #51 (ADR-0016 rev. 2), so
`collect()` and the whole rendering path are testable headless (QA-TEST).
Rev. 3 (#84): interactive, plotly.js inline, compared with the shipped
reference aggregates (ADR-0025), a local product with a note at the top.
"""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tta.core import reference as ref
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


def _payload(document: str) -> dict:
    match = re.search(r'<script type="application/json" id="tta-data">(.*?)</script>',
                      document, re.S)
    assert match, "no data block"
    return json.loads(match.group(1))


def _reference(rows):
    """A Reference from {(type, lang, field, year): {metric: (p05, p25, med, p75, p95)}};
    p05 and p95 None for a bucket with the inner band only."""
    document = {
        "format": ref.FORMAT, "format_version": ref.FORMAT_VERSION, "status": "release",
        "years": list(ref.YEARS), "min_theses": ref.min_theses(), "stats": list(ref.STATS),
        "rows": [
            {"type": t, "language": l, "field": f, "year": y,
             "values": {m: [med, med, p05, p25, p75, p95]
                        for m, (p05, p25, med, p75, p95) in values.items()}}
            for (t, l, f, y), values in rows.items()
        ],
    }
    return ref.Reference(document)


# -- collect() ---------------------------------------------------------------


def test_collect_over_an_empty_project_is_all_zeroes(project):
    data = report.collect(project.repo)
    assert (data.theses, data.excluded, data.garbled) == (0, 0, 0)
    assert data.median_words is None and data.year_range is None
    assert data.by_type == {} and data.records == []


def test_collect_builds_one_record_per_thesis(project):
    first = _seed(project, "a.pdf", word_count=9000, publication_year=2021, n_pages=30,
                  thesis_type="bachelor", language_code="en", flesch_reading_ease=50.0,
                  creator_category="word", producer_category="other")
    _seed(project, "b.pdf", word_count=21000, publication_year=2023,
          thesis_type="master", language_code="de", creator_category="other",
          producer_category="latex")
    _seed(project, "c.pdf", word_count=15000, language_code="de")

    data = report.collect(project.repo)
    assert data.theses == 3
    assert data.by_type == {"bachelor": 1, "master": 1, "unspecified": 1}
    assert data.by_language == {"de": 2, "en": 1}
    assert data.median_words == 15000
    assert data.year_range == (2021, 2023)
    records = {r.filename: r for r in data.records}
    a = records["a.pdf"]
    assert a.id == first and a.year == 2021 and a.language == "en"
    assert a.uri.startswith("file:") and a.uri.endswith("/a.pdf")
    assert a.metrics["words_per_page"] == 300.0  # derived, as in the reference
    assert a.tool == "word"
    assert records["b.pdf"].tool == "latex"  # producer where the creator says "other"
    assert records["c.pdf"].year is None and records["c.pdf"].tool == "unknown"


def test_collect_excludes_excluded_theses_but_counts_them(project):
    _seed(project, "keep.pdf", word_count=9000, thesis_type="bachelor")
    _seed(project, "drop.pdf", excluded=True, word_count=99000, thesis_type="master")
    data = report.collect(project.repo)
    assert (data.theses, data.excluded) == (1, 1)
    assert [r.filename for r in data.records] == ["keep.pdf"]


def test_collect_drops_garbled_theses(project):
    _seed(project, "good.pdf", word_count=9000, extraction_quality="ok")
    _seed(project, "bad.pdf", word_count=1, extraction_quality="garbled")
    data = report.collect(project.repo)
    assert (data.theses, data.garbled) == (1, 1)
    assert data.median_words == 9000


# -- comparison levels -------------------------------------------------------

BANDS = {"word_count": (10.0, 20.0, 25.0, 30.0, 40.0)}


def _record(value, *, year=2015, thesis_type="bachelor", language="de"):
    return report.ThesisRecord(1, "x.pdf", None, thesis_type, language, year, "word",
                               {"word_count": value})


@pytest.fixture
def reference():
    return _reference({
        ("all", "all", "all", 2015): BANDS,
        ("bachelor", "de", "all", 2015): BANDS,
        ("bachelor", "de", "300", 2015): {"word_count": (100.0, 200.0, 250.0, 300.0, 400.0)},
    })


def test_comparison_options_order(reference):
    assert report.comparison_options(reference) == ["summary", "all", "300"]
    assert report.comparison_options(None) == ["summary", "all"]


@pytest.mark.parametrize(
    "value,levels",
    [
        (25.0, "002"),      # inside, inside, far below field 300
        (20.0, "002"),      # p25 edge is inside
        (30.0, "002"),      # p75 edge is inside
        (10.0, "112"),      # p05 edge: outside the IQR, inside 5-95
        (40.0, "112"),      # p95 edge
        (9.99, "222"),
        (400.0, "221"),     # field 300: p95 edge
        (300.0, "220"),     # field 300: p75 edge
    ],
)
def test_level_string_at_the_percentile_edges(reference, value, levels):
    options = report.comparison_options(reference)
    assert report.level_string(_record(value), "word_count", reference, options) == levels


def test_level_string_without_the_outer_band_never_claims_outside_5_95():
    """A bucket with the inner band only (ADR-0025 rev. 2): far off is level 1,
    not 2, while the yearly summary with both bands still says 2."""
    inner_only = _reference({
        ("all", "all", "all", 2015): BANDS,
        ("bachelor", "de", "all", 2015): {"word_count": (None, 20.0, 25.0, 30.0, None)},
    })
    options = report.comparison_options(inner_only)
    assert options == ["summary", "all"]
    for value, levels in ((25.0, "00"), (30.0, "00"), (35.0, "11"), (500.0, "21"),
                          (-500.0, "21")):
        assert report.level_string(_record(value), "word_count", inner_only, options) == levels


def test_level_string_without_a_comparison(reference):
    options = report.comparison_options(reference)
    # outside the reference years: shown, but without a comparison
    assert report.level_string(_record(25.0, year=2026), "word_count", reference, options) == "---"
    assert report.level_string(_record(25.0, year=None), "word_count", reference, options) == "---"
    # a type outside the reference only compares with the yearly summary
    diploma = _record(25.0, thesis_type="diploma")
    assert report.level_string(diploma, "word_count", reference, options) == "0--"
    french = _record(25.0, language="fr")
    assert report.level_string(french, "word_count", reference, options) == "0--"
    # no bucket for the year
    assert report.level_string(_record(25.0, year=2016), "word_count", reference, options) == "---"
    assert report.level_string(_record(25.0), "word_count", None, ["summary", "all"]) == "--"


# -- post-run policy and paths (unchanged by rev. 3) --------------------------


@pytest.mark.parametrize(
    "mode,cancelled,ok,expected",
    [
        ("ask", False, 3, "ask"),
        ("always", False, 3, "open"),
        ("never", False, 3, "skip"),
        ("nonsense", False, 3, "ask"),  # unknown preference falls back to asking
        ("always", True, 3, "skip"),  # cancelled runs never nag
        ("always", False, 0, "skip"),  # an all-errored run produced nothing
        ("ask", False, 0, "skip"),
    ],
)
def test_should_offer_report(mode, cancelled, ok, expected):
    assert report.should_offer_report(mode, cancelled=cancelled, ok=ok) == expected


def test_open_report_modes_are_the_documented_three():
    assert report.OPEN_REPORT_MODES == ("ask", "always", "never")


def test_default_report_path_is_dated_and_under_reports(tmp_path):
    from datetime import date

    path = report.default_report_path(tmp_path, date(2026, 8, 26))
    assert path == tmp_path / "reports" / "report-2026-08-26.html"
    # pure: nothing is created on disk (ADR-0002 - core does no I/O)
    assert not path.parent.exists()


# -- render_html -------------------------------------------------------------


def _demo(project):
    """A small professor cohort: two types, two languages, years in and out of
    the reference range."""
    for index in range(8):
        _seed(project, f"t{index}.pdf", word_count=9000 + index * 2500,
              publication_year=2016 + index, thesis_type=("bachelor", "master")[index % 2],
              language_code=("de", "en")[index % 2], flesch_reading_ease=40.0 + index,
              n_pages=40 + index, creator_category="word")
    _seed(project, "old.pdf", word_count=30000, publication_year=1998,
          thesis_type="diploma", language_code="de")


def test_render_html_makes_no_external_request(project):
    """QA-PRIV, ADR-0016 rev. 3: one self-contained file. Outside the vendored
    library there is no URL at all; the library is exactly the pinned file;
    nothing is loaded through src/href/@import/url()."""
    _demo(project)
    out = report.render_html(report.collect(project.repo))
    library = report.plotly_js()
    assert out.count(library) == 1
    assert hashlib.sha256(library.encode("utf-8")).hexdigest() == report.PLOTLY_SHA256
    outside = out.replace(library, "")
    assert "http://" not in outside and "https://" not in outside
    assert "@import" not in outside and "url(" not in outside
    for attribute in re.findall(r'\b(?:src|href)\s*=\s*"([^"]*)"', outside):
        assert attribute.startswith("file:"), attribute
    assert "<link" not in outside and "<img" not in outside and "<iframe" not in outside
    assert out.startswith("<!DOCTYPE html>") and out.count("</html>") == 1
    # the cloud features of plotly are switched off by configuration
    script = report._asset(report.SCRIPT_FILENAME)
    for setting in ("showLink: false", "showSendToCloud: false",
                    "showEditInChartStudio: false", 'topojsonURL: ""'):
        assert setting in script


def test_the_vendored_library_cannot_end_its_script_element():
    library = report.plotly_js().lower()
    assert "</script" not in library and "<script" not in library


def test_a_tampered_library_is_refused(monkeypatch):
    monkeypatch.setattr(report, "PLOTLY_SHA256", "0" * 64)
    with pytest.raises(RuntimeError):
        report.plotly_js()


def test_render_html_carries_the_privacy_note_at_the_top(project):
    _demo(project)
    out = report.render_html(report.collect(project.repo))
    note = out.index("This report may contain personal data.")
    assert note < out.index('class="cards"')
    assert "not intended to be sent to the research team" in out
    assert "anonymised export" in out


def test_render_html_builds_from_the_shipped_aggregates_and_the_project(project):
    """The report is the shipped aggregates plus the project, nothing else."""
    _demo(project)
    data = report.collect(project.repo)
    shipped = ref.load_shipped()
    assert shipped is not None
    payload = _payload(report.render_html(data))
    assert payload["bands"], "the shipped reference reached the report"
    summary = payload["bands"]["all|all|all"]
    assert set(summary) <= set(ref.METRICS)
    assert all(len(series) == len(payload["years"]) for series in summary.values())
    assert payload["options"] == report.comparison_options(shipped)
    theses = {t["name"]: t for t in payload["theses"]}
    assert set(theses) == {r.filename for r in data.records}
    assert theses["t0.pdf"]["uri"].startswith("file:")
    assert theses["old.pdf"]["lv"]["word_count"] == "-" * len(payload["options"])
    # the jitter is stable and stays within the year
    again = _payload(report.render_html(report.collect(project.repo)))
    assert [t["x"] for t in again["theses"]] == [t["x"] for t in payload["theses"]]
    for thesis in payload["theses"]:
        if thesis["year"] is not None:
            assert abs(thesis["x"] - thesis["year"]) <= report.JITTER


def test_render_html_shows_no_reference_counts(project):
    _demo(project)
    payload = _payload(report.render_html(report.collect(project.repo)))
    for series in payload["bands"].values():
        for values in series.values():
            for stats in values:
                assert stats is None or len(stats) == len(ref.STATS)
    assert "min_theses" not in json.dumps(payload["bands"])


def test_render_html_levels_follow_band_level(project, reference):
    _seed(project, "in.pdf", word_count=25.0, publication_year=2015,
          thesis_type="bachelor", language_code="de")
    _seed(project, "far.pdf", word_count=500.0, publication_year=2015,
          thesis_type="bachelor", language_code="de")
    payload = _payload(report.render_html(report.collect(project.repo), reference))
    levels = {t["name"]: t["lv"]["word_count"] for t in payload["theses"]}
    assert levels == {"in.pdf": "002", "far.pdf": "222"}


def test_render_html_caption_names_both_thresholds(project, reference):
    out = report.render_html(report.collect(project.repo), reference)
    assert "shown where at least 4 reference theses have a value" in out
    assert "the 5th-95th band only where at least 20 do" in out


def test_render_html_carries_null_outer_statistics(project):
    inner_only = _reference({
        ("bachelor", "de", "all", 2015): {"word_count": (None, 20.0, 25.0, 30.0, None)},
    })
    payload = _payload(report.render_html(report.collect(project.repo), inner_only))
    stats = payload["bands"]["bachelor|de|all"]["word_count"][2015 - ref.YEARS[0]]
    assert stats == [25.0, 25.0, None, 20.0, 30.0, None]


HARNESS = Path(__file__).with_name("report_js_harness.js")


def _run_script(payload: dict, tmp_path, selection=("bachelor", "de", "all")) -> dict:
    """The traces report.js would draw, from node with a fake DOM/Plotly."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    data = tmp_path / "payload.json"
    data.write_text(json.dumps(payload), encoding="utf-8")
    script = Path(report.__file__).with_name("report_assets") / "report.js"
    result = subprocess.run([node, str(HARNESS), str(script), str(data), *selection],
                            capture_output=True, text=True, check=True, timeout=60)
    return json.loads(result.stdout)


def test_report_script_draws_no_outer_band_where_it_is_missing(project, tmp_path):
    """ADR-0025 rev. 2: years with the inner statistics only get the median
    and the 25-75 band, no 5-95 band; each band breaks where it is missing,
    a lone year is a short block; the highlight there stops at level 1."""
    both = {"word_count": (100.0, 200.0, 250.0, 300.0, 400.0)}
    inner = {"word_count": (None, 200.0, 250.0, 300.0, None)}
    rows = {("bachelor", "de", "all", year): both for year in (2010, 2011, 2012, 2020)}
    rows.update({("bachelor", "de", "all", year): inner for year in (2013, 2014, 2015, 2018)})
    _seed(project, "far-inner.pdf", word_count=900.0, publication_year=2014,
          thesis_type="bachelor", language_code="de")
    _seed(project, "far-outer.pdf", word_count=900.0, publication_year=2011,
          thesis_type="bachelor", language_code="de")
    payload = _payload(report.render_html(report.collect(project.repo), _reference(rows)))
    traces = _run_script(payload, tmp_path)["traces"]["g-length"]

    def band_years(group):
        xs = set()
        for trace in traces:
            if trace.get("legendgroup") == group:
                xs.update(round(x, 2) for x in trace["x"])
        return xs

    assert band_years("outer") == {2010, 2011, 2012, 2019.65, 2020.35}
    assert band_years("inner") == {2010, 2011, 2012, 2013, 2014, 2015,
                                   2017.65, 2018.35, 2019.65, 2020.35}
    # every filled band edge is paired with its lower edge, per run
    for group, runs in (("outer", 2), ("inner", 3)):
        edges = [t for t in traces if t.get("legendgroup") == group]
        fills = [t for t in edges if t.get("fill")]
        assert len(edges) == 2 * runs and len(fills) == runs
        assert sum(t["showlegend"] for t in fills) == 1
    median = next(t for t in traces if t.get("name") == payload["strings"]["median"])
    text = dict(zip(payload["years"], median["text"]))
    assert "P5-P95" in text[2011] and "P25-P75" in text[2011]
    assert "P5-P95" not in text[2014] and "P25-P75" in text[2014]
    assert text[2016] is None
    points = {t["name"]: t["text"] for t in traces if t.get("mode") == "markers"}
    strings = payload["strings"]
    assert any("far-inner.pdf" in head for head in points[strings["level1"]])
    assert any("far-outer.pdf" in head for head in points[strings["level2"]])
    assert not any("far-inner.pdf" in head for head in points[strings["level2"]])


def test_report_script_claims_nothing_about_5_95_without_a_level_2(project, tmp_path):
    """Theses only outside an inner-only band: the note under the panel counts
    them against the 25-75 band, not as '0 outside the 5-95 band'."""
    inner = {"word_count": (None, 200.0, 250.0, 300.0, None)}
    rows = {("bachelor", "de", "all", year): inner for year in (2013, 2014)}
    for name in ("a.pdf", "b.pdf"):
        _seed(project, name, word_count=900.0, publication_year=2014,
              thesis_type="bachelor", language_code="de")
    payload = _payload(report.render_html(report.collect(project.repo), _reference(rows)))
    notes = _run_script(payload, tmp_path)["notes"]["o-length"]
    strings = payload["strings"]
    assert notes == [strings["outsideInner"].replace("{count}", "2")]
    assert "5th-95th" not in " ".join(notes)


def test_render_html_without_reference_data(project):
    _demo(project)
    out = report.render_html(report.collect(project.repo), None)
    payload = _payload(out)
    assert payload["bands"] == {}
    assert "No reference data is available" in out


def test_render_html_renders_an_empty_cohort(project):
    out = report.render_html(report.collect(project.repo))
    assert _payload(out)["theses"] == []
    assert out.endswith("</html>\n")


def test_render_html_reports_the_garbled_caption(project):
    _seed(project, "good.pdf", word_count=9000)
    _seed(project, "bad.pdf", extraction_quality="garbled")
    assert "garbled text extraction" in report.render_html(report.collect(project.repo))


def test_render_html_escapes_names_and_values():
    # built directly: such a name is not a legal file name on Windows
    record = report.ThesisRecord(7, "x</script><img src=y>.pdf", None, "a&b", "<img>",
                                 2015, "word", {"word_count": 100.0})
    data = report.ReportData(theses=1, by_type={"a&b": 1}, by_language={"<img>": 1},
                             records=[record])
    out = report.render_html(data)
    outside = out.replace(report.plotly_js(), "")
    assert "</script><img" not in outside
    assert "<img>" not in outside
    payload = _payload(out)
    assert payload["theses"][0]["name"] == "x</script><img src=y>.pdf"
    assert "&lt;img&gt;" in payload["theses"][0]["head"]


def test_render_html_marks_interim_reference_data(project, reference):
    out = report.render_html(report.collect(project.repo), reference)
    assert "Interim reference values" not in out
    reference.status = "interim"
    out = report.render_html(report.collect(project.repo), reference)
    assert "Interim reference values" in out


def test_the_shipped_reference_is_the_release_file(project):
    """Owner decision 2026-11-18: the re-run's values ship (ADR-0025 decision
    10), with their provenance and without the interim notice."""
    shipped = ref.load_shipped()
    assert shipped.status == "release"
    assert shipped.document["source"] and shipped.document["analysed_with"]
    assert "Interim reference values" not in report.render_html(report.collect(project.repo))


def test_render_html_timestamp_is_injectable(project):
    from datetime import datetime

    out = report.render_html(report.collect(project.repo), None, datetime(2026, 8, 26, 9, 5))
    assert "2026-08-26 09:05" in out


def test_render_html_offers_the_filters_and_pickers(project):
    out = report.render_html(report.collect(project.repo))
    for element in ('id="f-type"', 'id="f-lang"', 'id="f-field"', 'id="m-length"',
                    'id="m-style"', 'id="m-vocabulary"', 'id="m-boxes"'):
        assert element in out
    for value in ref.REFERENCE_THESIS_TYPES:
        assert f'<option value="{value}">' in out


def test_every_type_is_named_with_its_label(project):
    """#82: every detected class is shown under its label in the summary."""
    from tta.core.types import thesis_type_label

    _seed(project, "m.pdf", word_count=30000, publication_year=1999, thesis_type="magister")
    _seed(project, "l.pdf", word_count=40000, publication_year=1998, thesis_type="licentiate")
    page = report.render_html(report.collect(project.repo))
    for value in ("magister", "licentiate"):
        assert thesis_type_label(value) in page
