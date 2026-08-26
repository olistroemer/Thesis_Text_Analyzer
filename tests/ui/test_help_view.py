"""Help viewer over the core help corpus (Sec. 9.4.1, ADR-0012, #72).

The loader and the markdown-subset renderer are pure and tested headless;
the window itself and the toolbar wiring need a display and are skipped
without one.

Assertions stay ASCII (ADR-0018) even though the shipped corpus is German:
the real-corpus tests key on slugs and URIs, never on rendered titles.
"""

import inspect
import os
import tkinter

import pytest

from tta.core.project import Project
from tta.ui.tk import help_view
from tta.ui.tk.help_view import (
    Block,
    Run,
    Topic,
    document_blocks,
    index_topics,
    load_topics,
    parse_inline,
    parse_uri_list,
    render_blocks,
    split_front_matter,
)

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


def test_front_matter_is_parsed_and_stripped_from_the_body():
    fields, body = split_front_matter(PAGE)
    assert fields["slug"] == "word_count"
    assert fields["title"] == "Word count"
    assert fields["kind"] == "metric"
    assert body.startswith("\n# Word count")
    assert "slug:" not in body and "see_also:" not in body


def test_page_without_front_matter_is_all_body():
    fields, body = split_front_matter("# Plain\n\ntext\n")
    assert fields == {}
    assert body == "# Plain\n\ntext\n"


def test_uri_list_keeps_only_well_formed_cross_references():
    assert parse_uri_list("[module:a, metric:b]") == ("module:a", "metric:b")
    assert parse_uri_list("[not-a-uri, concept:c]") == ("concept:c",)
    assert parse_uri_list("") == ()


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
    topics = load_topics()
    index = index_topics(topics)
    dangling = [
        run.target
        for topic in topics
        for block in render_blocks(topic.body)
        for run in block.runs
        if run.target and run.target not in index
    ]
    assert dangling == []


# -- markdown subset ----------------------------------------------------------


def test_headings_paragraphs_bullets_quotes_and_code():
    blocks = render_blocks(PAGE.split("---\n", 2)[2])
    kinds = [block.kind for block in blocks]
    assert kinds[:2] == ["h1", "p"]
    assert "li" in kinds and "quote" in kinds and "pre" in kinds
    # consecutive paragraph lines join into one wrapped block
    assert blocks[1].text.count("\n") == 0
    assert "see tokens and" in blocks[1].text
    # fenced content keeps its literal spacing, table rows survive as source
    assert "literal   spacing" in [block.text for block in blocks]
    assert "| a | b |" in [block.text for block in blocks]


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


def test_help_viewer_never_hands_a_url_to_a_browser():
    """QA-PRIV: the viewer opens no external program for help content."""
    assert "webbrowser" not in inspect.getsource(help_view)


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


def _display_available() -> bool:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        tkinter.Tk().destroy()
        return True
    except tkinter.TclError:
        return False


display_only = pytest.mark.skipif(not _display_available(), reason="no display")


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
            opened.destroy()
        finally:
            window.root.destroy()
