"""Unit tests for mod_determine_publication_year (SDD Sec. 7.4, #17, #81, ADR-0022).

Fusion precedence: thesis date from the title page (+3 pages) > PDF creation
year > PDF modification year > none. The date rules ("date rules v1") are
exercised form by form and exclusion by exclusion with synthetic title pages
modelled on the corpus examples of docs/titlepage-rules.md (no real names).
Validation against a labelled holdout is #50.
"""

import pytest

from tta.core.modules import _dates
from tta.core.modules._titlepage import CoverRule, CoverRuleset
from tta.core.modules.determine_publication_year import DeterminePublicationYear

TITLE_WITH_YEAR = (
    "University of Someplace\n\nA Study of Widgets\n\n"
    "Master's Thesis, submitted September 2021\n"
)
TITLE_NO_YEAR = "University of Someplace\n\nA Study of Widgets\n\nby A. Researcher\n"
HEAD = "Universit\u00e4t Musterstadt\nEine Studie \u00fcber Widgets\nMasterarbeit\nvorgelegt von A. Researcher\n"

# A repository cover page in the layout of the ETH Research Collection
# (synthetic values): deposit metadata, not the thesis.
REPOSITORY_COVER = (
    "ETH Library\nA Study of Widgets\nMaster Thesis\nAuthor(s):\nA. Researcher\n"
    "Publication date:\n2015\nPermanent link:\nhttps://doi.org/10.0000/example\n"
    "Rights / license:\nIn Copyright - Non-Commercial Use Permitted\n"
    "This page was generated automatically upon download from the ETH Zurich "
    "Research Collection.\nFor more information, please consult the Terms of use.\n"
)
ETH_RULES = CoverRuleset(
    id="eth-research-collection",
    version="1",
    rules=(
        CoverRule(
            "eth-rc-download-cover",
            all_of=(
                "This page was generated automatically upon download from the ETH Zurich "
                "Research Collection",
            ),
        ),
    ),
)


def meta(creation=None, modification=None):
    info = {}
    if creation is not None:
        info["/CreationDate"] = f"D:{creation}0101000000Z"
    if modification is not None:
        info["/ModDate"] = f"D:{modification}0101000000Z"
    return {"info": info}


def run(build_ctx, raw_text, creation=None, modification=None, cover_rules=None):
    ctx = build_ctx(raw_text=raw_text, pdf_metadata=meta(creation, modification))
    return DeterminePublicationYear(cover_rules).run(ctx)


def title_date(build_ctx, raw_text, **kwargs):
    return run(build_ctx, raw_text, creation=1999, **kwargs).diagnostics["title_page_date"]


# -- fusion ---------------------------------------------------------------------


def test_title_page_year_wins_over_pdf_metadata(build_ctx):
    result = run(build_ctx, TITLE_WITH_YEAR, creation=2019, modification=2020)
    assert result.metrics["publication_year"] == 2021
    assert result.metrics["publication_year_source"] == "title_page"
    assert result.metrics["publication_date_precision"] == "month"


def test_falls_back_to_pdf_creation_flagged_as_year_precision(build_ctx):
    result = run(build_ctx, TITLE_NO_YEAR, creation=2019, modification=2020)
    assert result.metrics["publication_year"] == 2019
    assert result.metrics["publication_year_source"] == "pdf_creation"
    assert result.metrics["publication_date_precision"] == "year"
    assert result.diagnostics["title_page_date"] is None


def test_falls_back_to_pdf_modification(build_ctx):
    result = run(build_ctx, TITLE_NO_YEAR, creation=None, modification=2018)
    assert result.metrics["publication_year"] == 2018
    assert result.metrics["publication_year_source"] == "pdf_modification"


def test_no_signal_is_ok_with_null_year_and_precision(build_ctx):
    result = run(build_ctx, TITLE_NO_YEAR, creation=None, modification=None)
    assert result.metrics["publication_year"] is None
    assert result.metrics["publication_year_source"] == "none"
    assert result.metrics["publication_date_precision"] is None


def test_empty_text_falls_back(build_ctx):
    result = run(build_ctx, "", creation=2020)
    assert result.metrics["publication_year_source"] == "pdf_creation"
    assert result.diagnostics["title_page"] is None


def test_implausible_future_year_is_ignored(build_ctx):
    result = run(build_ctx, HEAD + "Berlin, M\u00e4rz 2038\n", creation=2022)
    assert result.metrics["publication_year"] == 2022
    assert result.metrics["publication_year_source"] == "pdf_creation"


# -- matched forms ----------------------------------------------------------------


@pytest.mark.parametrize(
    "line, year, precision, form",
    [
        ("Berlin, March 24, 2005", 2005, "day", "month_d_y"),
        ("Z\u00fcrich, 12. Mai 2014", 2014, "day", "d_month_y"),
        ("Berlin, den 29.3.1995", 1995, "day", "num_dmy"),
        ("Thursday 24th March, 2016", 2016, "day", "d_month_y"),
        ("August, 22, 2006", 2006, "day", "month_d_y"),
        ("8/15/2008", 2008, "day", "num_dmy_slash"),
        ("2003-05-26", 2003, "day", "iso_ymd"),
        ("2007/10/01", 2007, "day", "ymd_slash"),
        ("02-01-2008", 2008, "day", "num_dmy_dash"),
        ("Berlin, im August 2007", 2007, "month", "month_y"),
        ("Z\u00fcrich, M\u00e4rz 1978", 1978, "month", "month_y"),
        ("Zurich, Marz 1978", 1978, "month", "month_y"),  # OCR umlaut loss
        ("Zurich, M\u00a8arz 1978", 1978, "month", "month_y"),  # LaTeX/OCR diaeresis
        ("Zurich, Sept. 2010", 2010, "month", "month_y"),
        ("Agosto 2001", 2001, "month", "month_y"),  # Italian
        ("2006-03", 2006, "month", "iso_ym"),
        ("Date: 08/2009", 2009, "month", "num_my"),
        ("Sommersemester 1948", 1948, "semester", "semester"),
        ("FS 2009", 2009, "semester", "semester"),
        ("Master Thesis HS 2013", 2013, "semester", "semester"),
        ("Semester: Sommer 2018", 2018, "semester", "season"),
        ("Spring 2017", 2017, "semester", "season"),
        ("2020/2021", 2021, "year_range", "acad"),
        ("2006", 2006, "year", "year"),
        ("Humboldt-Universit\u00e4t zu Berlin, 2009. - 78 S.", 2009, "year", "year"),
    ],
)
def test_matched_forms(build_ctx, line, year, precision, form):
    result = run(build_ctx, HEAD + line + "\n", creation=1999)
    assert result.metrics["publication_year"] == year
    assert result.metrics["publication_date_precision"] == precision
    assert result.diagnostics["title_page_date"]["form"] == form


@pytest.mark.parametrize(
    "line, year",
    [
        ("Wintersemester 1997/98", 1998),
        ("Einreichung: WS 2013/14", 2014),
        ("Diplomarbeit WS 97/98", 1998),
        ("Winter 2005", 2006),
    ],
)
def test_winter_terms_map_to_the_end_year(build_ctx, line, year):
    result = run(build_ctx, HEAD + line + "\n", creation=1999)
    assert result.metrics["publication_year"] == year
    assert result.metrics["publication_date_precision"] == "semester"


def test_french_month_names_are_not_matched(build_ctx):
    # French months occur only in reference lists of the corpus: the month is
    # not read; the year still counts as a bare year ending a title-page line
    result = run(build_ctx, HEAD + "Paris, 12 juillet 2004\n", creation=2010)
    assert result.metrics["publication_year"] == 2004
    assert result.metrics["publication_date_precision"] == "year"


def test_day_and_month_are_kept_in_diagnostics_only(build_ctx):
    result = run(build_ctx, HEAD + "Berlin, den 12.05.2014\n", creation=1999)
    assert result.diagnostics["title_page_date"]["date"] == "2014-05-12"
    assert set(result.metrics) == {
        "publication_year",
        "publication_year_source",
        "publication_date_precision",
    }


# -- exclusions -------------------------------------------------------------------


@pytest.mark.parametrize(
    "noise, reason",
    [
        ("geboren am 11.05.1968 in Musterstadt", "birth"),
        ("born on the 12th of March 1988 in Geneva", "birth"),
        ("Tag der m\u00fcndlichen Pr\u00fcfung: 15. Dezember 2006", "defence"),
        ("defended on: 14 June 2012", "defence"),
        ("akzeptiert: M\u00e4rz 2006", "defence"),
        ("\u00a9 Copyright 2008 Distributed Systems Group", "copyright"),
        ("zuletzt aufgerufen: 30. Dez. 2022", "access"),
        ("[\u00fcberarbeitet im August 2018]", "revision"),
        ("Version with minor changes, January 1, 2017", "revision"),
        ("This document was compiled on Tuesday 30th May, 2023", "build"),
    ],
)
def test_negative_cues_exclude_a_candidate(build_ctx, noise, reason):
    text = HEAD + noise + "\nBerlin, im Oktober 2005\n"
    result = run(build_ctx, text, creation=1999)
    assert result.metrics["publication_year"] == 2005
    rejected = {c["rejected"] for c in result.diagnostics["candidates"]}
    assert reason in rejected


def test_label_line_directly_above_counts_as_a_cue(build_ctx):
    text = (
        HEAD
        + "Tag der m\u00fcndlichen Pr\u00fcfung:\n15. Januar 2006\n"
        + "eingereicht am:\n30. September 2005\n"
    )
    assert run(build_ctx, text, creation=1999).metrics["publication_year"] == 2005


def test_negative_cues_never_cross_lines(build_ctx):
    text = HEAD + "geboren am 30. Dezember 1981 in Leipzig\n9th February 2009\n"
    assert run(build_ctx, text, creation=1999).metrics["publication_year"] == 2009


def test_surname_born_is_not_a_birth_cue(build_ctx):
    text = HEAD + "A. Born, Zurich, April 11, 2023\n"
    assert run(build_ctx, text, creation=1999).metrics["publication_year"] == 2023


def test_citations_are_excluded(build_ctx):
    text = HEAD + "(Diaconis, 1988; Critchlow, 1985)\nBerlin, im Mai 2004\n"
    result = run(build_ctx, text, creation=1999)
    assert result.metrics["publication_year"] == 2004
    assert "citation" in {c["rejected"] for c in result.diagnostics["candidates"]}


def test_the_end_of_a_range_wins(build_ctx):
    date = title_date(build_ctx, HEAD + "September 2011 - March 2012\n")
    assert date["date"] == "2012-03"
    date = title_date(build_ctx, HEAD + "5. M\u00e4rz bis 27. Juli 2001\n")
    assert date["date"] == "2001-07-27"


def test_years_in_titles_are_excluded(build_ctx):
    text = (
        "Die deutsche Au\u00dfenpolitik SEIT 1945\nZWISCHEN 1933 UND 1939\n"
        "Masterarbeit\nBerlin, im Mai 2010\n"
    )
    assert run(build_ctx, text, creation=1999).metrics["publication_year"] == 2010


def test_bare_year_needs_a_position(build_ctx):
    # a year inside running title-page text is no thesis date
    text = HEAD + "Eine Untersuchung der Wahl von 1998 und ihrer Folgen\n"
    result = run(build_ctx, text, creation=2011)
    assert result.metrics["publication_year_source"] == "pdf_creation"


def test_thesis_year_cue_for_series_reprints(build_ctx):
    # owner decision #81: a series reprint gets the thesis year, not the series year
    text = (
        HEAD + "\f\f\fDiese Ver\u00f6ffentlichung geht zur\u00fcck auf eine Masterarbeit, "
        "eingereicht im Jahr 2003.\nBerlin, 2005\n"
    )
    result = run(build_ctx, text, creation=1999)
    assert result.metrics["publication_year"] == 2003
    assert result.diagnostics["title_page_date"]["rule"] == "submission_cue"


# -- position and preference --------------------------------------------------------


def test_after_the_title_page_running_text_dates_do_not_count(build_ctx):
    text = HEAD + "\fVorwort\nIm Juli 2005 gr\u00fcndete die Firma ein Labor.\n"
    result = run(build_ctx, text, creation=2007)
    assert result.metrics["publication_year_source"] == "pdf_creation"
    assert "after_title_page" in {c["rejected"] for c in result.diagnostics["candidates"]}


def test_after_the_title_page_place_date_counts(build_ctx):
    text = HEAD + "\fErkl\u00e4rung\nIch versichere ...\nBerlin, den 3. Mai 2005\n"
    date = title_date(build_ctx, text)
    assert date["date"] == "2005-05-03" and date["page"] == 1


def test_submission_cue_wins_within_a_page(build_ctx):
    text = HEAD + "Wintersemester 2004/2005\nletzte Version am: 8. November 2004\n"
    date = title_date(build_ctx, text)
    assert date["date"] == "2004-11-08" and date["rule"] == "submission_cue"


def test_explicit_date_beats_an_earlier_semester(build_ctx):
    text = HEAD + "Sommersemester 2014\nZ\u00fcrich, 3. Februar 2015\n"
    date = title_date(build_ctx, text)
    assert date["date"] == "2015-02-03" and date["rule"] == "most_precise_on_page"


def test_title_page_date_beats_a_later_declaration_date(build_ctx):
    text = HEAD + "November 2023\n\fErkl\u00e4rung\nZurich, 26. 1. 2024\n"
    assert run(build_ctx, text, creation=1999).metrics["publication_year"] == 2023


def test_blank_leading_page_is_not_the_title_page(build_ctx):
    text = "   \n  - \f" + HEAD + "Berlin, im Mai 2004\n"
    result = run(build_ctx, text, creation=1999)
    assert result.diagnostics["title_page"] == 1
    assert result.metrics["publication_year"] == 2004


def test_window_is_the_title_page_plus_three_pages(build_ctx):
    inside = HEAD + "\f\f\fBerlin, den 3. Mai 2005\n"
    assert run(build_ctx, inside, creation=1999).metrics["publication_year"] == 2005
    outside = HEAD + "\f\f\f\fBerlin, den 3. Mai 2005\n"
    assert run(build_ctx, outside, creation=1999).metrics["publication_year"] == 1999


# -- repository cover pages (ADR-0022 / ADR-0023) ----------------------------------------


def test_default_path_applies_no_cover_rule(build_ctx):
    text = REPOSITORY_COVER + "\f" + HEAD + "Zurich, 1. M\u00e4rz 2014\n"
    result = run(build_ctx, text, creation=2026)
    assert result.diagnostics["cover_rules"] is None
    assert result.diagnostics["cover_pages"] == []
    assert result.diagnostics["title_page"] == 0  # the cover page is not skipped


def test_default_path_ignores_the_repository_metadata_page(build_ctx):
    # the deposit year on the metadata page never becomes the thesis year
    text = REPOSITORY_COVER + "\f" + HEAD + "Zurich, 1. M\u00e4rz 2014\n"
    result = run(build_ctx, text, creation=2026)
    assert result.metrics["publication_year"] != 2015
    rejected = {c["rejected"] for c in result.diagnostics["candidates"] if c["page"] == 0}
    assert rejected == {"repository_metadata_page"}


def test_publication_date_label_is_excluded_anywhere(build_ctx):
    text = HEAD + "Publication date:\n2015\nBerlin, im Mai 2014\n"
    result = run(build_ctx, text, creation=1999)
    assert result.metrics["publication_year"] == 2014
    assert "repository" in {c["rejected"] for c in result.diagnostics["candidates"]}


def test_cover_ruleset_skips_the_cover_and_is_recorded(build_ctx):
    text = (
        REPOSITORY_COVER + "\f" + REPOSITORY_COVER + "\f" + HEAD + "Zurich, 1. M\u00e4rz 2014\n"
    )
    result = run(build_ctx, text, creation=2026, cover_rules=ETH_RULES)
    assert result.metrics["publication_year"] == 2014
    assert result.metrics["publication_date_precision"] == "day"
    assert result.diagnostics["title_page"] == 2
    assert result.diagnostics["title_page_date"]["page"] == 0
    assert result.diagnostics["cover_pages"] == [
        {"page": 0, "rule": "eth-rc-download-cover"},
        {"page": 1, "rule": "eth-rc-download-cover"},
    ]
    assert result.diagnostics["cover_rules"]["id"] == "eth-research-collection"


def test_cover_ruleset_changes_the_module_version():
    base = DeterminePublicationYear().spec.version
    with_rules = DeterminePublicationYear(ETH_RULES).spec.version
    assert base == DeterminePublicationYear.spec.version
    assert with_rules.startswith(base + "+covers.eth-research-collection.")


# -- the helper directly -------------------------------------------------------------


def test_every_form_has_a_precision():
    assert {name for name, _rx in _dates.PATTERNS} == set(_dates.PRECISION)
    assert set(_dates.PRECISION.values()) == {"day", "month", "semester", "year", "year_range"}
