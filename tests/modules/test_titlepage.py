"""Unit tests for the shared title-page parser (`_titlepage`, SDD Sec. 7.4, #81, #82).

Covers the page model (front matter, title page), the normalisation helpers
and the rule-agnostic researcher-ruleset hook of ADR-0023 (whose default is no
rules at all: the text is read unmodified).
"""

from tta.core.modules import _titlepage
from tta.core.modules._titlepage import CoverRule, CoverRuleset, PatternRule

COVER_MARK = "generated automatically upon download from the Example Repository"
RULES = CoverRuleset(
    id="example-repo",
    version="1",
    covers=(CoverRule("example-cover", all_of=(COVER_MARK,)),),
    not_evidence_pages=(
        CoverRule("example-metadata", any_of=("Deposited:", "Licence:", "Persistent ID:"), min_any=2),
    ),
    date_cues=(PatternRule("example-deposit-label", "deposited"),),
    type_passages=(PatternRule("example-form", "this form applies to every thesis", tail=10),),
    max_pages=2,
    source="example.toml",
)
METADATA_PAGE = "Deposited:\n2015\nLicence:\nCC BY\n"


def test_normalise_folds_case_accents_apostrophes_and_space():
    assert _titlepage.normalise("  Master\u2019s  Thesis\n\u00dcBER Stra\u00dfe ") == (
        "masters thesis uber strasse"
    )


def test_collapse_letter_spacing_joins_spaced_headings_only():
    assert _titlepage.collapse_letter_spacing("m a s t e r t h e s i s") == "masterthesis"
    assert _titlepage.collapse_letter_spacing("a b c") == "a b c"
    assert _titlepage.collapse_letter_spacing("in a b c d e f study") == "in abcdef study"


def test_title_page_is_the_first_page_with_30_characters():
    front = _titlepage.front_matter(" \f- 3 -\f" + "x" * 30 + "\fmore")
    assert front.title_page() == 2
    assert _titlepage.front_matter("short\fshort").title_page() is None


def test_front_matter_reads_a_bounded_number_of_pages():
    text = "\f".join(f"page {i}" for i in range(100))
    front = _titlepage.front_matter(text)
    assert len(front.pages) == _titlepage.LEAD_PAGES
    assert front.pages[-1] == f"page {_titlepage.LEAD_PAGES - 1}"


# -- researcher rulesets (ADR-0023) ------------------------------------------------


def test_default_is_no_rules_and_the_text_unmodified():
    text = COVER_MARK + "\f" + METADATA_PAGE + "\fTitle page " + "x" * 30
    front = _titlepage.front_matter(text)
    assert front.pages == tuple(text.split("\f"))
    assert front.covers == () and front.not_evidence == ()
    assert front.own_start == 0
    assert _titlepage.cover_diagnostics(front, None) == {
        "cover_rules": None,
        "cover_pages": [],
        "not_evidence_pages": [],
    }


def test_page_rule_matches_after_normalisation():
    rule = CoverRule("r", all_of=(COVER_MARK,))
    page = "This page was\nGENERATED automatically upon\ndownload from the Example  Repository."
    assert rule.matches(_titlepage.normalise(page))
    assert not CoverRule("empty").matches(_titlepage.normalise(page))


def test_page_rule_all_of_any_of_and_min_any():
    rule = CoverRule("r", all_of=("cover sheet",), any_of=("deposited", "archived"))
    assert rule.matches("cover sheet archived 2020")
    assert not rule.matches("cover sheet 2020")
    assert not rule.matches("archived 2020")
    two = CoverRule("two", any_of=("a:", "b:", "c:"), min_any=2)
    assert two.matches("a: 1 c: 2")
    assert not two.matches("a: 1")


def test_only_leading_cover_pages_are_skipped():
    text = "\f".join([COVER_MARK, COVER_MARK, "Title page " + "x" * 30, COVER_MARK])
    front = _titlepage.front_matter(text, RULES)
    assert front.covers == ((0, "example-cover"), (1, "example-cover"))
    assert front.own_start == 2
    assert front.title_page() == 2
    # a matching page after the title page is not a cover
    assert len(front.own_pages()) == 2


def test_cover_skipping_is_capped_at_max_pages():
    text = "\f".join([COVER_MARK] * 5 + ["Title page " + "x" * 30])
    assert len(_titlepage.front_matter(text, RULES).covers) == RULES.max_pages


def test_not_evidence_pages_are_kept_and_marked():
    text = "Title page " + "x" * 30 + "\f" + METADATA_PAGE + "\fmore"
    front = _titlepage.front_matter(text, RULES)
    assert front.covers == ()
    assert front.not_evidence == ((1, "example-metadata"),)
    assert front.not_evidence_rule(1) == "example-metadata"
    assert front.not_evidence_rule(0) is None
    assert front.title_page() == 0


def test_ruleset_fingerprint_covers_every_rule_kind_but_not_the_source():
    moved = CoverRuleset(
        RULES.id,
        RULES.version,
        RULES.covers,
        RULES.not_evidence_pages,
        RULES.date_cues,
        RULES.type_passages,
        RULES.max_pages,
        source="elsewhere.toml",
    )
    assert moved.fingerprint() == RULES.fingerprint()
    for changed in (
        CoverRuleset(RULES.id, RULES.version, (CoverRule("example-cover", all_of=("other",)),)),
        CoverRuleset(RULES.id, RULES.version, RULES.covers, date_cues=(PatternRule("x", "other"),)),
        CoverRuleset(
            RULES.id, RULES.version, RULES.covers, type_passages=(PatternRule("x", "y", tail=1),)
        ),
    ):
        assert changed.fingerprint() != RULES.fingerprint()


def test_versioned_appends_a_ruleset_suffix_only_with_rules():
    assert _titlepage.versioned("0.3.0", None) == "0.3.0"
    assert _titlepage.versioned("0.3.0", RULES) == (
        f"0.3.0+covers.example-repo.{RULES.fingerprint()[:8]}"
    )


def test_cover_diagnostics_record_ruleset_and_pages():
    text = COVER_MARK + "\fTitle " + "x" * 30 + "\f" + METADATA_PAGE
    front = _titlepage.front_matter(text, RULES)
    diagnostics = _titlepage.cover_diagnostics(front, RULES)
    assert diagnostics["cover_pages"] == [{"page": 0, "rule": "example-cover"}]
    assert diagnostics["not_evidence_pages"] == [{"page": 2, "rule": "example-metadata"}]
    assert diagnostics["cover_rules"] == {
        "id": "example-repo",
        "version": "1",
        "fingerprint": RULES.fingerprint(),
        "rules": ["example-cover", "example-metadata", "example-deposit-label", "example-form"],
        "source": "example.toml",
    }
