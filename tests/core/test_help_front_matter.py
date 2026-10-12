"""The one front-matter parser and the corpus helpers (ADR-0012 rev. 5, #78).

``core.help_corpus`` is what the GUI viewer, the CLI and the corpus gate all
read help pages through, so its edge cases are pinned here once rather than
in each consumer.
"""

import pytest

from tta.core import help_corpus
from tta.core.help_corpus import (
    FrontMatterError,
    find_page,
    first_paragraph,
    list_field,
    opens_with_title,
    read_page,
    split_front_matter,
    text_field,
)

PAGE = """---
slug: word_count
title: "Word count"
kind: metric
# a comment line inside the front matter
produced_by: mod_surface_counts

applicability: Always: every analysed thesis has one.
references: [flesch1948, 'amstad1978', ]
see_also: [module:mod_surface_counts, concept:length_confound]
---

# Word count

The number of word tokens.
"""


# -- split_front_matter -------------------------------------------------------


def test_scalars_lists_and_body_are_separated():
    fields, body = split_front_matter(PAGE)
    assert fields == {
        "slug": "word_count",
        "title": "Word count",  # quotes stripped
        "kind": "metric",
        "produced_by": "mod_surface_counts",
        # only the first colon separates key from value
        "applicability": "Always: every analysed thesis has one.",
        # quotes stripped, the empty trailing item dropped
        "references": ["flesch1948", "amstad1978"],
        "see_also": ["module:mod_surface_counts", "concept:length_confound"],
    }
    assert body == "\n# Word count\n\nThe number of word tokens.\n"


def test_page_without_front_matter_is_all_body():
    text = "# Plain\n\ntext\n"
    assert split_front_matter(text) == ({}, text)


def test_empty_text_is_all_body():
    assert split_front_matter("") == ({}, "")


def test_crlf_line_endings_are_accepted():
    fields, body = split_front_matter(PAGE.replace("\n", "\r\n"))
    assert fields["slug"] == "word_count"
    assert fields["see_also"] == ["module:mod_surface_counts", "concept:length_confound"]
    assert all("\r" not in key and "\r" not in str(value) for key, value in fields.items())
    assert body == "\r\n# Word count\r\n\r\nThe number of word tokens.\r\n"


def test_a_thematic_break_in_the_body_stays_body():
    text = "---\nslug: x\n---\n\nabove\n\n---\n\nbelow: not a field\n"
    fields, body = split_front_matter(text)
    assert fields == {"slug": "x"}
    assert body == "\nabove\n\n---\n\nbelow: not a field\n"


def test_dashes_that_do_not_open_the_file_are_not_front_matter():
    for text in (
        "# Title\n\n---\nslug: x\n---\n",  # a block further down
        "\n---\nslug: x\n---\n",  # not on the first line
    ):
        assert split_front_matter(text) == ({}, text)


def test_an_unterminated_block_is_not_front_matter():
    text = "---\nslug: x\n\nno closing line\n"
    assert split_front_matter(text) == ({}, text)


def test_closing_line_at_end_of_file_without_newline():
    assert split_front_matter("---\nslug: x\n---") == ({"slug": "x"}, "")


@pytest.mark.parametrize(
    "line",
    [
        "  nested: value",  # indented: nested YAML
        "- item",  # a block-list item
        "no colon here",
        ": no key",
    ],
)
def test_lines_the_flat_schema_cannot_express_are_skipped_by_default(line):
    fields, body = split_front_matter(f"---\nslug: x\n{line}\ntitle: T\n---\nbody\n")
    assert fields == {"slug": "x", "title": "T"}
    assert body == "body\n"


@pytest.mark.parametrize("line", ["  nested: value", "- item", "no colon here", ": no key"])
def test_strict_mode_raises_on_them(line):
    with pytest.raises(FrontMatterError, match="not a flat"):
        split_front_matter(f"---\nslug: x\n{line}\n---\nbody\n", strict=True)


def test_strict_mode_accepts_a_well_formed_page():
    assert split_front_matter(PAGE, strict=True) == split_front_matter(PAGE)


# -- field accessors ----------------------------------------------------------


def test_text_field_reads_scalars_only():
    fields = {"title": "T", "see_also": ["a:b"]}
    assert text_field(fields, "title") == "T"
    assert text_field(fields, "see_also") == ""  # a list is not a title
    assert text_field(fields, "missing") == ""


def test_list_field_reads_lists_and_lone_scalars():
    fields = {"see_also": ["a:b", "c:d"], "references": "flesch1948", "empty": ""}
    assert list_field(fields, "see_also") == ("a:b", "c:d")
    assert list_field(fields, "references") == ("flesch1948",)
    assert list_field(fields, "empty") == ()
    assert list_field(fields, "missing") == ()


# -- corpus lookup ------------------------------------------------------------


def _corpus(root):
    for section, slug in (("modules", "mod_x"), ("metrics", "shared"), ("concepts", "shared")):
        (root / section).mkdir(parents=True, exist_ok=True)
        (root / section / f"{slug}.md").write_text(
            f"---\nslug: {slug}\ntitle: {section}\n---\n# H\n", encoding="utf-8"
        )
    return root


def test_find_page_searches_sections_in_display_order(tmp_path):
    root = _corpus(tmp_path / "help")
    assert find_page("mod_x", root=root) == root / "modules" / "mod_x.md"
    # metrics come before concepts
    assert find_page("shared", root=root) == root / "metrics" / "shared.md"
    assert find_page("nope", root=root) is None


def test_find_page_restricted_to_one_kind(tmp_path):
    root = _corpus(tmp_path / "help")
    assert find_page("shared", "concept", root=root) == root / "concepts" / "shared.md"
    assert find_page("mod_x", "metric", root=root) is None


def test_find_page_tolerates_a_missing_section(tmp_path):
    root = tmp_path / "help"
    root.mkdir()
    assert find_page("anything", root=root) is None


def test_read_page_splits_a_file(tmp_path):
    root = _corpus(tmp_path / "help")
    fields, body = read_page(root / "modules" / "mod_x.md")
    assert fields == {"slug": "mod_x", "title": "modules"}
    assert body == "# H\n"


def test_find_page_defaults_to_the_shipped_corpus():
    page = find_page("mod_readability", "module")
    assert page is not None
    assert text_field(read_page(page)[0], "slug") == "mod_readability"
    assert help_corpus.SECTIONS == ("modules", "metrics", "concepts")


# -- body helpers -------------------------------------------------------------


def test_opens_with_title():
    assert opens_with_title("\n\n# Title\n\ntext")
    assert opens_with_title("#\n")
    assert not opens_with_title("## Section\n")
    assert not opens_with_title("#hashtag\n")
    assert not opens_with_title("text\n# Later\n")
    assert not opens_with_title("")


def test_first_paragraph_skips_headings_and_stops_at_a_blank_line():
    body = "\n# Title\n\n## Sub\n\nFirst **line**\nsecond line\n\nNext paragraph.\n"
    assert first_paragraph(body) == "First **line**\nsecond line"


def test_first_paragraph_handles_crlf_and_empty_bodies():
    assert first_paragraph("# T\r\n\r\nOne.\r\nTwo.\r\n\r\nThree.") == "One.\nTwo."
    assert first_paragraph("# Only a heading\n") == ""
    assert first_paragraph("") == ""


def test_every_shipped_module_page_has_a_title_and_a_first_paragraph():
    """What `tta module show` prints for each registered module (#78)."""
    from tta.core.modules.registry import default_registry

    for spec in (module.spec for module in default_registry().in_topological_order()):
        page = find_page(spec.name, "module")
        assert page is not None, spec.name
        fields, body = read_page(page)
        assert text_field(fields, "title"), spec.name
        paragraph = first_paragraph(body)
        assert paragraph and not paragraph.startswith("#"), spec.name
