"""Reading the help corpus: the one front-matter parser (ADR-0012 rev. 5, #78).

Every consumer of a help page reads it through this module. That covers the
GUI viewer (``ui/tk/help_view.py``), the CLI (``tta help``, ``tta module
show``) and the corpus gate (``tests/core/test_help_corpus.py``). It lives in
core because both adapters need it and the CLI may not import the UI layer
(ADR-0002, SDD Sec. 5.2). Before this module there were two parsers, which
disagreed, and the CLI had none, so ``tta help`` printed the front matter as
the page's first paragraph. ADR-0012 says front matter is parsed, never
rendered.

The module sits next to ``core/help/`` rather than inside it. That directory is
packaged content (``help/**/*.md``), and a Python module in it would turn the
corpus into a package.

The parser reads ADR-0012's flat schema and pulls in no YAML dependency: a
scalar stays a string, and a bracketed value (``[a, b]``) becomes a list. By
default it skips any line the flat schema cannot express (nested YAML), so a
contributed page written in fuller YAML still loads. ``strict=True`` raises on
such a line instead, and the gate uses it to keep the shipped corpus flat.
"""

from __future__ import annotations

import re
from importlib import resources

from tta.core.i18n import DEFAULT_LOCALE, active_locale, normalise_locale

#: Corpus layout (ADR-0012), in display order. "privacy" is deliberately
#: absent: the legal stubs under ``help/privacy/`` are not help pages.
SECTIONS = ("modules", "metrics", "concepts")
SECTION_KINDS = {"modules": "module", "metrics": "metric", "concepts": "concept"}
KIND_SECTIONS = {kind: section for section, kind in SECTION_KINDS.items()}

#: Guide pages (ADR-0012 rev. 6, #92): the GUI viewer's front pages, above
#: the three sections. An authored guide page exists per locale, as
#: ``help/guide/<locale>/<slug>.md`` - unlike the German-only sections - so
#: the cover page follows the UI language. ``privacy`` has no file: the
#: viewer generates it at view time from the ADR-0009 registry.
GUIDE_DIRECTORY = "guide"
GUIDE_KIND = "guide"
COVER_SLUG = "cover"
PRIVACY_SLUG = "privacy"
COVER_URI = f"{GUIDE_KIND}:{COVER_SLUG}"
PRIVACY_URI = f"{GUIDE_KIND}:{PRIVACY_SLUG}"
#: Guide slugs with no file: valid link targets, rendered by code.
GENERATED_GUIDE_SLUGS = (PRIVACY_SLUG,)

#: A front-matter block: ``---`` on the file's FIRST line, then everything up
#: to the next line that is ``---``. Anchored with ``\A``, so a ``---``
#: further down (a markdown thematic break) is body, never front matter.
_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_HEADING = re.compile(r"#{1,6}(?:[ \t]|\Z)")

#: Parsed front matter: field name -> scalar string or list of strings.
Metadata = dict[str, str | list[str]]


class FrontMatterError(ValueError):
    """A front-matter line the flat ADR-0012 schema cannot express (strict)."""


def split_front_matter(text: str, *, strict: bool = False) -> tuple[Metadata, str]:
    """Split a help page into its front-matter fields and its markdown body.

    A page without front matter returns ``({}, text)``. Values are strings,
    except a bracketed value, which becomes a list of its stripped, unquoted,
    non-empty items. Blank lines and ``#`` comment lines are skipped. A line
    the flat schema cannot express is skipped as well: an indented or
    ``- item`` line of nested YAML, or a line without ``key:``. With
    ``strict=True`` such a line raises :class:`FrontMatterError` instead.
    """
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}, text
    fields: Metadata = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or line[:1] in " \t-":
            if strict:
                raise FrontMatterError(
                    f"front-matter line is not a flat 'key: value' field: {line!r}"
                )
            continue
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = (item.strip().strip("\"'") for item in value[1:-1].split(","))
            fields[key.strip()] = [item for item in items if item]
        else:
            fields[key.strip()] = value.strip("\"'")
    return fields, text[match.end() :]


def text_field(fields: Metadata, key: str) -> str:
    """A scalar field, or "" when it is absent or was written as a list."""
    value = fields.get(key)
    return value if isinstance(value, str) else ""


def list_field(fields: Metadata, key: str) -> tuple[str, ...]:
    """A list field. A lone scalar counts as a one-item list; absent is ()."""
    value = fields.get(key)
    if isinstance(value, list):
        return tuple(value)
    return (value,) if value else ()


def help_root():
    """The installed help corpus root (a Traversable, works when frozen)."""
    return resources.files("tta.core") / "help"


def find_page(slug: str, kind: str | None = None, root=None):
    """The page file for ``slug``, or None if this installation has none.

    ``kind`` ("module", "metric", "concept") restricts the search to one
    section; without it the sections are searched in display order, as
    ``tta help <topic>`` does. ``root`` defaults to the packaged corpus.
    """
    root = help_root() if root is None else root
    sections = (KIND_SECTIONS[kind],) if kind else SECTIONS
    for section in sections:
        candidate = root / section / f"{slug}.md"
        if candidate.is_file():
            return candidate
    return None


def read_page(entry) -> tuple[Metadata, str]:
    """Read one page file (a Traversable or path) and split it."""
    return split_front_matter(entry.read_text(encoding="utf-8"))


def find_guide_page(slug: str, locale: str | None = None, root=None):
    """The guide page file for ``slug`` in ``locale`` (default: the active
    one), else the German page; None if neither is installed.

    The fallback is the privacy stubs' (ADR-0009): a page in the default
    language beats a missing one.
    """
    root = help_root() if root is None else root
    tag = normalise_locale(locale) or active_locale()
    for candidate in (tag, DEFAULT_LOCALE):
        page = root / GUIDE_DIRECTORY / candidate / f"{slug}.md"
        if page.is_file():
            return page
    return None


def opens_with_title(body: str) -> bool:
    """Whether the body's first non-blank line is a level-1 ``#`` heading.

    The rule for both adapters: the front-matter title is shown as the
    heading only when the body does not carry one itself.
    """
    for line in body.splitlines():
        if line.strip():
            return line.startswith("# ") or line.rstrip() == "#"
    return False


def first_paragraph(body: str) -> str:
    """The body's first block of text, skipping any leading headings.

    The block's lines are returned as they stand, joined with newlines, so a
    caller can still render the markdown in them. A body with no such block
    yields "".
    """
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        if not lines and _HEADING.match(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)
