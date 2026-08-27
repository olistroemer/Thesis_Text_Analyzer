"""Help viewer over the core help corpus (Sec. 9.4.1, ADR-0012).

Two panes: a topic tree grouped by kind on the left, the rendered page in a
read-only ``tk.Text`` on the right - the same read-only text-window pattern
the privacy statement uses. Pages are read from ``tta.core/help`` through
``importlib.resources``, so the frozen single-file build works unchanged
(the PyInstaller spec bundles ``help/**/*.md``).

The renderer handles the documented markdown *subset* of Sec. 9.4.1 and
carries no extra runtime dependency (QA-RES; ADR-0012 rev. 2): headings,
paragraphs, bullets, quotes, code blocks, and the inline forms bold,
italic, code and link. Tables, footnotes and math fall through as plain
source lines. Underscore emphasis is deliberately unsupported - identifiers
like ``publication_year_source`` are pervasive here and would emphasise
their own middles.

Cross-references (``module:`` / ``metric:`` / ``concept:`` + slug) are
clickable and navigate in place; a target with no installed page renders as
inert text, because the corpus legitimately points at pages that are not
authored yet. ``http`` links render as text and are never handed to a
browser (QA-PRIV).
"""

from __future__ import annotations

import re
import tkinter as tk
from dataclasses import dataclass
from importlib import resources
from tkinter import font as tkfont
from tkinter import ttk

from tta.core.i18n import N_, _

WINDOW_TITLE = N_("Help")
EMPTY_MESSAGE = N_("no help topics installed yet")
SEE_ALSO_HEADING = N_("See also")

# Corpus layout (ADR-0012). "privacy" is deliberately absent: the privacy
# statement is not help content and keeps its own menu entry.
SECTIONS = ("modules", "metrics", "concepts")
SECTION_KINDS = {"modules": "module", "metrics": "metric", "concepts": "concept"}
SECTION_LABELS = {
    "modules": N_("Modules"),
    "metrics": N_("Metrics"),
    "concepts": N_("Concepts"),
}

CROSS_REF = re.compile(r"(?:module|metric|concept):[A-Za-z0-9_.-]+\Z")


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
    """One help page: front-matter metadata plus the markdown body."""

    kind: str
    slug: str
    title: str
    body: str
    see_also: tuple[str, ...] = ()

    @property
    def uri(self) -> str:
        return f"{self.kind}:{self.slug}"


# -- loading ------------------------------------------------------------------

_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a help page into flat front-matter fields and its body.

    Only the scalar top-level fields the viewer needs are read (title, kind,
    slug, see_also); nested YAML is skipped rather than mis-parsed, so no
    YAML dependency is pulled in for four keys.
    """
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}, text
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or line[:1] in " \t-":
            continue
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, text[match.end() :]


def parse_uri_list(value: str) -> tuple[str, ...]:
    """Parse a front-matter list of cross-reference URIs ("[a:b, c:d]")."""
    items = [item.strip().strip("\"'") for item in value.strip("[]").split(",")]
    return tuple(item for item in items if CROSS_REF.match(item))


def help_root():
    """The installed help corpus root (a Traversable, works when frozen)."""
    return resources.files("tta.core") / "help"


def load_topics(root=None) -> list[Topic]:
    """Load every installed help page, ordered by section then slug.

    ``root`` may be any Traversable or ``pathlib.Path``; it defaults to the
    packaged corpus. A missing section directory is normal (``concepts/`` does
    not exist yet) and simply contributes nothing.
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
            fields, body = split_front_matter(entry.read_text(encoding="utf-8"))
            slug = fields.get("slug") or entry.name[:-3]
            topics.append(
                Topic(
                    kind=fields.get("kind") or SECTION_KINDS[section],
                    slug=slug,
                    title=fields.get("title") or slug,
                    body=body,
                    see_also=parse_uri_list(fields.get("see_also", "")),
                )
            )
    return topics


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


def parse_inline(line: str) -> tuple[Run, ...]:
    """Split one line into styled runs (bold, italic, code, links)."""
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
        elif match.group("bold") is not None:
            runs.append(Run(match.group("bold"), "bold"))
        else:
            runs.append(Run(match.group("italic"), "italic"))
    if position < len(line):
        runs.append(Run(line[position:]))
    return tuple(runs) or (Run(""),)


def _link_run(label: str, target: str) -> Run:
    """Cross-references stay clickable; external links become plain text.

    Handing a URL to the user's browser is a hand-off QA-PRIV does not need
    the help viewer to make, so an http link renders as "label (url)".
    """
    if CROSS_REF.match(target):
        return Run(label, target=target)
    if target.startswith(("http://", "https://")):
        return Run(f"{label} ({target})")
    return Run(label)


def render_blocks(body: str) -> list[Block]:
    """Render the markdown subset of Sec. 9.4.1 into display blocks."""
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Block("p", parse_inline(" ".join(paragraph))))
            paragraph.clear()

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
        if not stripped:
            flush()
            continue
        if raw.startswith("    ") and not paragraph:
            blocks.append(Block("pre", (Run(raw[4:], "mono"),)))
            continue
        # GFM tables, footnote bodies and display math have no subset
        # rendering: they keep their source line, in fixed pitch so table
        # columns still line up.
        if stripped.startswith("|"):
            flush()
            blocks.append(Block("pre", (Run(stripped, "mono"),)))
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
    blocks = render_blocks(topic.body)
    if not blocks or blocks[0].kind != "h1":
        blocks.insert(0, Block("h1", (Run(topic.title),)))
    if topic.see_also:
        blocks.append(Block("h2", (Run(_(SEE_ALSO_HEADING)),)))
        for uri in topic.see_also:
            target = index.get(uri)
            if target is None:
                # A page #2 has not authored yet: inert, never an error.
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
        self.topics = list(load_topics() if topics is None else topics)
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
        self.text = tk.Text(right, wrap="word", padx=12, pady=8, cursor="arrow")
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
        if self.tree.exists(topic.uri):
            self.tree.see(topic.uri)

    def _on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if selection and selection[0] in self.index:
            self.show_topic(self.index[selection[0]])

    def _follow(self, target: str) -> None:
        """Cross-reference click: navigate, or do nothing if unresolvable."""
        if target in self.index:
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
    """Open the help viewer, raising the existing one instead of stacking."""
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
    if topic is not None:
        window.show_topic(topic)
    return window
