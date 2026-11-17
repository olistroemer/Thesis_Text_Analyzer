"""Help viewer over the core help corpus (Sec. 9.4.1, ADR-0012, #72).

The loader and the markdown-subset renderer are pure and tested headless;
the window itself and the toolbar wiring need a display and are skipped
without one.

Assertions stay ASCII (ADR-0018) even though the shipped corpus is German:
the real-corpus tests key on slugs and URIs, never on rendered titles.
"""

import ast
import inspect
import pathlib
import re
import tkinter

import pytest

from tta.core import help_corpus
from tta.core.help_corpus import COVER_URI, PRIVACY_URI
from tta.core.project import Project
from tta.core.third_party_licenses import LICENSES_URI
from tta.ui.tk import help_view
from tta.ui.tk.help_view import (
    Block,
    Run,
    Topic,
    all_topics,
    cross_refs,
    document_blocks,
    guide_topics,
    index_topics,
    load_topics,
    parse_inline,
    render_blocks,
)
from tests.ui.conftest import display_available

PAGE = """---
slug: word_count
title: Word count
kind: metric
produced_by: mod_surface_counts
applicability: Always: every analysed thesis has one.
see_also: [module:mod_surface_counts, module:mod_not_authored_yet]
---

# Word count

The number of **word** tokens, see [tokens](metric:token_count) and
the `mod_surface_counts` module.

## Details

- first *item*
- second item with a [dangling ref](metric:nope)
- an [external link](https://example.org/paper)

> a quoted remark

```
literal   spacing
```

| a | b |
|---|---|
| 1 | 2 |
"""


def _topic(**overrides) -> Topic:
    fields = dict(kind="metric", slug="word_count", title="Word count", body="body text")
    fields.update(overrides)
    return Topic(**fields)


def _write_corpus(root):
    (root / "metrics").mkdir(parents=True)
    (root / "modules").mkdir(parents=True)
    (root / "metrics" / "word_count.md").write_text(PAGE, encoding="utf-8")
    (root / "metrics" / "notes.txt").write_text("not a help page", encoding="utf-8")
    (root / "modules" / "mod_surface_counts.md").write_text(
        "# Surface counts\n\nCounts things.\n", encoding="utf-8"
    )
    return root


# -- front matter -------------------------------------------------------------
# The parser itself is core's (ADR-0012 rev. 5) and is unit-tested in
# tests/core/test_help_front_matter.py; here only the viewer's use of it.


def test_viewer_has_no_front_matter_parser_of_its_own():
    """#78: one parser in core; the adapter must not grow a second one."""
    assert not hasattr(help_view, "split_front_matter")
    assert not hasattr(help_view, "_FRONT_MATTER")
    assert help_view.read_page is help_corpus.read_page


def test_front_matter_is_stripped_from_the_topic_body(tmp_path):
    metric = load_topics(_write_corpus(tmp_path / "help"))[1]
    assert metric.body.startswith("\n# Word count")
    assert "slug:" not in metric.body and "see_also:" not in metric.body


def test_cross_refs_keep_only_well_formed_uris():
    assert cross_refs(["module:a", "metric:b"]) == ("module:a", "metric:b")
    assert cross_refs(["not-a-uri", "concept:c"]) == ("concept:c",)
    assert cross_refs(()) == ()


# -- loading ------------------------------------------------------------------


def test_load_topics_reads_sections_and_falls_back_to_the_filename(tmp_path):
    topics = load_topics(_write_corpus(tmp_path / "help"))
    assert [topic.uri for topic in topics] == [
        "module:mod_surface_counts",  # modules section comes first
        "metric:word_count",
    ]
    module = topics[0]
    # no front matter: kind from the directory, title from the filename
    assert module.kind == "module"
    assert module.title == "mod_surface_counts"
    assert module.see_also == ()
    metric = topics[1]
    assert metric.title == "Word count"
    assert metric.see_also == ("module:mod_surface_counts", "module:mod_not_authored_yet")


def test_missing_section_directory_is_not_an_error(tmp_path):
    root = tmp_path / "help"
    (root / "metrics").mkdir(parents=True)
    (root / "metrics" / "x.md").write_text("# X\n", encoding="utf-8")
    assert [topic.uri for topic in load_topics(root)] == ["metric:x"]


def test_empty_corpus_yields_no_topics(tmp_path):
    root = tmp_path / "help"
    root.mkdir()
    assert load_topics(root) == []


def test_shipped_corpus_loads_from_package_resources():
    """Works through importlib.resources, so the frozen build works too."""
    topics = load_topics()
    uris = {topic.uri for topic in topics}
    assert {
        "metric:thesis_type",
        "metric:publication_year",
        "metric:publication_year_source",
        "module:mod_classify_thesis_type",
        "module:mod_determine_publication_year",
    } <= uris
    # the privacy stubs are not help content and must not show up
    assert not any("stub" in uri for uri in uris)
    for topic in topics:
        assert topic.title and topic.body.strip()


def test_shipped_body_cross_references_all_resolve():
    topics = all_topics()
    index = index_topics(topics)
    dangling = [
        run.target
        for topic in topics
        for block in render_blocks(topic.markdown())
        for run in block.runs
        if run.target and run.target not in index
        and run.target != LICENSES_URI  # the in-app target, not a page (#36)
    ]
    assert dangling == []


# -- guide pages: cover and privacy (#92) ---------------------------------------


def _write_guide(root, locales=("de", "en")):
    for locale in locales:
        page = root / "guide" / locale / "cover.md"
        page.parent.mkdir(parents=True)
        page.write_text(
            f"---\nslug: cover\ntitle: Cover {locale}\nkind: guide\n---\n\n"
            f"# Tool\n\nText {locale}. See the [statement](guide:privacy).\n",
            encoding="utf-8",
        )
    return root


def test_guide_topics_are_the_cover_then_the_generated_privacy_page(tmp_path):
    topics = guide_topics(_write_guide(tmp_path / "help"))
    assert [topic.uri for topic in topics] == [COVER_URI, PRIVACY_URI]
    cover, privacy = topics
    assert cover.title == "Cover en"  # the active locale's page (tests run en)
    assert privacy.title == "Privacy statement" and privacy.body == ""


def test_the_cover_page_follows_the_locale_and_falls_back_to_german(tmp_path):
    from tta.core import i18n

    root = _write_guide(tmp_path / "both")
    i18n.install("de")
    assert guide_topics(root)[0].title == "Cover de"
    i18n.install("en")
    german_only = _write_guide(tmp_path / "de-only", locales=("de",))
    assert guide_topics(german_only)[0].title == "Cover de"


def test_without_a_cover_page_the_privacy_page_still_exists(tmp_path):
    root = tmp_path / "help"
    root.mkdir()
    assert [topic.uri for topic in guide_topics(root)] == [PRIVACY_URI]


def test_the_privacy_page_is_generated_on_every_display(monkeypatch):
    """No stored copy: each display calls the generator again (ADR-0009)."""
    calls = []

    def fake():
        calls.append(1)
        return f"# Statement {len(calls)}\n"

    monkeypatch.setattr(help_view, "render_statement_md", fake)
    (privacy,) = [t for t in guide_topics() if t.uri == PRIVACY_URI]
    assert document_blocks(privacy)[0].text == "Statement 1"
    assert document_blocks(privacy)[0].text == "Statement 2"


def test_all_topics_put_the_guide_pages_before_the_corpus():
    uris = [topic.uri for topic in all_topics()]
    assert uris[:2] == [COVER_URI, PRIVACY_URI]
    assert "metric:yules_k" in uris


_MARKERS = ("**", "`", "|", "](")
_WORD = re.compile(r"[^\W_]+")
_TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d")


def _privacy_page():
    (privacy,) = [topic for topic in all_topics() if topic.uri == PRIVACY_URI]
    return privacy


@pytest.mark.parametrize("locale", ["de", "en"])
def test_the_privacy_page_renders_without_raw_markdown_markers(locale):
    """#92: the statement used to show `#`, `**` and `|` tables verbatim."""
    from tta.core import i18n

    i18n.install(locale)
    blocks = document_blocks(_privacy_page())
    leftovers = [
        block.text
        for block in blocks
        if block.text.lstrip().startswith(("#", "- ", "* ", "> "))
        or any(marker in block.text for marker in _MARKERS)
    ]
    assert leftovers == []
    assert "pre" not in {block.kind for block in blocks}  # no fixed-pitch source
    # every markdown heading became a heading block, sections 1-7 included
    markdown = _privacy_page().markdown()
    headings = [line for line in markdown.splitlines() if line.startswith("#")]
    assert len([b for b in blocks if b.kind in ("h1", "h2", "h3")]) == len(headings)
    assert sum(1 for line in headings if re.match(r"## [1-7]\. ", line)) == 7


def _words(text):
    return set(_WORD.findall(text))


@pytest.mark.parametrize("locale", ["de", "en"])
def test_the_privacy_page_says_what_tta_privacy_report_says(locale, tmp_path):
    """#92: content identical to `tta privacy report`. The markdown is the
    CLI's output byte for byte (generation timestamp aside), and rendering
    loses no word of it except the first column's header label, which the
    row items do not repeat."""
    import os
    import subprocess
    import sys

    from tta.core import i18n

    repo = pathlib.Path(__file__).resolve().parents[2]
    env = dict(os.environ, TTA_LOCALE=locale, PYTHONPATH=str(repo), PYTHONIOENCODING="utf-8")
    cli = subprocess.run(
        [sys.executable, "-m", "tta.cli.main", "privacy", "report"],
        capture_output=True, encoding="utf-8", check=True, cwd=str(tmp_path), env=env,
    ).stdout
    i18n.install(locale)
    page = _privacy_page()
    markdown = page.markdown()
    assert _TIMESTAMP.sub("T", cli).rstrip("\n") == _TIMESTAMP.sub("T", markdown).rstrip("\n")

    rendered = " ".join(block.text for block in document_blocks(page))
    lines = markdown.splitlines()
    first_column_headers = {
        lines[i].strip("|").split("|")[0]
        for i in range(len(lines) - 1)
        if lines[i].startswith("|") and lines[i + 1].startswith("|---")
    }
    allowed = set().union(*(_words(header) for header in first_column_headers))
    assert _words(markdown) - _words(rendered) <= allowed
    assert _words(rendered) <= _words(markdown)


# -- markdown subset ----------------------------------------------------------


def test_headings_paragraphs_bullets_quotes_and_code():
    blocks = render_blocks(PAGE.split("---\n", 2)[2])
    kinds = [block.kind for block in blocks]
    assert kinds[:2] == ["h1", "p"]
    assert "li" in kinds and "quote" in kinds and "pre" in kinds
    # consecutive paragraph lines join into one wrapped block
    assert blocks[1].text.count("\n") == 0
    assert "see tokens and" in blocks[1].text
    # fenced content keeps its literal spacing; a table row becomes an item
    # that names its columns (#92), and no pipe survives
    assert "literal   spacing" in [block.text for block in blocks]
    assert Block("li", (Run("1"), Run(" - "), Run("b: "), Run("2"))) in blocks
    assert not any("|" in block.text for block in blocks)


def test_a_table_renders_one_item_per_row_with_its_header_labels():
    """Sec. 9.4.1 (#92): no column alignment, no pipes, inline-rendered
    cells - a link in a cell stays a link, an escaped pipe is a pipe."""
    blocks = render_blocks(
        "intro line\n"
        "| Metric | German | English |\n"
        "|:---|---:|---|\n"
        "| [ttr](metric:ttr) | 0,20 | `a\\|b` |\n"
        "| plain |  | 0,12 |\n"
        "after\n"
    )
    assert [block.kind for block in blocks] == ["p", "li", "li", "p"]
    first, second = blocks[1], blocks[2]
    assert first.runs == (
        Run("ttr", target="metric:ttr"),
        Run(" - "),
        Run("German: "),
        Run("0,20"),
        Run("; "),
        Run("English: "),
        Run("a|b", "mono"),
    )
    # an empty cell is skipped, the separator follows the cells shown
    assert second.text == "plain - English: 0,12"


def test_a_table_without_a_delimiter_row_has_no_header_labels():
    (block,) = render_blocks("| x | y |\n")
    assert block == Block("li", (Run("x"), Run(" - "), Run("y")))


def test_code_inside_emphasis_keeps_its_own_form():
    """The statement's generation line is italic around a code span (#92)."""
    runs = parse_inline("*Generated by `core/privacy_metadata.py`.*")
    assert runs == (
        Run("Generated by ", "italic"),
        Run("core/privacy_metadata.py", "mono"),
        Run(".", "italic"),
    )
    (link,) = parse_inline("**[ttr](metric:ttr)**")
    assert link == Run("ttr", "bold", "metric:ttr")


def test_deep_headings_clamp_to_h3():
    assert [b.kind for b in render_blocks("#### deep\n")] == ["h3"]


def test_inline_styles():
    runs = parse_inline("plain **bold** and *italic* and `code`")
    assert runs == (
        Run("plain "),
        Run("bold", "bold"),
        Run(" and "),
        Run("italic", "italic"),
        Run(" and "),
        Run("code", "mono"),
    )


def test_underscored_identifiers_are_not_emphasised():
    (run,) = parse_inline("publication_year_source is one word")
    assert run == Run("publication_year_source is one word")


def test_cross_reference_links_carry_their_target():
    runs = parse_inline("see [tokens](metric:token_count) now")
    assert runs[1] == Run("tokens", target="metric:token_count")


def test_external_links_render_as_text_and_are_never_clickable():
    runs = parse_inline("[paper](https://example.org/p)")
    assert runs == (Run("paper (https://example.org/p)"),)


def _imported_modules(module) -> set:
    """Top-level module names imported anywhere in a module's source."""
    names = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_help_viewer_never_hands_a_url_to_a_browser():
    """QA-PRIV: the viewer opens no external program for help content."""
    assert "webbrowser" not in _imported_modules(help_view)


# -- document assembly --------------------------------------------------------


def test_document_prepends_a_title_only_when_the_body_lacks_one():
    with_h1 = document_blocks(_topic(body="# Own title\n\ntext\n"))
    assert with_h1[0] == Block("h1", (Run("Own title"),))
    without = document_blocks(_topic(body="text only\n"))
    assert without[0] == Block("h1", (Run("Word count"),))


def test_see_also_block_links_resolvable_refs_and_inerts_the_rest():
    topic = _topic(see_also=("module:mod_surface_counts", "module:gone"))
    index = {"module:mod_surface_counts": _topic(kind="module", slug="mod_surface_counts",
                                                title="Surface counts")}
    blocks = document_blocks(topic, index)
    assert blocks[-3] == Block("h2", (Run("See also"),))
    assert blocks[-2] == Block("li", (Run("Surface counts", target="module:mod_surface_counts"),))
    assert blocks[-1] == Block("li", (Run("module:gone"),))  # inert, not an error


# -- window (needs a display) -------------------------------------------------


display_only = pytest.mark.skipif(not display_available(), reason="no display")


@pytest.fixture
def root():
    window = tkinter.Tk()
    yield window
    window.destroy()


@pytest.fixture
def corpus(tmp_path):
    return load_topics(_write_corpus(tmp_path / "help"))


@display_only
def test_window_lists_topics_by_section_and_renders_the_first(root, corpus):
    window = help_view.HelpWindow(root, topics=corpus)
    try:
        root.update_idletasks()
        assert window.title() == "Help"
        assert set(window.tree.get_children("")) == {"section:module", "section:metric"}
        assert window.tree.get_children("section:metric") == ("metric:word_count",)
        assert window.current.uri == "module:mod_surface_counts"
        assert "Counts things." in window.text.get("1.0", "end")
        assert str(window.text["state"]) == "disabled"
    finally:
        window.destroy()


@display_only
def test_tree_selection_and_cross_reference_clicks_navigate(root, corpus):
    window = help_view.HelpWindow(root, topics=corpus)
    try:
        window.tree.selection_set("metric:word_count")
        root.update()
        assert window.current.uri == "metric:word_count"
        rendered = window.text.get("1.0", "end")
        assert "Word count" in rendered
        # the See also entry for the authored module is a bound link
        targets = set(window._link_targets.values())
        assert "module:mod_surface_counts" in targets
        assert "metric:nope" in targets  # bound but unresolvable
        # following the resolvable one navigates and syncs the tree
        window._follow("module:mod_surface_counts")
        root.update()
        assert window.current.uri == "module:mod_surface_counts"
        assert window.tree.selection() == ("module:mod_surface_counts",)
        # following a dangling ref is a no-op, not a traceback
        window._follow("metric:nope")
        root.update()
        assert window.current.uri == "module:mod_surface_counts"
    finally:
        window.destroy()


@display_only
def test_empty_corpus_shows_the_placeholder(root):
    window = help_view.HelpWindow(root, topics=[])
    try:
        root.update_idletasks()
        assert help_view.EMPTY_MESSAGE in window.text.get("1.0", "end")
        assert window.tree.get_children("") == ()
    finally:
        window.destroy()


@display_only
def test_open_help_raises_the_existing_window_instead_of_stacking(root, corpus):
    first = help_view.open_help(root, topics=corpus)
    try:
        second = help_view.open_help(root, topics=corpus, topic="metric:word_count")
        assert second is first
        assert second.current.uri == "metric:word_count"
    finally:
        first.destroy()
    # after it is gone a fresh one is created
    third = help_view.open_help(root, topics=corpus)
    try:
        assert third is not first
    finally:
        third.destroy()


@display_only
def test_toolbar_help_button_opens_help_not_the_privacy_statement(tmp_path):
    """#72's acceptance criterion, on the real MainWindow toolbar."""
    from tta.ui.tk.main_window import MainWindow

    with Project.open(tmp_path / "proj", create=True) as project:
        window = MainWindow(project)
        try:
            window.root.update_idletasks()
            window._toolbar_buttons["? Help"].invoke()
            window.root.update_idletasks()
            opened = window._help_window
            assert isinstance(opened, help_view.HelpWindow)
            assert opened.title() == "Help"
            assert opened.topics, "the shipped corpus must be reachable from the GUI"
            # #92: it opens on the cover page, which heads the tree
            assert opened.current.uri == COVER_URI
            assert opened.tree.get_children("")[:2] == (COVER_URI, PRIVACY_URI)
            assert opened.tree.selection() == (COVER_URI,)
            opened.destroy()
        finally:
            window.root.destroy()


@display_only
def test_the_cover_page_links_to_the_privacy_page(root):
    window = help_view.HelpWindow(root)
    try:
        root.update_idletasks()
        assert window.current.uri == COVER_URI
        assert PRIVACY_URI in window._link_targets.values()
        window._follow(PRIVACY_URI)
        root.update()
        assert window.current.uri == PRIVACY_URI
        assert window.tree.selection() == (PRIVACY_URI,)
        shown = window.text.get("1.0", "end")
        assert "7. Publisher and contact" in shown
        assert "## " not in shown and "|" not in shown
    finally:
        window.destroy()


def test_the_in_app_licence_link_is_clickable_and_no_other_app_target_is():
    """ADR-0012 rev. 4 (#36): `app:third_party_licenses` is a live target,
    any other non-page target stays inert."""
    (run,) = parse_inline(f"[Lizenzen]({LICENSES_URI})")
    assert run.target == LICENSES_URI
    (other,) = parse_inline("[x](app:something_else)")
    assert other.target == ""
