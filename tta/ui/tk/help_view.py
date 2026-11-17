"""Help viewer over the core help corpus (Sec. 9.4.1, ADR-0012).

Two panes: a topic tree grouped by kind on the left, the rendered page in a
read-only ``tk.Text`` on the right. Pages are read from ``tta.core/help``
through ``importlib.resources``, so the frozen single-file build works
unchanged (the PyInstaller spec bundles ``help/**/*.md``). Front matter is
split off by ``core.help_corpus``, the one parser every consumer shares
(ADR-0012 rev. 5); this module only renders.

Above the corpus sections sit two guide pages (ADR-0012 rev. 6, #92): the
cover page, authored per locale, which the viewer opens on, and the privacy
statement, generated at view time by ``core.privacy_metadata.
render_statement_md`` - the text ``tta privacy report`` prints, never a
stored copy (ADR-0009).

The renderer handles the documented markdown *subset* of Sec. 9.4.1 and
carries no extra runtime dependency (QA-RES; ADR-0012 rev. 2): headings,
paragraphs, bullets, quotes, code blocks, tables (one item per row, #92),
and the inline forms bold, italic, code and link. Footnotes and math fall
through as plain source lines. Underscore emphasis is deliberately
unsupported - identifiers like ``publication_year_source`` are pervasive
here and would emphasise their own middles.

Cross-references (``module:`` / ``metric:`` / ``concept:`` / ``guide:`` +
slug) are
clickable and navigate in place; a target with no installed page renders as
inert text, so a contributed module's page may point at a page this
installation does not have without raising. ``http`` links render as text and are never handed to a
browser (QA-PRIV). The one non-page target, ``app:third_party_licenses``
(ADR-0012 rev. 4), opens the third-party licence window (#36).
"""

from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, field
from tkinter import font as tkfont
from tkinter import ttk

from tta.core.help_corpus import (
    COVER_SLUG,
    GUIDE_KIND,
    PRIVACY_SLUG,
    SECTION_KINDS,
    SECTIONS,
    find_guide_page,
    help_root,
    list_field,
    read_page,
    text_field,
)
from tta.core.i18n import N_, _
from tta.core.privacy_metadata import render_statement_md
from tta.core.third_party_licenses import LICENSES_URI
from tta.ui.tk.columns import column_label

WINDOW_TITLE = N_("Help")
EMPTY_MESSAGE = N_("no help topics installed yet")
SEE_ALSO_HEADING = N_("See also")
# The generated guide page's tree label: the msgid of the menu entry.
PRIVACY_TITLE = N_("Privacy statement")

# Tree labels for the corpus sections (core.help_corpus.SECTIONS). The guide
# pages (cover, privacy) sit above them, at the top level of the tree.
SECTION_LABELS = {
    "modules": N_("Modules"),
    "metrics": N_("Metrics"),
    "concepts": N_("Concepts"),
}

CROSS_REF = re.compile(r"(?:module|metric|concept|guide):[A-Za-z0-9_.-]+\Z")


# -- content model ------------------------------------------------------------


@dataclass(frozen=True)
class Run:
    """An inline stretch of text with one optional style and link target."""

    text: str
    style: str = ""  # "", "bold", "italic", "mono"
    target: str = ""  # "<kind>:<slug>" for a clickable cross-reference


@dataclass(frozen=True)
class Block:
    """A rendered block: h1..h3, p, li, quote, pre."""

    kind: str
    runs: tuple[Run, ...]

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


@dataclass(frozen=True)
class Topic:
    """One help page: front-matter metadata plus the markdown body.

    A generated page (the privacy statement, #92) carries ``generate``
    instead of a body. It is called on every display, so the page is never
    a stale copy of what it renders.
    """

    kind: str
    slug: str
    title: str
    body: str
    see_also: tuple[str, ...] = ()
    generate: Callable[[], str] | None = field(default=None, compare=False)

    @property
    def uri(self) -> str:
        return f"{self.kind}:{self.slug}"

    def markdown(self) -> str:
        """The page's markdown: generated now, or the authored body."""
        return self.generate() if self.generate is not None else self.body


# -- loading ------------------------------------------------------------------

def cross_refs(items) -> tuple[str, ...]:
    """The well-formed cross-reference URIs among front-matter list items."""
    return tuple(item for item in items if CROSS_REF.match(item))


def load_topics(root=None) -> list[Topic]:
    """Load every installed help page, ordered by section then slug.

    ``root`` may be any Traversable or ``pathlib.Path``; it defaults to the
    packaged corpus. A missing section directory is not an error - it simply
    contributes nothing (the shipped corpus has all three since #2).
    """
    root = help_root() if root is None else root
    topics: list[Topic] = []
    for section in SECTIONS:
        directory = root / section
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            if not entry.name.endswith(".md"):
                continue
            fields, body = read_page(entry)
            slug = text_field(fields, "slug") or entry.name[:-3]
            topics.append(
                Topic(
                    kind=text_field(fields, "kind") or SECTION_KINDS[section],
                    slug=slug,
                    # Every shipped page carries a title (#2). A page without
                    # one - a contributed module's, say - falls back to the
                    # friendly column label (#16) and only then to the bare
                    # slug, so the tree is never blank.
                    title=text_field(fields, "title") or column_label(slug),
                    body=body,
                    see_also=cross_refs(list_field(fields, "see_also")),
                )
            )
    return topics


def guide_topics(root=None) -> list[Topic]:
    """The guide pages in tree order: the cover page in the active locale
    (German fallback), if installed, then the generated privacy statement."""
    topics: list[Topic] = []
    cover = find_guide_page(COVER_SLUG, root=root)
    if cover is not None:
        fields, body = read_page(cover)
        topics.append(
            Topic(
                kind=GUIDE_KIND,
                slug=COVER_SLUG,
                title=text_field(fields, "title") or COVER_SLUG,
                body=body,
                see_also=cross_refs(list_field(fields, "see_also")),
            )
        )
    topics.append(
        Topic(
            kind=GUIDE_KIND,
            slug=PRIVACY_SLUG,
            title=_(PRIVACY_TITLE),
            body="",
            generate=render_statement_md,
        )
    )
    return topics


def all_topics(root=None) -> list[Topic]:
    """What the viewer shows by default: the guide pages, then the corpus."""
    return guide_topics(root) + load_topics(root)


def index_topics(topics) -> dict[str, Topic]:
    return {topic.uri: topic for topic in topics}


# -- markdown subset ----------------------------------------------------------

_INLINE = re.compile(
    r"\[(?P<label>[^\]\n]+)\]\((?P<target>[^)\s]+)\)"
    r"|`(?P<mono>[^`\n]+)`"
    r"|\*\*(?P<bold>[^*\n]+)\*\*"
    r"|\*(?P<italic>[^*\n]+)\*"
)
_HEADING = re.compile(r"(#{1,6})\s+(.*)")
_BULLET = re.compile(r"[-*+]\s+(.*)")
_FENCE = re.compile(r"\s*(```|~~~)")
#: A GFM table cell separator: a pipe not escaped as ``\|``.
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_DELIMITER_CELL = re.compile(r":?-+:?\Z")


def parse_inline(line: str) -> tuple[Run, ...]:
    """Split one line into styled runs (bold, italic, code, links).

    Bold and italic are parsed again inside, so a code span or a link in an
    emphasised stretch keeps its own form instead of showing its backticks
    or brackets (the privacy statement's generation line, #92).
    """
    runs: list[Run] = []
    position = 0
    for match in _INLINE.finditer(line):
        if match.start() > position:
            runs.append(Run(line[position : match.start()]))
        position = match.end()
        if match.group("label") is not None:
            runs.append(_link_run(match.group("label"), match.group("target")))
        elif match.group("mono") is not None:
            runs.append(Run(match.group("mono"), "mono"))
        else:
            style = "bold" if match.group("bold") is not None else "italic"
            for inner in parse_inline(match.group(style)):
                runs.append(Run(inner.text, inner.style or style, inner.target))
    if position < len(line):
        runs.append(Run(line[position:]))
    return tuple(runs) or (Run(""),)


def _link_run(label: str, target: str) -> Run:
    """Cross-references stay clickable; external links become plain text.

    Handing a URL to the user's browser is a hand-off QA-PRIV does not need
    the help viewer to make, so an http link renders as "label (url)".
    """
    if CROSS_REF.match(target) or target == LICENSES_URI:
        return Run(label, target=target)
    if target.startswith(("http://", "https://")):
        return Run(f"{label} ({target})")
    return Run(label)


def _table_cells(line: str) -> list[str]:
    """The stripped cells of one GFM table row, with ``\\|`` unescaped."""
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _CELL_SPLIT.split(inner)]


def table_blocks(lines: list[str]) -> list[Block]:
    """A GFM table as one list item per body row (Sec. 9.4.1, #92).

    A row reads ``first cell - header: cell; header: cell``. Nothing needs
    aligning, the item word-wraps like prose, and every cell is
    inline-rendered, so a link in a cell stays clickable. The header and
    delimiter rows are not shown on their own: the header labels reappear
    in every row.
    """
    rows = [_table_cells(line) for line in lines]
    header: list[str] = []
    if len(rows) >= 2 and all(_DELIMITER_CELL.match(cell) for cell in rows[1] if cell):
        header, rows = rows[0], rows[2:]
    blocks: list[Block] = []
    for cells in rows:
        runs = list(parse_inline(cells[0])) if cells[0] else []
        separator = " - "
        for index, cell in enumerate(cells[1:], start=1):
            if not cell:
                continue
            runs.append(Run(separator))
            separator = "; "
            if index < len(header) and header[index]:
                label = "".join(run.text for run in parse_inline(header[index]))
                runs.append(Run(f"{label}: "))
            runs.extend(parse_inline(cell))
        if runs:
            blocks.append(Block("li", tuple(runs)))
    return blocks


def render_blocks(body: str) -> list[Block]:
    """Render the markdown subset of Sec. 9.4.1 into display blocks."""
    blocks: list[Block] = []
    paragraph: list[str] = []
    table: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Block("p", parse_inline(" ".join(paragraph))))
            paragraph.clear()
        if table:
            blocks.extend(table_blocks(table))
            table.clear()

    fenced = False
    for raw in body.splitlines():
        if _FENCE.match(raw):
            flush()
            fenced = not fenced
            continue
        if fenced:
            blocks.append(Block("pre", (Run(raw, "mono"),)))
            continue
        stripped = raw.strip()
        # A GFM table is collected row by row and rendered as a whole by
        # table_blocks once a non-table line (or the end) closes it.
        if stripped.startswith("|"):
            if paragraph:
                blocks.append(Block("p", parse_inline(" ".join(paragraph))))
                paragraph.clear()
            table.append(stripped)
            continue
        if table:
            flush()
        if not stripped:
            flush()
            continue
        if raw.startswith("    ") and not paragraph:
            blocks.append(Block("pre", (Run(raw[4:], "mono"),)))
            continue
        heading = _HEADING.match(stripped)
        if heading:
            flush()
            level = min(len(heading.group(1)), 3)
            blocks.append(Block(f"h{level}", parse_inline(heading.group(2))))
            continue
        bullet = _BULLET.match(stripped)
        if bullet:
            flush()
            blocks.append(Block("li", parse_inline(bullet.group(1))))
            continue
        if stripped.startswith(">"):
            flush()
            blocks.append(Block("quote", parse_inline(stripped.lstrip("> ").rstrip())))
            continue
        paragraph.append(stripped)
    flush()
    return blocks


def document_blocks(topic: Topic, index: dict[str, Topic] | None = None) -> list[Block]:
    """Full page: body blocks, a title if the body lacks one, "See also"."""
    index = index or {}
    blocks = render_blocks(topic.markdown())
    if not blocks or blocks[0].kind != "h1":
        blocks.insert(0, Block("h1", (Run(topic.title),)))
    if topic.see_also:
        blocks.append(Block("h2", (Run(_(SEE_ALSO_HEADING)),)))
        for uri in topic.see_also:
            target = index.get(uri)
            if target is None:
                # No installed page: inert text, never an error.
                blocks.append(Block("li", (Run(uri),)))
            else:
                blocks.append(Block("li", (Run(target.title, target=uri),)))
    return blocks


# -- window -------------------------------------------------------------------


class HelpWindow(tk.Toplevel):
    """Topic tree plus rendered page; read-only, keyboard/mouse selectable."""

    def __init__(self, parent, topics=None):
        super().__init__(parent)
        self.title(_(WINDOW_TITLE))
        self.geometry("900x640")
        self.topics = list(all_topics() if topics is None else topics)
        self.index = index_topics(self.topics)
        self.current: Topic | None = None
        self._link_targets: dict[str, str] = {}
        self._build()

    # -- construction --------------------------------------------------------

    def _build(self) -> None:
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tree_bar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_bar.set)
        tree_bar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        right = ttk.Frame(panes)
        # Body text in the proportional UI font: a bare tk.Text defaults to
        # TkFixedFont, which made every page read like source code. Fixed
        # pitch stays for code spans and blocks ("mono", "pre").
        self.text = tk.Text(
            right, wrap="word", padx=12, pady=8, cursor="arrow", font="TkTextFont"
        )
        text_bar = ttk.Scrollbar(right, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=text_bar.set)
        text_bar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        panes.add(left, weight=1)
        panes.add(right, weight=3)

        self._configure_tags()
        self._fill_tree()
        if self.topics:
            self.show_topic(self.topics[0])
        else:
            self._write([Block("p", (Run(_(EMPTY_MESSAGE)),))])

    def _configure_tags(self) -> None:
        body = tkfont.nametofont("TkTextFont")
        fixed = tkfont.nametofont("TkFixedFont")
        size = int(body.cget("size")) or 10
        heading = {
            "h1": tkfont.Font(font=body),
            "h2": tkfont.Font(font=body),
            "h3": tkfont.Font(font=body),
        }
        for name, step in (("h1", 6), ("h2", 3), ("h3", 1)):
            # A negative Tk font size is a pixel size, so "bigger" there
            # means further from zero in the other direction.
            bigger = size - step if size < 0 else size + step
            heading[name].configure(size=bigger, weight="bold")
        self._fonts = heading  # keep alive: Tk fonts are reference-counted
        self.text.tag_configure("h1", font=heading["h1"], spacing1=10, spacing3=8)
        self.text.tag_configure("h2", font=heading["h2"], spacing1=12, spacing3=5)
        self.text.tag_configure("h3", font=heading["h3"], spacing1=10, spacing3=4)
        self.text.tag_configure("p", spacing3=8)
        self.text.tag_configure("li", lmargin1=18, lmargin2=32, spacing3=3)
        self.text.tag_configure("quote", lmargin1=24, lmargin2=24, spacing3=8)
        self.text.tag_configure("pre", font=fixed, lmargin1=18, lmargin2=18, wrap="none")
        self.text.tag_configure("bold", font=tkfont.Font(font=body, weight="bold"))
        self.text.tag_configure("italic", font=tkfont.Font(font=body, slant="italic"))
        self.text.tag_configure("mono", font=fixed)
        self.text.tag_configure("link", foreground="#1a5fb4", underline=True)
        self.text.tag_bind("link", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("link", "<Leave>", lambda _e: self.text.configure(cursor="arrow"))

    def _fill_tree(self) -> None:
        # Guide pages first, at the top level (#92): the cover page is the
        # one the viewer opens on, the privacy page the menu's other target.
        for topic in self.topics:
            if topic.kind == GUIDE_KIND:
                self.tree.insert("", "end", iid=topic.uri, text=topic.title)
        for section in SECTIONS:
            kind = SECTION_KINDS[section]
            in_section = [topic for topic in self.topics if topic.kind == kind]
            if not in_section:
                continue
            parent = f"section:{kind}"
            self.tree.insert(
                "", "end", iid=parent, text=_(SECTION_LABELS[section]), open=True
            )
            for topic in in_section:
                self.tree.insert(parent, "end", iid=topic.uri, text=topic.title)

    # -- navigation ----------------------------------------------------------

    def show_topic(self, topic) -> None:
        """Render a topic (a Topic or a "<kind>:<slug>" URI) in the text pane."""
        if not isinstance(topic, Topic):
            resolved = self.index.get(str(topic))
            if resolved is None:
                return
            topic = resolved
        self.current = topic
        self._write(document_blocks(topic, self.index))
        if self.tree.exists(topic.uri) and self.tree.selection() != (topic.uri,):
            self.tree.selection_set(topic.uri)
        if topic.kind == GUIDE_KIND:
            # The guide pages head the tree; keep the whole head in view.
            self.tree.yview_moveto(0.0)
        elif self.tree.exists(topic.uri):
            self.tree.see(topic.uri)

    def _on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if selection and selection[0] in self.index:
            self.show_topic(self.index[selection[0]])

    def _follow(self, target: str) -> None:
        """Cross-reference click: navigate, or do nothing if unresolvable.
        The in-app licence target opens its own window instead (#36)."""
        if target == LICENSES_URI:
            from tta.ui.tk.licenses_view import show_third_party_licenses

            self._licenses_window = show_third_party_licenses(self)
        elif target in self.index:
            self.show_topic(self.index[target])

    # -- rendering -----------------------------------------------------------

    def _write(self, blocks) -> None:
        self.text.configure(state="normal")
        for tag in self._link_targets:
            self.text.tag_delete(tag)
        self._link_targets = {}
        self.text.delete("1.0", "end")
        for block in blocks:
            if block.kind == "li":
                self.text.insert("end", "- ", block.kind)
            for run in block.runs:
                tags = [block.kind]
                if run.style:
                    tags.append(run.style)
                if run.target:
                    tags.extend(("link", self._bind_link(run.target)))
                self.text.insert("end", run.text, tuple(tags))
            self.text.insert("end", "\n", block.kind)
        self.text.configure(state="disabled")
        self.text.yview_moveto(0.0)

    def _bind_link(self, target: str) -> str:
        tag = f"link-{len(self._link_targets)}"
        self._link_targets[tag] = target
        self.text.tag_configure(tag)
        self.text.tag_bind(tag, "<Button-1>", lambda _e, t=target: self._follow(t))
        return tag


_WINDOWS: dict[str, HelpWindow] = {}


def open_help(parent, topic=None, topics=None) -> HelpWindow:
    """Open the help viewer, raising the existing one instead of stacking.

    A fresh viewer starts on its first topic (the cover page). An open one
    is raised and focused; it changes page only when ``topic`` is given
    (Sec. 9.4.1, #92) - the Help button passes none, so the reader's page
    survives, while the privacy entry passes its page.
    """
    key = str(parent)
    window = _WINDOWS.get(key)
    try:
        alive = window is not None and bool(window.winfo_exists())
    except tk.TclError:
        alive = False
    if not alive:
        window = HelpWindow(parent, topics=topics)
        _WINDOWS[key] = window
    else:
        window.deiconify()
        window.lift()
        window.focus_force()
    if topic is not None:
        window.show_topic(topic)
    return window
