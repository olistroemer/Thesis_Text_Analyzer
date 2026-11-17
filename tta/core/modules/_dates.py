"""Date rules for `mod_determine_publication_year` (#81, ADR-0022).

Ported from the #81 exploration (title-page dates of the reference corpus).
The rule catalogue - every matched form and every exclusion, each with a
corpus example - is `docs/titlepage-rules.md`; this module implements its
"date rules v1".

Works on the raw (not normalised) page text: the patterns need the case of
the semester abbreviations ("SS 2014" vs "ss") and the umlaut/OCR variants of
month names ("M\u00e4rz", "Maerz", "Marz", "M\u00a8arz"). Non-ASCII characters are
written as \\uXXXX escapes (ADR-0018).

Outline:

1. ``candidates`` finds every date-like string on a page (one candidate per
   character span, the most specific form wins).
2. ``annotate`` attaches the context: cue words before it on the same line or
   on a label line ending in ":" directly above (negative cues never cross
   further lines), range starts, citations, standalone/imprint positions.
3. ``rejection`` applies the exclusions and the restrictions on bare years and
   on dates after the title page.
4. ``pick`` walks the window page by page: the first page with a valid
   candidate decides; a submission-cued date wins, else the most precise
   (day/month > semester > year), the earliest on ties.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# -- month names (German, English, Italian; OCR/LaTeX variants) ----------------
# French month names occur in the corpus only in reference lists, so they are
# deliberately absent ("mars" would also hit the planet).
_MONTHS = {
    1: ("januar", "j\u00e4nner", "january", "gennaio", "jan"),
    2: ("februar", "february", "febbraio", "feb"),
    3: ("m\u00e4rz", "maerz", "marz", "m\u00a8arz", "march", "marzo", "mar", "m\u00e4r", "mrz"),
    4: ("april", "aprile", "apr"),
    5: ("mai", "may", "maggio"),
    6: ("juni", "june", "giugno", "jun"),
    7: ("juli", "july", "luglio", "jul"),
    8: ("august", "agosto", "aug"),
    9: ("september", "settembre", "sept", "sep"),
    10: ("oktober", "october", "ottobre", "okt", "oct"),
    11: ("november", "novembre", "nov"),
    12: ("dezember", "december", "dicembre", "dez", "dec"),
}
MONTH_NUMBER = {word: number for number, words in _MONTHS.items() for word in words}
_MONTH_WORDS = sorted(MONTH_NUMBER, key=len, reverse=True)
MONTH = (
    r"(?<![A-Za-z\u00c0-\u00ff])(?:"
    + "|".join(re.escape(w) for w in _MONTH_WORDS)
    + r")(?![a-z\u00e0-\u00ff])\.?"
)
YEAR = r"(?:19\d\d|20[0-3]\d)"
SEMESTER = (
    r"(?:(?i:Sommersemester|Wintersemester|Sommer-?\s?semester|Winter-?\s?semester|"
    r"Herbstsemester|Fr\u00fchjahrssemester|Fr\u00fchlingssemester)|SoSe|WiSe|SS|WS|HS|FS)"
)
SEASON = (
    r"(?:Spring|Summer|Fall|Autumn|Winter|Fr\u00fchjahr|Fr\u00fchling|Sommer|Herbst)"
    r"(?:\s+(?:Term|Semester|semester|term))?"
)

# Ordered: most specific first. Every pattern contains a year.
_PATTERNS = (
    ("iso_ymd", rf"(?<![\d-]){YEAR}-[01]\d-[0-3]\d(?!\d)", 0),
    ("num_dmy", rf"(?<![\d.])[0-3]?\d\s?\.\s?[01]?\d\s?\.\s?{YEAR}(?!\d)", 0),
    ("ymd_slash", rf"(?<![\d/]){YEAR}/[01]\d/[0-3]\d(?!\d)", 0),
    ("num_dmy_slash", rf"(?<![\d/])[0-3]?\d\s?/\s?[0-3]?\d\s?/\s?{YEAR}(?!\d)", 0),
    ("num_dmy_dash", rf"(?<![\d-])[0-3]?\d-[01]?\d-{YEAR}(?!\d)", 0),
    ("d_month_y", rf"(?<!\d)[0-3]?\d(?:\.|th|st|nd|rd)?\s*(?:of\s+)?{MONTH},?\s*{YEAR}(?!\d)", re.I),
    ("month_d_y", rf"{MONTH},?\s*[0-3]?\d(?:th|st|nd|rd)?\.?,?\s+{YEAR}(?!\d)", re.I),
    ("month_y", rf"{MONTH},?\s*{YEAR}(?!\d)", re.I),
    ("iso_ym", rf"(?<![\d-]){YEAR}-[01]\d(?![\d-])", 0),
    ("num_my", rf"(?<![\d./])[01]?\d\s?[./]\s?{YEAR}(?!\d)", 0),
    ("semester", rf"{SEMESTER}\.?\s*{YEAR}(?:\s?/\s?(?:\d\d|{YEAR}))?(?!\d)", 0),
    ("semester2", rf"(?<![A-Za-z]){SEMESTER}\.?\s*\d\d\s?/\s?\d\d(?!\d)", 0),
    ("season", rf"(?<![A-Za-z]){SEASON}\s+{YEAR}(?!\d)", re.I),
    ("acad", rf"(?<![\d./-]){YEAR}\s?/\s?(?:{YEAR}|\d\d)(?!\d)", 0),
    ("year", rf"(?<![\d.,/-]){YEAR}(?![\d])", 0),
)
PATTERNS = tuple((name, re.compile(rx, flags)) for name, rx, flags in _PATTERNS)

#: Precision levels stored in `publication_date_precision` (ADR-0022).
DAY, MONTH_PRECISION, SEMESTER_PRECISION, YEAR_PRECISION, YEAR_RANGE = (
    "day",
    "month",
    "semester",
    "year",
    "year_range",
)
PRECISION = {
    "iso_ymd": DAY,
    "ymd_slash": DAY,
    "num_dmy": DAY,
    "num_dmy_slash": DAY,
    "num_dmy_dash": DAY,
    "d_month_y": DAY,
    "month_d_y": DAY,
    "month_y": MONTH_PRECISION,
    "iso_ym": MONTH_PRECISION,
    "num_my": MONTH_PRECISION,
    "semester": SEMESTER_PRECISION,
    "semester2": SEMESTER_PRECISION,
    "season": SEMESTER_PRECISION,
    "acad": YEAR_RANGE,
    "year": YEAR_PRECISION,
}
#: Within a page: day/month dates beat a semester, a semester beats a year.
_RANK = {DAY: 0, MONTH_PRECISION: 0, SEMESTER_PRECISION: 1, YEAR_RANGE: 2, YEAR_PRECISION: 2}
#: Forms that are a bare year (or academic-year / month-year number) and need
#: an extra positional reason to count (rule "bare years").
_BARE_FORMS = ("year", "acad", "num_my")
_TERM_FORMS = ("semester", "semester2", "season")
_WINTER_RE = re.compile(r"(?i)^(winter|ws|wise)")


@dataclass
class Candidate:
    start: int
    end: int
    form: str
    surface: str
    year: int
    month: int | None
    day: int | None
    page: int = 0  # relative to the title page
    cues: set[str] = field(default_factory=set)
    range_start: bool = False
    citation: bool = False
    standalone: bool = False
    line_final: bool = False
    title_prep: bool = False
    place_prefix: bool = False
    alone: bool = False

    @property
    def precision(self) -> str:
        return PRECISION[self.form]

    @property
    def reported_year(self) -> int:
        """Winter semester/term -> its end year; everything else as stated."""
        if self.form in _TERM_FORMS and _WINTER_RE.match(self.surface):
            return self.year + 1
        return self.year

    def iso(self) -> str:
        """The stated date at its own precision (``2014``, ``2014-05``, ``2014-05-12``)."""
        if self.month is None:
            return str(self.reported_year)
        if self.day is None:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


def _parse(form: str, surface: str) -> tuple[int, int | None, int | None] | None:
    """(year, month, day) from the surface; month/day ``None`` if absent."""
    if form == "semester2":
        yy = int(re.search(r"(\d\d)\s?/", surface).group(1))
        return (1900 + yy if yy > 40 else 2000 + yy), None, None
    year = int(re.findall(YEAR, surface)[0])
    if form == "acad":
        # the end of an academic year "2004/05" / "2004/2005"
        tail = re.search(r"/\s?(\d+)$", surface).group(1)
        year = int(tail) if len(tail) == 4 else int(str(year)[:2] + tail)
        return year, None, None
    month = day = None
    if form == "iso_ymd":
        _, month, day = (int(x) for x in surface.split("-"))
    elif form == "iso_ym":
        month = int(surface.split("-")[1])
    elif form in ("num_dmy", "num_dmy_dash"):
        parts = [int(x) for x in re.findall(r"\d+", surface)]
        day, month = parts[0], parts[1]
    elif form == "ymd_slash":
        _, month, day = (int(x) for x in surface.split("/"))
    elif form == "num_dmy_slash":
        a, b, _ = (int(x) for x in re.findall(r"\d+", surface))
        day, month = (a, b) if b <= 12 else (b, a)  # US M/D/YYYY when the 2nd is > 12
    elif form == "num_my":
        month = int(re.findall(r"\d+", surface)[0])
    elif form in ("d_month_y", "month_d_y", "month_y"):
        word = re.search(MONTH, surface, re.I).group(0).rstrip(".").lower()
        month = MONTH_NUMBER.get(word)
        if form != "month_y":
            numbers = [int(x) for x in re.findall(r"\d+", surface) if len(x) <= 2]
            day = numbers[0] if numbers else None
    if month is not None and not 1 <= month <= 12:
        return None
    if day is not None and not 1 <= day <= 31:
        return None
    return year, month, day


def candidates(text: str) -> list[Candidate]:
    """Every date-like string in ``text``; a character span is covered by at
    most one candidate (the most specific form wins)."""
    taken: list[tuple[int, int]] = []
    found: list[Candidate] = []
    for name, rx in PATTERNS:
        for match in rx.finditer(text):
            start, end = match.span()
            if any(start < t_end and t_start < end for t_start, t_end in taken):
                continue
            parsed = _parse(name, match.group(0))
            if parsed is None:
                continue
            taken.append((start, end))
            found.append(Candidate(start, end, name, match.group(0), *parsed))
    found.sort(key=lambda c: c.start)
    return found


# -- context cues --------------------------------------------------------------
_U = "[u\u00fc]"
CUES = {
    # exclusions (negative cues)
    "birth": r"(geboren|geb\.|(?-i:\bborn\b|\bBorn (?:on|in)\b)|date of birth|geburtsdatum|"
    r"geburtstag|\bgeb\b)",
    "access": rf"(\bstand\b|zugriff|abgerufen|abrufdatum|accessed|retrieved|visited|besucht|"
    rf"gepr{_U}ft|last checked|last modified|aufgerufen|online;)",
    "copyright": r"(\u00a9|copyright|(?<!\w)\(c\)|c\u20dd)",
    "build": r"(compiled|kompiliert|generated|erstellt am|ge[a\u00e4]ndert am|printed)",
    "revision": rf"({_U}berarbeitet|revised|revision|version with|korrigiert|corrected)",
    "defence": rf"(m{_U}ndlichen pr{_U}fung|disputation|defen[cs]e|verteidigung|"
    rf"pr{_U}fungstermin|akzeptiert|accepted|oral exam|colloquium|kolloquium|verteidigt|defended)",
    # positive cues
    "submission": r"(eingereicht|submitted|submission|abgabe|abgegeben|vorgelegt|letzte version|"
    r"date:|datum:|handed in|thesis type and date)",
    "citation_open": r"[(\[]\s*$",
}
CUE_RE = {name: re.compile(rx, re.I) for name, rx in CUES.items()}
#: Cues that make a candidate invalid wherever they appear before it. Only
#: linguistic cues tied to no repository; a researcher ruleset may add more
#: (named ``ruleset:<id>``, ADR-0023).
EXCLUSION_CUES = ("birth", "access", "copyright", "build", "revision", "defence")
#: Prefix of the cue names a researcher ruleset adds.
RULESET_CUE = "ruleset:"
#: Cues read on the candidate's own line only (never from a label above).
_SAME_LINE_ONLY = ("citation_open",)
_CUE_WIDTH = 40

_RANGE_SEP_RE = re.compile(r"^\s*[.,]?\s*(?:[-\u2013\u2014]|bis|to|until|and)\s*$", re.I)
_THESIS_YEAR_CUE_RE = re.compile(r"(eingereicht|vorgelegt|aus dem|im)\s+jahre?\s*$", re.I)
_THESIS_WORD_RE = re.compile(r"(arbeit|thesis)", re.I)
_TITLE_PREP_RE = re.compile(
    r"(?i)(\b(seit|zwischen|und|bis|von|vom|in|im|um|nach|vor|ab|since|between|and|from|to|of|"
    r"until)|[:/\u2013-])\s*$"
)
_PLACE_PREFIX_RE = re.compile(r"[A-Z\u00c4\u00d6\u00dc][\w\u00a8.-]+\s*,\s*((den|am|im|the)\s+)?$")
_IMPRINT_RE = re.compile(
    r"(?:[A-Z\u00c4\u00d6\u00dc][A-Za-z\u00e4\u00f6\u00fc\u00df\u00a8]+|^\s*[a-z\u00e4\u00f6\u00fc\u00df]+)\s*,\s*$"
)
_PLACE_LINE_RE = re.compile(r"\s*[A-Z\u00c4\u00d6\u00dc][a-z\u00e4\u00f6\u00fc\u00df]+\s*")
_CITE_AFTER_RE = re.compile(r"^[a-z]?[)\];:]")


def cues_before(
    text: str,
    start: int,
    width: int = _CUE_WIDTH,
    extra: tuple[tuple[str, re.Pattern], ...] = (),
) -> set[str]:
    """Cue names found on the same line before ``start``; a label line ending
    in ":" directly above (with nothing before the date on its own line)
    counts too ("eingereicht am:" / "Tag der m\u00fcndlichen Pr\u00fcfung:")."""
    line_start = text.rfind("\n", 0, start) + 1
    pre_line = text[max(line_start, start - width) : start]
    prev_end = line_start - 1
    prev_line = text[text.rfind("\n", 0, max(prev_end, 0)) + 1 : prev_end] if prev_end > 0 else ""
    label_above = prev_line.rstrip().endswith(":") and not pre_line.strip()
    found = set()
    for name, rx in (*CUE_RE.items(), *extra):
        if name in _SAME_LINE_ONLY or not label_above:
            target = pre_line
        else:
            target = prev_line[-width:] + " " + pre_line
        if rx.search(target):
            found.add(name)
    return found


def _line_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return line_start, (line_end if line_end != -1 else len(text))


def _standalone(text: str, c: Candidate) -> bool:
    """Alone on its line, an imprint "Place, YYYY", or "Berlin 2016" as the line."""
    line_start, line_end = _line_bounds(text, c.start, c.end)
    rest = (text[line_start : c.start] + text[c.end : line_end]).strip(" .,;:")
    if not rest:
        return True
    pre_line = text[max(0, c.start - 40) : c.start].split("\n")[-1]
    post_line = text[c.end : c.end + 60].split("\n")[0].strip(" .,;:")
    if _IMPRINT_RE.search(pre_line):
        return True
    return not post_line and _PLACE_LINE_RE.fullmatch(pre_line) is not None


def annotate(
    text: str, cands: list[Candidate], extra: tuple[tuple[str, re.Pattern], ...] = ()
) -> list[Candidate]:
    for i, c in enumerate(cands):
        c.cues = cues_before(text, c.start, extra=extra)
        if _THESIS_YEAR_CUE_RE.search(text[max(0, c.start - 30) : c.start]) and _THESIS_WORD_RE.search(
            text[max(0, c.start - 250) : c.start]
        ):
            # "eingereicht im Jahr 2003" / "aus dem Jahr 2023" (series reprints:
            # the thesis year, not the series year - owner decision on #81)
            c.cues.add("submission")
        following = cands[i + 1] if i + 1 < len(cands) else None
        c.range_start = bool(
            following and _RANGE_SEP_RE.match(text[c.end : following.start])
        )
        after = text[c.end : c.end + 3]
        pre_line = text[max(0, c.start - 80) : c.start].split("\n")[-1]
        inside_paren = pre_line.rfind("(") > pre_line.rfind(")")
        c.citation = c.form in ("year", "acad") and (
            "citation_open" in c.cues or inside_paren or _CITE_AFTER_RE.match(after) is not None
        )
        c.standalone = _standalone(text, c)
        c.line_final = not text[c.end : c.end + 80].split("\n")[0].strip(" .,;:")
        near = text[max(0, c.start - 60) : c.start].split("\n")[-1]
        c.title_prep = bool(_TITLE_PREP_RE.search(near))
        c.place_prefix = bool(_PLACE_PREFIX_RE.search(near))
        c.alone = c.line_final and not near.strip(" .,;:")
    return cands


def rejection(c: Candidate, max_year: int) -> str | None:
    """Why ``c`` is not a thesis date, or ``None`` if it is a valid candidate."""
    if c.year > max_year or c.year < 1900:
        return "implausible_year"
    excluded = sorted(
        cue for cue in c.cues if cue in EXCLUSION_CUES or cue.startswith(RULESET_CUE)
    )
    if excluded:
        return excluded[0]
    if c.range_start:
        return "range_start"
    if c.form in _BARE_FORMS:
        if c.citation:
            return "citation"
        title_page_line_end = c.page == 0 and c.line_final and not c.title_prep
        if not (c.standalone or "submission" in c.cues or title_page_line_end):
            return "bare_year_position"
    elif c.page > 0 and not ("submission" in c.cues or c.place_prefix or c.alone):
        # after the title page only a cued, "Place, date" or own-line date counts
        return "after_title_page"
    return None


@dataclass
class Decision:
    winner: Candidate | None
    rule: str | None  # "submission_cue" | "most_precise_on_page"
    considered: list[tuple[Candidate, str | None]]


def compile_cues(rules) -> tuple[tuple[str, re.Pattern], ...]:
    """Extra negative cues of a researcher ruleset (``PatternRule``s)."""
    return tuple((RULESET_CUE + r.id, re.compile(r.pattern, re.I)) for r in rules)


def pick(
    pages: list[str],
    max_year: int,
    not_evidence: list[str | None] | None = None,
    extra_cues: tuple[tuple[str, re.Pattern], ...] = (),
) -> Decision:
    """The thesis date from the window ``pages`` (title page first).

    ``not_evidence`` holds, per page, the id of the researcher rule that marks
    it as no evidence (or ``None``); ``extra_cues`` are a ruleset's extra
    negative cues. Both are empty on the default path (ADR-0023).
    """
    considered: list[tuple[Candidate, str | None]] = []
    for rel, page in enumerate(pages):
        valid: list[Candidate] = []
        marked = not_evidence[rel] if not_evidence and rel < len(not_evidence) else None
        for c in annotate(page, candidates(page), extra_cues):
            c.page = rel
            reason = RULESET_CUE + marked if marked else rejection(c, max_year)
            considered.append((c, reason))
            if reason is None:
                valid.append(c)
        if not valid:
            continue
        cued = [c for c in valid if "submission" in c.cues]
        if cued:
            return Decision(cued[0], "submission_cue", considered)
        best = min(valid, key=lambda c: (_RANK[c.precision], c.start))
        return Decision(best, "most_precise_on_page", considered)
    return Decision(None, None, considered)
