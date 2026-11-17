"""Shared title-page parsing for the two title-page modules (SDD Sec. 7.4).

`mod_classify_thesis_type` (#9, #82, ADR-0019) and
`mod_determine_publication_year` (#17, #81, ADR-0022) both read the front
matter of `raw_text` and share this page / normalisation / cover-rule
machinery so the two heuristics stay consistent (mirrors the `_tokens.py`
shared-helper precedent).

Pages: `mod_extract_pymupdf` joins pages with a form feed, so the front matter
is read page by page. Both modules work on page windows, not on a character
cap (#81/#82 exploration: the date and the type marker sit within a few pages,
and on series reprints on page 3-4).

Cover pages (ADR-0023): a *cover rule* recognises a page that a repository
prepends on download (it is not part of the thesis). The mechanism is
rule-agnostic and its default is **no rules at all**: the shipped app never
skips a page. A researcher can load a ruleset from a file through the CLI
(`tta run --cover-rules`); the leading pages it matches are then skipped
before the title page is located, and the ruleset is recorded in the module
version and in `diagnostics`.

Kept lightweight and dependency-free: this is a keyword/regex heuristic, not ML.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field

#: Raw pages read from the start of `raw_text`. Covers (at most
#: `CoverRuleset.max_pages`) + blank pages before the title page + the
#: windows of both modules (title page + 3, own pages 0-4) fit comfortably.
LEAD_PAGES = 16

#: A page counts as the title page once it has this many non-space
#: characters (#81: blank and near-blank leading pages exist).
MIN_TITLE_PAGE_CHARS = 30

_WHITESPACE_RE = re.compile(r"\s+")
_NON_SPACE_RE = re.compile(r"\S")
#: Apostrophe variants folded away so "Bachelor's" == "bachelors". Written as
#: \uXXXX escapes so the source stays pure ASCII (ADR-0018): straight quote,
#: right/left single quote, modifier-letter apostrophe, backtick, acute accent.
_APOSTROPHES = ("'", "\u2019", "\u2018", "\u02bc", "`", "\u00b4")
#: The German eszett, folded to "ss" before accent stripping (ADR-0018).
_ESZETT = "\u00df"
#: Five or more single word characters separated by single spaces: a
#: letter-spaced heading ("m a s t e r t h e s i s") in normalised text.
_LETTER_SPACED_RE = re.compile(r"(?<!\w)(?:\w ){4,}\w(?!\w)")


def normalise(text: str) -> str:
    """Case-fold + accent/umlaut-fold so keyword matching is robust.

    Case-folds, maps the German eszett to ``ss``, drops apostrophe variants,
    strips combining marks via NFKD decomposition (so umlauts and accented
    letters compare equal to their ASCII base), and collapses runs of
    whitespace to a single space. Keyword lists must be given already in this
    normalised form.
    """
    text = text.casefold().replace(_ESZETT, "ss")
    for apostrophe in _APOSTROPHES:
        text = text.replace(apostrophe, "")
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def collapse_letter_spacing(normalised_text: str) -> str:
    """Join letter-spaced words in already-normalised text (#82).

    ``"m a s t e r t h e s i s"`` becomes ``"masterthesis"``; runs of fewer
    than five single characters ("a b c") are left alone.
    """
    return _LETTER_SPACED_RE.sub(lambda m: m.group(0).replace(" ", ""), normalised_text)


def non_space_chars(page: str) -> int:
    return len(_NON_SPACE_RE.findall(page))


#: Labels of a repository metadata block (normalised). Generic deposit
#: metadata, not one repository's layout: a page carrying at least
#: `REPOSITORY_LABELS_MIN` of them describes the deposit, not the thesis.
REPOSITORY_LABELS = ("publication date:", "permanent link:", "rights / license:")
REPOSITORY_LABELS_MIN = 2


def is_repository_metadata_page(page: str) -> bool:
    """Whether ``page`` carries a repository metadata block (ADR-0022/0019).

    Applies on the default path: evidence on such a page (a type line, the
    deposit "Publication date") is ignored. The page is **not** skipped - it
    still counts as a page for the title-page position and the windows, unlike
    a cover rule (ADR-0023).
    """
    normalised = normalise(page)
    return sum(label in normalised for label in REPOSITORY_LABELS) >= REPOSITORY_LABELS_MIN


# -- cover rules (ADR-0023) ----------------------------------------------------


@dataclass(frozen=True)
class CoverRule:
    """One kind of repository cover page, recognised by its content.

    A page matches when it contains **every** string of ``all_of`` and, if
    ``any_of`` is given, **at least one** of ``any_of``. Strings are compared
    in the form produced by :func:`normalise` (case, accents, apostrophes and
    whitespace folded), so a rule survives line breaks and case variants of
    the marker text. A rule with neither list never matches.
    """

    id: str
    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    description: str = ""

    def matches(self, normalised_page: str) -> bool:
        if not self.all_of and not self.any_of:
            return False
        if not all(normalise(s) in normalised_page for s in self.all_of):
            return False
        return not self.any_of or any(normalise(s) in normalised_page for s in self.any_of)


@dataclass(frozen=True)
class CoverRuleset:
    """A named, versioned list of cover rules (ADR-0023).

    Only *leading* pages are skipped: from the first page on, while a page
    matches any rule, and at most ``max_pages`` of them. ``source`` names the
    file the set was loaded from; it is reported but is not part of the
    fingerprint, so the same rules give the same module version wherever the
    file lives.
    """

    id: str
    version: str
    rules: tuple[CoverRule, ...]
    max_pages: int = 3
    source: str = field(default="", compare=False)

    def fingerprint(self) -> str:
        """Short content hash over everything that changes what is skipped."""
        canonical = json.dumps(
            {
                "id": self.id,
                "version": self.version,
                "max_pages": self.max_pages,
                "rules": [[r.id, list(r.all_of), list(r.any_of)] for r in self.rules],
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("ascii")).hexdigest()[:12]

    def version_suffix(self) -> str:
        """Appended to a module version (``0.3.0+covers.<id>.<hash>``), so
        runs with and without the ruleset are different versions and the
        planner re-runs a thesis when the choice changes (ADR-0023)."""
        slug = re.sub(r"[^a-z0-9]+", "-", self.id.lower()).strip("-") or "rules"
        return f"covers.{slug}.{self.fingerprint()[:8]}"

    def provenance(self) -> dict[str, object]:
        return {
            "id": self.id,
            "version": self.version,
            "fingerprint": self.fingerprint(),
            "rules": [r.id for r in self.rules],
            "source": self.source,
        }


def versioned(base_version: str, cover_rules: CoverRuleset | None) -> str:
    """A module's effective version under ``cover_rules`` (ADR-0023)."""
    if cover_rules is None:
        return base_version
    return f"{base_version}+{cover_rules.version_suffix()}"


def match_covers(pages: list[str], cover_rules: CoverRuleset | None) -> list[tuple[int, str]]:
    """``(page index, rule id)`` of every leading cover page (empty without rules)."""
    if cover_rules is None or not cover_rules.rules:
        return []
    covers: list[tuple[int, str]] = []
    for index, page in enumerate(pages[: cover_rules.max_pages]):
        normalised = normalise(page)
        rule = next((r for r in cover_rules.rules if r.matches(normalised)), None)
        if rule is None:
            break
        covers.append((index, rule.id))
    return covers


# -- the front matter ------------------------------------------------------------


@dataclass(frozen=True)
class FrontMatter:
    """The leading pages of a thesis, with any cover pages identified.

    ``pages`` are raw page texts (absolute indices); ``covers`` lists the
    skipped cover pages. ``own_start`` is the first page that belongs to the
    document itself.
    """

    pages: tuple[str, ...]
    covers: tuple[tuple[int, str], ...] = ()

    @property
    def own_start(self) -> int:
        return len(self.covers)

    def own_pages(self) -> tuple[str, ...]:
        return self.pages[self.own_start :]

    def title_page(self) -> int | None:
        """Absolute index of the title page: the first own page with at
        least ``MIN_TITLE_PAGE_CHARS`` non-space characters (#81)."""
        for index in range(self.own_start, len(self.pages)):
            if non_space_chars(self.pages[index]) >= MIN_TITLE_PAGE_CHARS:
                return index
        return None


def front_matter(
    text: str, cover_rules: CoverRuleset | None = None, max_pages: int = LEAD_PAGES
) -> FrontMatter:
    """Split the first ``max_pages`` pages off ``text`` and apply the cover rules."""
    pages = text.split("\f", max_pages)[:max_pages]
    return FrontMatter(pages=tuple(pages), covers=tuple(match_covers(pages, cover_rules)))


def cover_diagnostics(
    front: FrontMatter, cover_rules: CoverRuleset | None
) -> dict[str, object]:
    """What the cover rules did, for a module's ``diagnostics`` (ADR-0023).

    ``cover_rules`` is ``None`` on the default path (the shipped app), so a run
    with a researcher ruleset can never be mistaken for one without.
    """
    return {
        "cover_rules": None if cover_rules is None else cover_rules.provenance(),
        "cover_pages": [{"page": page, "rule": rule} for page, rule in front.covers],
    }


# -- legacy single-window helpers ---------------------------------------------
# Still used by mod_classify_thesis_type 0.2.0 until it moves to page windows
# (#82); removed in the same change.

#: Scan roughly the first page (the pre-#81/#82 window).
TITLE_PAGE_CHARS = 3000
#: Plausible four-digit years, not embedded in a longer digit run.
_YEAR_RE = re.compile(r"(?<!\d)(19\d\d|20\d\d|21\d\d)(?!\d)")


def leading_window(text: str, limit: int = TITLE_PAGE_CHARS) -> str:
    """Everything up to the first page break, capped at ``limit`` characters."""
    return text.split("\f", 1)[0][:limit]


def matched_keywords(normalised_text: str, keywords: tuple[str, ...]) -> list[str]:
    """Which of ``keywords`` occur in the already-normalised text."""
    return [kw for kw in keywords if kw in normalised_text]


def first_index_of_any(normalised_text: str, keywords: tuple[str, ...]) -> int | None:
    """Earliest start index among ``keywords`` present, or ``None``."""
    best: int | None = None
    for kw in keywords:
        idx = normalised_text.find(kw)
        if idx != -1 and (best is None or idx < best):
            best = idx
    return best


def find_years(text: str, lo: int = 1900, hi: int = 2100) -> list[int]:
    """Plausible four-digit years found in ``text``, in order of appearance."""
    return [year for year in (int(m) for m in _YEAR_RE.findall(text)) if lo <= year <= hi]
