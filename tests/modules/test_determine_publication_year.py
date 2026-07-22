"""Unit tests for mod_determine_publication_year (SDD Sec. 7.4, #17).

Fusion precedence: in-text title-page year > PDF creation year > PDF
modification year > none. Validation against the labeled exploration-harvest
dataset is a deferred follow-up (that dataset is not part of this repo).
"""

from tta.core.modules.determine_publication_year import DeterminePublicationYear

TITLE_WITH_YEAR = (
    "University of Someplace\n\nA Study of Widgets\n\n"
    "Master's Thesis, submitted September 2021\n"
)
TITLE_NO_YEAR = "University of Someplace\n\nA Study of Widgets\n\nby A. Researcher\n"


def meta(creation=None, modification=None):
    info = {}
    if creation is not None:
        info["/CreationDate"] = f"D:{creation}0101000000Z"
    if modification is not None:
        info["/ModDate"] = f"D:{modification}0101000000Z"
    return {"info": info}


def run(build_ctx, raw_text, creation=None, modification=None):
    ctx = build_ctx(raw_text=raw_text, pdf_metadata=meta(creation, modification))
    return DeterminePublicationYear().run(ctx)


def test_title_page_year_wins_over_pdf_metadata(build_ctx):
    result = run(build_ctx, TITLE_WITH_YEAR, creation=2019, modification=2020)
    assert result.metrics["publication_year"] == 2021
    assert result.metrics["publication_year_source"] == "title_page"


def test_falls_back_to_pdf_creation(build_ctx):
    result = run(build_ctx, TITLE_NO_YEAR, creation=2019, modification=2020)
    assert result.metrics["publication_year"] == 2019
    assert result.metrics["publication_year_source"] == "pdf_creation"


def test_falls_back_to_pdf_modification(build_ctx):
    result = run(build_ctx, TITLE_NO_YEAR, creation=None, modification=2018)
    assert result.metrics["publication_year"] == 2018
    assert result.metrics["publication_year_source"] == "pdf_modification"


def test_no_signal_is_ok_with_null_year(build_ctx):
    result = run(build_ctx, TITLE_NO_YEAR, creation=None, modification=None)
    assert result.metrics["publication_year"] is None
    assert result.metrics["publication_year_source"] == "none"


def test_most_recent_plausible_title_page_year_chosen(build_ctx):
    # a citation from 2010 plus the 2023 submission year -> pick the newest
    text = "Building on prior work from 2010, this Bachelor thesis (2023) ...\n"
    result = run(build_ctx, text, creation=2011)
    assert result.metrics["publication_year"] == 2023
    assert result.metrics["publication_year_source"] == "title_page"


def test_implausible_future_year_is_ignored(build_ctx):
    # a stray "2999" is out of range; fall back to the PDF creation year
    result = run(build_ctx, "Draft 2999 edition\n", creation=2022)
    assert result.metrics["publication_year"] == 2022
    assert result.metrics["publication_year_source"] == "pdf_creation"


def test_notes_record_the_fusion_detail(build_ctx):
    notes = run(build_ctx, TITLE_WITH_YEAR, creation=2019).notes
    assert notes["in_text_year"] == 2021
    assert notes["pdf_creation_year"] == 2019
    assert notes["source"] == "title_page"
