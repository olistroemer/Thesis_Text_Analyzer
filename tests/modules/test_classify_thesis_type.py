"""Unit tests for mod_classify_thesis_type (SDD Sec. 7.4, ADR-0019 rev. 3, #9, #67, #82).

Example-based, with synthetic de/en title pages modelled on the corpus
examples of docs/titlepage-rules.md ("type markers v1"; no real names).
Validation against a labelled holdout is #50.
"""

import pytest

from tta.core.modules import classify_thesis_type as ctt
from tta.core.modules._titlepage import CoverRule, CoverRuleset
from tta.core.modules.classify_thesis_type import ClassifyThesisType
from tta.core.types import REFERENCE_THESIS_TYPES, THESIS_TYPES, thesis_type_label

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
# Pre-Bologna German title page (#67). Carries a supervisor title with the
# abbreviated "Dipl.-Ing." form that must NOT be read as a degree.
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
# #67 false-positive trap: abbreviations are never markers.
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
# a repository cover page (synthetic values, ETH Research Collection layout):
# its type line is the repository's metadata
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
            all_of=("generated automatically upon download from the ETH Zurich Research Collection",),
        ),
    ),
)


def run(build_ctx, raw_text, cover_rules=None):
    return ClassifyThesisType(cover_rules).run(build_ctx(raw_text=raw_text))


def thesis_type(build_ctx, raw_text, cover_rules=None):
    return run(build_ctx, raw_text, cover_rules).metrics["thesis_type"]


# -- the original cases (#9, #67) -------------------------------------------------


def test_detects_german_master(build_ctx):
    result = run(build_ctx, GERMAN_MASTER)
    assert result.metrics["thesis_type"] == "master"
    assert result.diagnostics["winner"]["marker"] == "Masterarbeit/-thesis"
    assert result.diagnostics["rule"] == "earliest_marker"


def test_detects_german_bachelor(build_ctx):
    assert thesis_type(build_ctx, GERMAN_BACHELOR) == "bachelor"


def test_detects_english_master(build_ctx):
    assert thesis_type(build_ctx, ENGLISH_MASTER) == "master"


def test_detects_english_bachelor_by_the_degree_phrase(build_ctx):
    result = run(build_ctx, ENGLISH_BACHELOR)
    assert result.metrics["thesis_type"] == "bachelor"
    assert result.diagnostics["winner"]["marker"] == "degree of Bachelor"


def test_case_and_apostrophe_insensitive(build_ctx):
    # upper case + typographic apostrophe (\u2019) both fold to the marker
    text = "UNIVERSITY\n\nMASTER\u2019S THESIS\n\nin Computer Science\n"
    assert thesis_type(build_ctx, text) == "master"


def test_no_marker_is_unspecified(build_ctx):
    result = run(build_ctx, NO_DEGREE)
    assert result.metrics["thesis_type"] == "unspecified"
    assert result.diagnostics["winner"] is None


def test_garbled_or_empty_returns_unspecified_not_na(build_ctx):
    # sparse/garbled text is a valid 'unspecified', never NotApplicable (#9)
    assert thesis_type(build_ctx, "") == "unspecified"
    assert thesis_type(build_ctx, "\x00\x01 qz xkcd \f") == "unspecified"


def test_earliest_marker_wins(build_ctx):
    cases = {
        "Diplomarbeit ... vgl. Masterarbeit und Bachelorarbeit im Anhang": "diploma",
        "Masterarbeit ... vgl. Diplomarbeit und Bachelorarbeit im Anhang": "master",
        "Bachelorarbeit ... vgl. Diplomarbeit und Masterarbeit im Anhang": "bachelor",
        "Magisterarbeit zur Erlangung des Grades Magister Artium (M.A.)": "magister",
    }
    for text, expected in cases.items():
        assert thesis_type(build_ctx, text) == expected


def test_detects_german_and_english_diploma(build_ctx):
    result = run(build_ctx, GERMAN_DIPLOMA)
    assert result.metrics["thesis_type"] == "diploma"
    assert result.diagnostics["winner"]["marker"] == "Diplomarbeit/Diploma thesis"
    assert thesis_type(build_ctx, ENGLISH_DIPLOMA) == "diploma"


def test_dipl_supervisor_titles_are_not_a_diploma(build_ctx):
    result = run(build_ctx, GERMAN_MASTER_WITH_DIPL_SUPERVISORS)
    assert result.metrics["thesis_type"] == "master"
    assert {m["class"] for m in result.diagnostics["markers"]} == {"master"}


# -- window (own pages 0-4) ------------------------------------------------------


def test_marker_on_a_later_own_page_is_found(build_ctx):
    # HU series reprints: "geht zurueck auf eine Masterarbeit" on page 3
    text = "Berliner Reihe Heft 12\f\f\fDiese Ver\u00f6ffentlichung geht zur\u00fcck auf eine Masterarbeit.\n"
    result = run(build_ctx, text)
    assert result.metrics["thesis_type"] == "master"
    assert result.diagnostics["winner"]["page"] == 3


def test_window_is_five_own_pages(build_ctx):
    assert thesis_type(build_ctx, "x\f\f\f\fMasterarbeit\n") == "master"
    assert thesis_type(build_ctx, "x\f\f\f\f\fMasterarbeit\n") == "unspecified"


# -- the new classes (#82) ---------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected, marker",
    [
        ("Magisterarbeit zur Erlangung des akademischen Grades", "magister", "Magisterarbeit"),
        ("Magisterarb. im Fach Geschichte", "magister", "Magisterarbeit"),
        ("zur Erlangung des Grades Magistra Artium", "magister", "Magister/Magistra Artium"),
        ("Lizentiatsarbeit der Philosophischen Fakult\u00e4t", "licentiate", "Lizentiatsarbeit"),
        ("MAS-Programm in Raumplanung 2017/19", "mas", "Master of Advanced Studies / MAS"),
        (
            "Nachdiplomarbeit im Rahmen des Nachdiplomstudiums",
            "mas",
            "Nachdiplom / postgraduate studies",
        ),
        ("Semester Thesis\nInstitute for Widgets", "semester", "Semesterarbeit/-project"),
        ("Studienarbeit zur Erlangung des Bachelor of Laws", "semester", "Studienarbeit"),
        ("Focus Work\nAutonomous Systems Lab", "semester", "Focus Work"),
        (
            "Dissertation zur Erlangung des Doktorgrades",
            "doctoral",
            "Dissertation zur Erlangung / submitted",
        ),
        ("A thesis submitted for the degree of Doctor of Sciences", "doctoral",
         "Doctor of Sciences / Doktorgrad"),
        ("Doctoral Thesis\nDepartment of Widgets", "doctoral", "Doctoral thesis / Doktorarbeit"),
        ("Diplomthema C\nDiplomandin", "diploma", "Diplomthema/Diplomand"),
        ("Hausarbeit zur Diplompr\u00fcfung", "diploma", "Hausarbeit zur Diplompruefung"),
        ("Forschungsarbeit zur Erlangung des Grades Diplom-Psychologe", "diploma",
         "Diplom-<degree> (spelled out)"),
        ("Bachelor-Abschlussarbeit\nStudiengang Statistik", "bachelor", "Bachelorarbeit/-thesis"),
        ("M.Sc. Thesis in Statistics", "master", "MSc/Master of Science thesis"),
    ],
)
def test_marker_catalogue(build_ctx, text, expected, marker):
    result = run(build_ctx, text)
    assert result.metrics["thesis_type"] == expected
    assert result.diagnostics["winner"]["marker"] == marker


def test_mas_override_on_the_same_page(build_ctx):
    text = "Master Thesis\nMaster of Advanced Studies in Widget Engineering\n"
    result = run(build_ctx, text)
    assert result.metrics["thesis_type"] == "mas"
    assert result.diagnostics["rule"] == "earliest_marker+mas_override"


def test_mas_on_another_page_does_not_override(build_ctx):
    text = "Master Thesis\fsee also the Master of Advanced Studies programme\n"
    assert thesis_type(build_ctx, text) == "master"


def test_nachdiplomarbeit_is_not_a_diplomarbeit(build_ctx):
    result = run(build_ctx, "Nachdiplomarbeit\n")
    assert result.metrics["thesis_type"] == "mas"
    assert "diploma" not in {m["class"] for m in result.diagnostics["markers"]}


@pytest.mark.parametrize(
    "never",
    [
        "B.Sc. A. Researcher",
        "Betreuer: Prof. Dr. A. Beispiel, M.Sc.",
        "Gutachterin: B. Muster, M.A.",
        "Dipl.-Ing. C. Beispiel",
        "Dr. sc. D. Muster",
        "PhD candidate E. Beispiel",
        "lic. phil. F. Muster",
        "Online-Dissertationen im Vergleich",
        "Masterstudiengang Informatik",
        "Masterplan f\u00fcr die Innenstadt",
        "Diplom und Zeugnis",
    ],
)
def test_abbreviations_and_bare_words_are_never_markers(build_ctx, never):
    assert thesis_type(build_ctx, "Eine Studie\n" + never + "\n") == "unspecified"


def test_letter_spaced_headings_are_collapsed(build_ctx):
    assert thesis_type(build_ctx, "M A S T E R T H E S I S\nin Physics\n") == "master"
    assert thesis_type(build_ctx, "A B S C H L U S S A R B E I T\nBachelor of Science\n") == "bachelor"


def test_eth_declaration_of_originality_is_excluded(build_ctx):
    text = (
        "Declaration of originality\nThe signed declaration of originality is a component "
        "of every semester paper, Bachelor's thesis, Master's thesis and any other degree "
        "paper undertaken during the course of studies.\n"
    )
    result = run(build_ctx, text)
    assert result.metrics["thesis_type"] == "unspecified"
    assert {m["excluded"] for m in result.diagnostics["markers"]} == {"declaration of originality"}


# -- tier 2 ----------------------------------------------------------------------


def test_tier2_field_degree_only_without_a_tier1_marker(build_ctx):
    result = run(build_ctx, "Abschlussbericht\nBachelor of Science\nStudiengang Statistik\n")
    assert result.metrics["thesis_type"] == "bachelor"
    assert result.diagnostics["rule"] == "earliest_marker_tier2"
    assert result.diagnostics["winner"]["tier"] == 2


def test_tier1_beats_an_earlier_tier2_field_degree(build_ctx):
    # the author's previous degree comes first; the thesis type wins
    text = "submitted by A. Researcher, Bachelor of Science\nMaster Thesis\n"
    assert thesis_type(build_ctx, text) == "master"


# -- repository cover pages (ADR-0019 rev. 3 / ADR-0023) ------------------------------


def test_default_path_applies_no_cover_rule_but_ignores_the_metadata_page(build_ctx):
    text = REPOSITORY_COVER + "\fDiplomarbeit\nam Institut f\u00fcr Widgets\n"
    result = run(build_ctx, text)
    # the cover's "Master Thesis" type line is repository metadata
    assert result.metrics["thesis_type"] == "diploma"
    assert result.diagnostics["cover_rules"] is None
    assert result.diagnostics["cover_pages"] == []
    assert result.diagnostics["winner"]["page"] == 1  # the cover still counts as a page
    assert {m["excluded"] for m in result.diagnostics["markers"] if m["page"] == 0} == {
        "repository metadata page"
    }


def test_cover_ruleset_skips_the_cover(build_ctx):
    text = REPOSITORY_COVER + "\fDiplomarbeit\nam Institut f\u00fcr Widgets\n"
    result = run(build_ctx, text, cover_rules=ETH_RULES)
    assert result.metrics["thesis_type"] == "diploma"
    assert result.diagnostics["winner"]["page"] == 0
    assert result.diagnostics["cover_pages"] == [{"page": 0, "rule": "eth-rc-download-cover"}]
    assert result.diagnostics["cover_rules"]["fingerprint"] == ETH_RULES.fingerprint()


def test_cover_ruleset_changes_the_module_version():
    assert ClassifyThesisType().spec.version == ClassifyThesisType.spec.version
    assert ClassifyThesisType(ETH_RULES).spec.version.startswith(
        ClassifyThesisType.spec.version + "+covers.eth-research-collection."
    )


# -- the value domain -------------------------------------------------------------


def test_value_domain_and_reference_types():
    assert set(THESIS_TYPES) == {
        "bachelor",
        "master",
        "diploma",
        "magister",
        "mas",
        "licentiate",
        "semester",
        "doctoral",
        "unspecified",
    }
    assert set(ctt.TIER1) | {"unspecified"} == set(THESIS_TYPES)
    assert REFERENCE_THESIS_TYPES == ("bachelor", "master")
    assert "baccalaureate" not in THESIS_TYPES


def test_every_type_has_a_label():
    for value in THESIS_TYPES:
        assert thesis_type_label(value) and thesis_type_label(value) != value
    assert thesis_type_label("from_a_newer_version") == "from_a_newer_version"
