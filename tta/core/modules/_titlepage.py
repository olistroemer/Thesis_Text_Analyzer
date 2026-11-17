"""Shared title-page parsing for the two title-page modules (SDD Sec. 7.4).

`mod_classify_thesis_type` (#9, #82, ADR-0019) and
`mod_determine_publication_year` (#17, #81, ADR-0022) both read the front
matter of `raw_text` and share this page / normalisation / ruleset machinery
so the two heuristics stay consistent (mirrors the `_tokens.py` shared-helper
precedent).

Pages: `mod_extract_pymupdf` joins pages with a form feed, so the front matter
is read page by page. Both modules work on page windows, not on a character
cap (#81/#82 exploration: the date and the type marker sit within a few pages,
and on series reprints on page 3-4).

Researcher rulesets (ADR-0023): rules derived from a particular repository's
layout - a cover page it prepends on download, a metadata page, a form whose
text lists every paper type - are **never** part of the shipped app. The
mechanism here is rule-agnostic and its default is **no rules at all**: without
a ruleset the thesis text is processed unmodified. A researcher can load a
ruleset file through the CLI (`tta run --cover-rules FILE`); it may skip
leading cover pages and mark pages, date cues and passages as "not evidence".
The ruleset is recorded in the module version and in `diagnostics`.

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


# -- researcher rulesets (ADR-0023) --------------------------------------------


@dataclass(frozen=True)
class CoverRule:
    """A page rule: recognises a kind of page by its content.

    A page matches when it contains **every** string of ``all_of`` and at
    least ``min_any`` (default 1) of ``any_of`` (when ``any_of`` is given).
    Strings are compared in the form produced by :func:`normalise` (case,
    accents, apostrophes and whitespace folded), so a rule survives line
    breaks and case variants of the text. A rule with neither list never
    matches.
    """

    id: str
    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    min_any: int = 1
    description: str = ""

    def matches(self, normalised_page: str) -> bool:
        if not self.all_of and not self.any_of:
            return False
        if not all(normalise(s) in normalised_page for s in self.all_of):
            return False
        if not self.any_of:
            return True
        return sum(normalise(s) in normalised_page for s in self.any_of) >= self.min_any


@dataclass(frozen=True)
class PatternRule:
    """A text rule: a regular expression whose matches are not evidence.

    Used for extra date cues (matched case-insensitively on the raw text
    before a date, like the built-in cues) and for type-marker passages
    (matched on the normalised window; markers inside the match and up to
    ``tail`` characters after it do not count).
    """

    id: str
    pattern: str
    tail: int = 0
    description: str = ""


@dataclass(frozen=True)
class CoverRuleset:
    """A named, versioned researcher ruleset (ADR-0023).

    - ``covers``: leading pages to skip - from the first page on, while a page
      matches a rule, at most ``max_pages`` of them.
    - ``not_evidence_pages``: pages that are kept (they still count for
      positions and windows) but supply no date candidate and no type marker.
    - ``date_cues``: extra negative cues for the date rules.
    - ``type_passages``: passages whose type markers do not count.

    ``source`` names the file the set was loaded from; it is reported but is
    not part of the fingerprint, so the same rules give the same module version
    wherever the file lives.
    """

    id: str
    version: str
    covers: tuple[CoverRule, ...] = ()
    not_evidence_pages: tuple[CoverRule, ...] = ()
    date_cues: tuple[PatternRule, ...] = ()
    type_passages: tuple[PatternRule, ...] = ()
    max_pages: int = 3
    source: str = field(default="", compare=False)

    def rule_ids(self) -> list[str]:
        return [
            r.id
            for group in (self.covers, self.not_evidence_pages, self.date_cues, self.type_passages)
            for r in group
        ]

    def fingerprint(self) -> str:
        """Short content hash over everything that changes what is read."""

        def pages(rules):
            return [[r.id, list(r.all_of), list(r.any_of), r.min_any] for r in rules]

        def patterns(rules):
            return [[r.id, r.pattern, r.tail] for r in rules]

        canonical = json.dumps(
            {
                "id": self.id,
                "version": self.version,
                "max_pages": self.max_pages,
                "covers": pages(self.covers),
                "not_evidence_pages": pages(self.not_evidence_pages),
                "date_cues": patterns(self.date_cues),
                "type_passages": patterns(self.type_passages),
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
            "rules": self.rule_ids(),
            "source": self.source,
        }


def versioned(base_version: str, rules: CoverRuleset | None) -> str:
    """A module's effective version under ``rules`` (ADR-0023)."""
    if rules is None:
        return base_version
    return f"{base_version}+{rules.version_suffix()}"


def _first_match(rules: tuple[CoverRule, ...], normalised_page: str) -> str | None:
    rule = next((r for r in rules if r.matches(normalised_page)), None)
    return None if rule is None else rule.id


def match_covers(pages: list[str], rules: CoverRuleset | None) -> list[tuple[int, str]]:
    """``(page index, rule id)`` of every leading cover page (empty without rules)."""
    if rules is None or not rules.covers:
        return []
    covers: list[tuple[int, str]] = []
    for index, page in enumerate(pages[: rules.max_pages]):
        rule_id = _first_match(rules.covers, normalise(page))
        if rule_id is None:
            break
        covers.append((index, rule_id))
    return covers


def match_not_evidence(pages: list[str], rules: CoverRuleset | None) -> list[tuple[int, str]]:
    """``(page index, rule id)`` of every page that supplies no evidence."""
    if rules is None or not rules.not_evidence_pages:
        return []
    found = []
    for index, page in enumerate(pages):
        rule_id = _first_match(rules.not_evidence_pages, normalise(page))
        if rule_id is not None:
            found.append((index, rule_id))
    return found


# -- the front matter ------------------------------------------------------------


@dataclass(frozen=True)
class FrontMatter:
    """The leading pages of a thesis, with any ruleset findings.

    ``pages`` are raw page texts (absolute indices); ``covers`` lists the
    skipped cover pages, ``not_evidence`` the kept pages that supply no
    evidence. ``own_start`` is the first page that belongs to the document
    itself. Without a ruleset both lists are empty.
    """

    pages: tuple[str, ...]
    covers: tuple[tuple[int, str], ...] = ()
    not_evidence: tuple[tuple[int, str], ...] = ()

    @property
    def own_start(self) -> int:
        return len(self.covers)

    def own_pages(self) -> tuple[str, ...]:
        return self.pages[self.own_start :]

    def not_evidence_rule(self, index: int) -> str | None:
        """The rule id marking absolute page ``index`` as not evidence, if any."""
        return dict(self.not_evidence).get(index)

    def title_page(self) -> int | None:
        """Absolute index of the title page: the first own page with at
        least ``MIN_TITLE_PAGE_CHARS`` non-space characters (#81)."""
        for index in range(self.own_start, len(self.pages)):
            if non_space_chars(self.pages[index]) >= MIN_TITLE_PAGE_CHARS:
                return index
        return None


def front_matter(
    text: str, rules: CoverRuleset | None = None, max_pages: int = LEAD_PAGES
) -> FrontMatter:
    """Split the first ``max_pages`` pages off ``text`` and apply ``rules``."""
    pages = text.split("\f", max_pages)[:max_pages]
    covers = match_covers(pages, rules)
    not_evidence = [
        (index, rule_id)
        for index, rule_id in match_not_evidence(pages, rules)
        if index >= len(covers)
    ]
    return FrontMatter(pages=tuple(pages), covers=tuple(covers), not_evidence=tuple(not_evidence))


def cover_diagnostics(front: FrontMatter, rules: CoverRuleset | None) -> dict[str, object]:
    """What the researcher ruleset did, for a module's ``diagnostics`` (ADR-0023).

    ``cover_rules`` is ``None`` on the default path (the shipped app), so a run
    with a researcher ruleset can never be mistaken for one without.
    """
    return {
        "cover_rules": None if rules is None else rules.provenance(),
        "cover_pages": [{"page": page, "rule": rule} for page, rule in front.covers],
        "not_evidence_pages": [{"page": page, "rule": rule} for page, rule in front.not_evidence],
    }
