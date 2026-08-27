"""Unit tests for mod_classify_thesis_type (SDD Sec. 7.4, ADR-0019, #9).

Example-based, with representative de/en title-page fixtures. Validation
against the labeled exploration-harvest dataset (F1 / confusion matrix) is a
deferred follow-up (that dataset is not part of this repo).
"""

from tta.core.modules.classify_thesis_type import ClassifyThesisType

# German title page naming a master's thesis. "Universitaet" carries an umlaut
# to exercise the accent/umlaut-tolerant normalisation (\u00e4 keeps the source
# ASCII per ADR-0018).
GERMAN_MASTER = (
    "Technische Universit\u00e4t Musterstadt\n"
    "Fakult\u00e4t f\u00fcr Informatik\n\n"
    "Masterarbeit\n\n"
    "Zur Erlangung des akademischen Grades\n"
    "Master of Science (M.Sc.)\n\n"
    "Titel der Arbeit: Ein Beitrag zur Textanalyse\n"
    "vorgelegt von Max Mustermann\n"
)
GERMAN_BACHELOR = (
    "Hochschule Musterstadt\n\n"
    "Bachelorarbeit\n\n"
    "im Studiengang Informatik\n"
    "vorgelegt von Erika Musterfrau\n"
)
ENGLISH_MASTER = (
    "University of Someplace\n\n"
    "Master's Thesis\n\n"  # straight apostrophe
    "submitted in partial fulfilment of the degree of Master of Science\n"
)
ENGLISH_BACHELOR = (
    "University of Someplace\n\n"
    "A thesis submitted for the degree of Bachelor of Science (B.Sc.)\n"
)
# Pre-Bologna German title page (#67). Carries a spelled-out supervisor title
# with the abbreviated "Dipl.-Ing." form that must NOT be read as a degree.
GERMAN_DIPLOMA = (
    "Technische Universit\u00e4t Musterstadt\n"
    "Fakult\u00e4t f\u00fcr Maschinenbau\n\n"
    "Diplomarbeit\n\n"
    "Zur Erlangung des akademischen Grades\n"
    "Diplom-Ingenieur (Dipl.-Ing.)\n\n"
    "vorgelegt von Max Mustermann\n"
    "Betreuer: Prof. Dr.-Ing. Dipl.-Ing. E. Beispiel\n"
)
ENGLISH_DIPLOMA = (
    "University of Someplace\n\n"
    "A Diploma Thesis submitted to the Faculty of Engineering\n"
)
# A Masterarbeit whose title page credits supervisors with Diplom titles - the
# #67 false-positive trap: bare "dipl." / "diplom" must not classify this as
# `diploma`, because the titles sit in the same 3000-char window (_titlepage).
GERMAN_MASTER_WITH_DIPL_SUPERVISORS = (
    "Hochschule Musterstadt\n\n"
    "Masterarbeit\n\n"
    "im Studiengang Informatik\n"
    "vorgelegt von Erika Musterfrau\n\n"
    "Erstpr\u00fcfer: Prof. Dr. Dipl.-Inform. A. Beispiel\n"
    "Zweitpr\u00fcfer: Dipl.-Ing. B. Muster\n"
    "Betrieblicher Betreuer: Dipl.-Wirtsch.-Ing. C. Beispiel\n"
)

# no degree named anywhere on the page
NO_DEGREE = (
    "Some Institute\n\nAn Investigation into Widget Dynamics\n\n"
    "by A. Researcher, submitted September 2023\n"
)


def run(build_ctx, raw_text):
    return ClassifyThesisType().run(build_ctx(raw_text=raw_text))


def test_detects_german_master(build_ctx):
    result = run(build_ctx, GERMAN_MASTER)
    assert result.metrics["thesis_type"] == "master"
    assert "masterarbeit" in result.diagnostics["master_markers"]


def test_detects_german_bachelor(build_ctx):
    assert run(build_ctx, GERMAN_BACHELOR).metrics["thesis_type"] == "bachelor"


def test_detects_english_master(build_ctx):
    assert run(build_ctx, ENGLISH_MASTER).metrics["thesis_type"] == "master"


def test_detects_english_bachelor(build_ctx):
    assert run(build_ctx, ENGLISH_BACHELOR).metrics["thesis_type"] == "bachelor"


def test_case_and_apostrophe_insensitive(build_ctx):
    # upper case + typographic apostrophe (\u2019) both fold to the keyword
    text = "UNIVERSITY\n\nMASTER\u2019S THESIS\n\nin Computer Science\n"
    assert run(build_ctx, text).metrics["thesis_type"] == "master"


def test_no_keyword_is_unspecified(build_ctx):
    assert run(build_ctx, NO_DEGREE).metrics["thesis_type"] == "unspecified"


def test_garbled_or_empty_returns_unspecified_not_na(build_ctx):
    # sparse/garbled text is a valid 'unspecified', never NotApplicable (#9)
    assert run(build_ctx, "").metrics["thesis_type"] == "unspecified"
    assert run(build_ctx, "\x00\x01 qz xkcd \f").metrics["thesis_type"] == "unspecified"


def test_both_markers_earliest_wins(build_ctx):
    bach_first = "Bachelorarbeit ... siehe auch Masterarbeit im Anhang"
    mast_first = "Masterarbeit ... im Unterschied zur Bachelorarbeit"
    assert run(build_ctx, bach_first).metrics["thesis_type"] == "bachelor"
    assert run(build_ctx, mast_first).metrics["thesis_type"] == "master"


def test_only_the_title_page_window_is_scanned(build_ctx):
    # the keyword sits on the second page (after the form feed) -> not seen
    text = "Cover page with no degree named\n\n" + " " * 50 + "\f\nMasterarbeit on page two\n"
    assert run(build_ctx, text).metrics["thesis_type"] == "unspecified"


def test_detects_german_diploma(build_ctx):
    """#67: pre-Bologna German theses name neither Bachelor nor Master."""
    result = run(build_ctx, GERMAN_DIPLOMA)
    assert result.metrics["thesis_type"] == "diploma"
    assert "diplomarbeit" in result.diagnostics["diploma_markers"]


def test_detects_english_diploma(build_ctx):
    assert run(build_ctx, ENGLISH_DIPLOMA).metrics["thesis_type"] == "diploma"


def test_dipl_supervisor_titles_are_not_a_diploma(build_ctx):
    """#67 false-positive guard: "Dipl.-Inform."/"Dipl.-Ing." examiner titles
    live in the same title-page window, so bare "diplom"/"dipl." are excluded
    from the keyword set. This must stay a `master`."""
    result = run(build_ctx, GERMAN_MASTER_WITH_DIPL_SUPERVISORS)
    assert result.metrics["thesis_type"] == "master"
    assert result.diagnostics["diploma_markers"] == []


def test_diploma_keywords_exclude_the_ambiguous_short_forms(build_ctx):
    from tta.core.modules.classify_thesis_type import DIPLOMA_KEYWORDS

    assert "diplom" not in DIPLOMA_KEYWORDS
    assert "dipl." not in DIPLOMA_KEYWORDS
    assert "dipl" not in DIPLOMA_KEYWORDS


def test_three_class_tiebreak_earliest_marker_wins(build_ctx):
    """The old pairwise `<` comparison did not generalise to three classes."""
    cases = {
        "Diplomarbeit ... vgl. Masterarbeit und Bachelorarbeit im Anhang": "diploma",
        "Masterarbeit ... vgl. Diplomarbeit und Bachelorarbeit im Anhang": "master",
        "Bachelorarbeit ... vgl. Diplomarbeit und Masterarbeit im Anhang": "bachelor",
    }
    for text, expected in cases.items():
        assert run(build_ctx, text).metrics["thesis_type"] == expected


def test_diploma_is_in_the_declared_value_domain():
    from tta.core.types import THESIS_TYPES

    assert set(THESIS_TYPES) == {"bachelor", "master", "diploma", "unspecified"}
