"""Researcher rulesets (ADR-0023, #81, #82): loader, the ETH ruleset kept in
research/, and the guarantees that the shipped app applies no repository rule,
contains none of the moved rules' text and ships no ruleset.
"""

import ast
import re
from pathlib import Path

import pytest

from tta.core.cover_rules import CoverRulesError, load_cover_ruleset, parse_cover_ruleset
from tta.core.modules import _titlepage
from tta.core.modules.registry import default_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_RULES = REPO_ROOT / "research" / "cover_rules"
ETH_FILE = RESEARCH_RULES / "eth_research_collection.toml"
ETH_COVER = (
    "ETH Library\nA Study of Widgets\nMaster Thesis\nPublication date:\n2015\n"
    "This page was generated automatically upon download from the ETH Zurich "
    "Research Collection.\nFor more information, please consult the Terms of use.\n"
)
# the older layout puts a line break inside the marker sentence
ETH_COVER_OLD = (
    "Research Collection\nMaster Thesis\nA Study of Widgets\nPublication Date:\n2017\n"
    "This page was generated automatically upon download from the ETH Zurich Research "
    "Collection. For more\ninformation please consult the Terms of use.\nETH Library\n"
)

MINIMAL = {"id": "x", "version": "1", "covers": [{"id": "r", "all_of": ["cover"]}]}
# every repository- or institution-specific text the default path used to carry
# (round 1 of the lane) and the ETH cover marker: none may live under tta/
MOVED_TEXT = (
    "generated automatically upon download",
    "research collection",
    "publication date:",
    "permanent link",
    "rights / license",
    "component of every",
    "bestandteil jeder",
)


def test_parse_minimal_ruleset():
    rules = parse_cover_ruleset(MINIMAL, source="x.toml")
    assert rules.id == "x" and rules.version == "1" and rules.max_pages == 3
    assert rules.covers[0].all_of == ("cover",)
    assert rules.not_evidence_pages == rules.date_cues == rules.type_passages == ()
    assert rules.source == "x.toml"


def test_parse_every_rule_kind():
    rules = parse_cover_ruleset(
        {
            "id": "x",
            "version": 2,
            "not_evidence_pages": [{"id": "p", "any_of": ["a:", "b:", "c:"], "min_any": 2}],
            "date_cues": [{"id": "d", "pattern": "deposited"}],
            "type_passages": [{"id": "t", "pattern": "every (?:thesis|paper)", "tail": 40}],
        }
    )
    assert rules.covers == ()
    assert rules.not_evidence_pages[0].min_any == 2
    assert rules.date_cues[0].pattern == "deposited"
    assert rules.type_passages[0].tail == 40
    assert rules.rule_ids() == ["p", "d", "t"]


@pytest.mark.parametrize(
    "data, message",
    [
        ({**MINIMAL, "colour": "red"}, "unknown key"),
        ({**MINIMAL, "rules": []}, "unknown key"),  # the round-1 key is gone
        ({"version": "1", "covers": MINIMAL["covers"]}, "'id'"),
        ({"id": "x", "covers": MINIMAL["covers"]}, "'version'"),
        ({**MINIMAL, "covers": []}, "at least one rule"),
        ({**MINIMAL, "max_pages": 0}, "max_pages"),
        ({**MINIMAL, "covers": [{"id": "r", "allof": ["cover"]}]}, "unknown key"),
        ({**MINIMAL, "covers": [{"id": "r"}]}, "all_of"),
        ({**MINIMAL, "covers": [{"id": "r", "all_of": "cover"}]}, "list of non-empty strings"),
        ({**MINIMAL, "covers": [{"id": "r", "any_of": ["a"], "min_any": 2}]}, "min_any"),
        ({**MINIMAL, "covers": [{"id": "r", "all_of": ["a"]}, {"id": "r", "all_of": ["b"]}]},
         "duplicate"),
        ({**MINIMAL, "date_cues": [{"id": "r"}]}, "duplicate"),
        ({**MINIMAL, "date_cues": [{"id": "d"}]}, "'pattern'"),
        ({**MINIMAL, "date_cues": [{"id": "d", "pattern": "(unclosed"}]}, "regular expression"),
        ({**MINIMAL, "type_passages": [{"id": "t", "pattern": "x", "tail": -1}]}, "tail"),
        ({**MINIMAL, "type_passages": "x"}, "list of"),
    ],
)
def test_invalid_rulesets_are_rejected(data, message):
    with pytest.raises(CoverRulesError, match=message):
        parse_cover_ruleset(data)


def test_unreadable_or_invalid_toml_is_a_cover_rules_error(tmp_path):
    with pytest.raises(CoverRulesError, match="cannot read"):
        load_cover_ruleset(tmp_path / "missing.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("id = ", encoding="utf-8")
    with pytest.raises(CoverRulesError, match="not valid TOML"):
        load_cover_ruleset(bad)


def test_the_eth_research_ruleset_loads_and_matches_both_layouts():
    rules = load_cover_ruleset(ETH_FILE)
    assert rules.id == "eth-research-collection"
    assert rules.source == "eth_research_collection.toml"
    assert rules.rule_ids() == [
        "eth-rc-download-cover",
        "eth-rc-metadata-block",
        "eth-rc-publication-date-label",
        "eth-declaration-of-originality",
    ]
    for cover in (ETH_COVER, ETH_COVER_OLD):
        front = _titlepage.front_matter(cover + "\f" + cover + "\fMasterarbeit " + "x" * 30, rules)
        assert front.covers == ((0, "eth-rc-download-cover"), (1, "eth-rc-download-cover"))
    plain = _titlepage.front_matter("Masterarbeit\nETH Zurich " + "x" * 30, rules)
    assert plain.covers == ()


# -- the shipped app applies no cover rule and ships no ruleset ---------------------


def test_default_registry_applies_no_cover_rule():
    registry = default_registry()
    for name in ("mod_classify_thesis_type", "mod_determine_publication_year"):
        module = registry.get(name)
        assert module.cover_rules is None
        assert "+" not in module.spec.version


def test_registry_with_a_ruleset_versions_both_title_page_modules():
    rules = load_cover_ruleset(ETH_FILE)
    registry = default_registry(rules)
    suffix = "+" + rules.version_suffix()
    for name in ("mod_classify_thesis_type", "mod_determine_publication_year"):
        assert registry.get(name).spec.version.endswith(suffix)
    others = [m for m in registry.in_topological_order() if m.spec.name not in (
        "mod_classify_thesis_type", "mod_determine_publication_year")]
    assert all("+" not in m.spec.version for m in others)


def test_no_repository_specific_text_lives_in_the_package():
    """Repository- and institution-specific rules are data in research/, not
    shipped code or help (owner decisions on #81/#82): none of their text may
    appear anywhere under tta/ - sources, help pages or catalogues."""
    offenders = sorted(
        (str(path.relative_to(REPO_ROOT)), phrase)
        for path in (REPO_ROOT / "tta").rglob("*")
        if path.is_file() and path.suffix in {".py", ".md", ".po", ".pot", ".toml", ".json", ".txt"}
        for phrase in MOVED_TEXT
        if phrase in path.read_text(encoding="utf-8", errors="ignore").casefold()
    )
    assert offenders == []


def test_the_gui_never_loads_a_cover_ruleset():
    ui = REPO_ROOT / "tta" / "ui"
    hits = [
        str(path.relative_to(REPO_ROOT))
        for path in ui.rglob("*.py")
        if re.search(r"cover_rules|load_cover_ruleset", path.read_text(encoding="utf-8"))
    ]
    assert hits == []


def test_the_packaging_spec_bundles_no_research_ruleset():
    source = (REPO_ROOT / "packaging" / "tta.spec").read_text(encoding="utf-8")
    tree = ast.parse(source)
    datas = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "datas"
    )
    assert "research" not in ast.unparse(datas.value)
    assert "cover_rules" not in source


def test_the_wheel_packages_only_tta():
    import tomllib

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = config["tool"]["setuptools"]
    assert setuptools["packages"]["find"]["include"] == ["tta*"]
    package_data = setuptools.get("package-data", {})
    assert not any("research" in str(v) for v in package_data.values())
    assert not (RESEARCH_RULES / "__init__.py").exists()
