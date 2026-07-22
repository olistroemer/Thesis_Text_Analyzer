"""Shared title-page parsing for the two title-page modules (SDD Sec. 7.4).

`mod_classify_thesis_type` (#9, ADR-0019) and `mod_determine_publication_year`
(#17) both read the leading window of `raw_text` - the title page - and share
this normalisation / keyword / year machinery so the two heuristics stay
consistent (mirrors the `_tokens.py` shared-helper precedent).

Kept lightweight and dependency-free: this is a keyword/regex heuristic, not ML.
"""

from __future__ import annotations

import re
import unicodedata

#: Scan roughly the first page. `mod_extract_pymupdf` joins pages with a form
#: feed, so the first page is usually the title page (SDD Sec. 7.4).
TITLE_PAGE_CHARS = 3000

_WHITESPACE_RE = re.compile(r"\s+")
#: Apostrophe variants folded away so "Bachelor's" == "bachelors". Written as
#: \uXXXX escapes so the source stays pure ASCII (ADR-0018): straight quote,
#: right/left single quote, modifier-letter apostrophe, backtick, acute accent.
_APOSTROPHES = ("'", "\u2019", "\u2018", "\u02bc", "`", "\u00b4")
#: The German eszett, folded to "ss" before accent stripping (ADR-0018).
_ESZETT = "\u00df"
#: Plausible four-digit years, not embedded in a longer digit run.
_YEAR_RE = re.compile(r"(?<!\d)(19\d\d|20\d\d|21\d\d)(?!\d)")


def leading_window(text: str, limit: int = TITLE_PAGE_CHARS) -> str:
    """The title-page window: everything up to the first page break, capped
    at ``limit`` characters."""
    return text.split("\f", 1)[0][:limit]


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


def matched_keywords(normalised_text: str, keywords: tuple[str, ...]) -> list[str]:
    """Which of ``keywords`` occur in the already-normalised text."""
    return [kw for kw in keywords if kw in normalised_text]


def first_index_of_any(normalised_text: str, keywords: tuple[str, ...]) -> int | None:
    """Earliest start index among ``keywords`` present, or ``None`` if none
    occur. Lets callers break ties by which marker appears first on the page."""
    best: int | None = None
    for kw in keywords:
        idx = normalised_text.find(kw)
        if idx != -1 and (best is None or idx < best):
            best = idx
    return best


def find_years(text: str, lo: int = 1900, hi: int = 2100) -> list[int]:
    """Plausible four-digit years found in ``text``, in order of appearance."""
    return [year for year in (int(m) for m in _YEAR_RE.findall(text)) if lo <= year <= hi]
