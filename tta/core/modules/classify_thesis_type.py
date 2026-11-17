"""`mod_classify_thesis_type` - catalogue #11 (SDD Sec. 7.1/7.4, ADR-0019, #9, #82).

Detects the degree from the front matter of `raw_text` with a lightweight,
case-insensitive, accent/umlaut-tolerant marker heuristic (German + English) -
NOT ML. Produces the single `thesis_type` metric (value set in
`tta.core.types.THESIS_TYPES`); the matched markers and the deciding rule go
into `diagnostics` (no separate confidence metric).

Rules (ADR-0019 rev. 3, catalogue in `docs/titlepage-rules.md`, "type markers
v1"), ported from the #82 exploration:

- Window: the document's own pages 0-4 (after cover pages, if a researcher
  cover ruleset is loaded - ADR-0023; none by default), normalised by
  `_titlepage.normalise` with letter-spaced words collapsed.
- Markers are **spelled-out** type/degree phrases only. Abbreviations (B.Sc.,
  M.Sc., M.A., Dipl.-X, Dr. sc., PhD, lic. phil.), bare "Dissertation", bare
  "Diplom" and bare "Master..." are never markers: they are author,
  supervisor and examiner titles, study programmes or topics.
- The earliest valid marker wins. A "Master of Advanced Studies / MAS"
  statement on the same page turns a master marker into `mas`. "Nachdiplom..."
  is not "Diplom...". The ETH declaration of originality, which lists every
  paper type, is excluded.
- Tier 2: a bare "Bachelor/Master of <field>" counts only when no tier-1
  marker is in the window (it is also the author's previous degree).
- Markers on a page that carries a repository metadata block (generic deposit
  labels such as "Publication date:" / "Permanent link:") do not count; the
  page itself is not skipped.

Garbled/sparse or marker-free text returns `unspecified` (a valid answer),
never `NotApplicable` - the type metric is always present so the grid/report
can group by it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from tta.core import artefact_kinds
from tta.core.modules import _titlepage
from tta.core.modules.base import Module, ModuleSpec, RunContext, RunResult

BACHELOR, MASTER, DIPLOMA, UNSPECIFIED = "bachelor", "master", "diploma", "unspecified"
MAGISTER, MAS, LICENTIATE, SEMESTER, DOCTORAL = (
    "magister",
    "mas",
    "licentiate",
    "semester",
    "doctoral",
)

#: The document's own pages 0-4 (#82: the earliest true marker is within
#: them in 99 % of the labelled sample; page 3 holds HU series imprints).
WINDOW_PAGES = 5

#: Markers listed in `diagnostics`, so a marker-heavy front matter stays bounded.
MAX_LISTED_MARKERS = 40

# The degree phrase "(degree|Grades|requirements for|presented for|
# Abschlussarbeit) <= 3 words <type>" shared by bachelor and master.
_DEGREE_PHRASE = r"(?:degree|grades?|grads|requirements for|presented for|abschlussarbeit)\W+(?:\w+\W+){0,3}?"

#: Tier-1 markers: class -> ((marker id, regex on normalised text), ...).
TIER1: dict[str, tuple[tuple[str, str], ...]] = {
    BACHELOR: (
        ("Bachelorarbeit/-thesis", r"\bbachelors? ?-? ?(?:arbeit|thesis|abschlussarbeit)\b"),
        ("degree of Bachelor", _DEGREE_PHRASE + r"bachelor\b"),
    ),
    MASTER: (
        ("Masterarbeit/-thesis", r"\bmasters? ?-? ?(?:arbeit|thesis)\b"),
        ("MSc/Master of Science thesis", r"\b(?:m\. ?sc\.?|msc|master of science) thesis\b"),
        ("degree of Master", _DEGREE_PHRASE + r"master\b(?! of advanced)"),
    ),
    DIPLOMA: (
        (
            "Diplomarbeit/Diploma thesis",
            r"(?<!nach)\bdiplom ?-? ?arbeit|\bdiploma ?-? ?thesis\b|\bdiplomthesis\b",
        ),
        (
            "Diplom-<degree> (spelled out)",
            r"\bdiplom ?-? ?(?:ingenieur|informatiker|kauf|volkswirt|psycholog|physiker|biolog|"
            r"mathematiker|geograph|okonom|padagog|soziolog|betriebswirt)",
        ),
        ("Diplomthema/Diplomand", r"\bdiplom ?thema\b|\bdiplomand(?:in)?\b|\bdiplomsemester\b"),
        ("Hausarbeit zur Diplompruefung", r"hausarbeit zur diplomprufung"),
    ),
    MAGISTER: (
        ("Magisterarbeit", r"\bmagister ?-? ?arb(?:eit|\.)"),
        ("Magister/Magistra Artium", r"\bmagist(?:er|ra) artium\b"),
    ),
    LICENTIATE: (("Lizentiatsarbeit", r"\blizentiatsarbeit\b|\blicentiate thesis\b"),),
    MAS: (
        ("Master of Advanced Studies / MAS", r"master of advanced studies|\bmas[- ](?:programm|thesis|in )"),
        ("Nachdiplom / postgraduate studies", r"\bnachdiplom\w*|postgraduate studies"),
    ),
    SEMESTER: (
        ("Semesterarbeit/-project", r"\bsemester ?-? ?(?:arbeit|thesis|project|projekt|paper)\b"),
        ("Studienarbeit", r"\bstudien ?-? ?arbeit\b"),
        ("Focus Work", r"\bfocus work\b"),
    ),
    # No corpus evidence (the reference corpus holds no dissertation); kept
    # because professors supervise doctorates (ADR-0019 rev. 3).
    DOCTORAL: (
        (
            "Dissertation zur Erlangung / submitted",
            r"\bdissertation (?:zur erlangung|submitted|eingereicht|presented)",
        ),
        (
            "Doctor of Sciences / Doktorgrad",
            r"doctor of (?:sciences?|philosophy)|doktorgrad|(?:grades?|degree) (?:eines |einer |of )?"
            r"(?:doktors?|doctor)\b",
        ),
        ("Doctoral thesis / Doktorarbeit", r"\bdoctoral thesis\b|\bdoktorarbeit\b"),
    ),
}

#: Tier 2: only when no tier-1 marker is in the window.
TIER2: dict[str, tuple[tuple[str, str], ...]] = {
    BACHELOR: (
        ("Bachelor of <field>", r"\bbachelor of (?:science|arts|engineering|laws|education)\b"),
    ),
    MASTER: (
        (
            "Master of <field>",
            r"\bmaster of (?!advanced)(?:science|arts|engineering|economics|statistics|education|laws)\b",
        ),
    ),
}

#: Text spans whose markers do not count. The ETH declaration of originality
#: lists every paper type ("component of every semester paper, bachelor's
#: thesis, master's thesis ..."); the span runs 40 characters past the match.
EXCLUSIONS = (
    (
        "declaration of originality",
        re.compile(
            r"(?:component of every|bestandteil jeder).{0,160}?(?:degree paper|abschlussarbeit|arbeit)"
        ),
    ),
)
_EXCLUSION_TAIL = 40

#: Tie-break for two markers starting at the same index (practically
#: unreachable): the more specific class first.
PRIORITY = (MAGISTER, LICENTIATE, MAS, DIPLOMA, BACHELOR, MASTER, SEMESTER, DOCTORAL)

_MAS_MARKER = "Master of Advanced Studies / MAS"

_TIER1_RE = {cls: tuple((mid, re.compile(rx)) for mid, rx in lst) for cls, lst in TIER1.items()}
_TIER2_RE = {cls: tuple((mid, re.compile(rx)) for mid, rx in lst) for cls, lst in TIER2.items()}


@dataclass(frozen=True)
class Marker:
    offset: int  # in the joined window
    page: int  # own page index (0 = first page after any cover pages)
    cls: str
    marker: str
    tier: int
    excluded: str | None


#: Exclusion reason for markers on a page carrying a repository metadata
#: block (`_titlepage.is_repository_metadata_page`): its type line is the
#: repository's metadata, not the document's statement.
REPOSITORY_PAGE = "repository metadata page"


def _window(own_pages: tuple[str, ...]) -> tuple[str, list[int], list[bool]]:
    """Normalised, letter-spacing-collapsed window, each page's start offset
    and whether the page is a repository metadata page."""
    text, starts, metadata = "", [], []
    for page in own_pages[:WINDOW_PAGES]:
        starts.append(len(text))
        metadata.append(_titlepage.is_repository_metadata_page(page))
        text += _titlepage.collapse_letter_spacing(_titlepage.normalise(page)) + " "
    return text, starts, metadata


def _page_of(offset: int, starts: list[int]) -> int:
    return max(i for i, start in enumerate(starts) if start <= offset)


def find_markers(
    text: str, starts: list[int], tier: int, metadata: list[bool] | None = None
) -> list[Marker]:
    spans = [
        (m.start(), m.end() + _EXCLUSION_TAIL, name)
        for name, rx in EXCLUSIONS
        for m in rx.finditer(text)
    ]
    table = _TIER1_RE if tier == 1 else _TIER2_RE
    found = []
    for cls, markers in table.items():
        for mid, rx in markers:
            for m in rx.finditer(text):
                page = _page_of(m.start(), starts)
                excluded = next((n for s, e, n in spans if s <= m.start() < e), None)
                if excluded is None and metadata and metadata[page]:
                    excluded = REPOSITORY_PAGE
                found.append(Marker(m.start(), page, cls, mid, tier, excluded))
    found.sort(key=lambda h: (h.offset, PRIORITY.index(h.cls)))
    return found


def classify(own_pages: tuple[str, ...]) -> tuple[str, str | None, Marker | None, list[Marker]]:
    """``(class, rule, winning marker, all markers)`` for the document's own pages."""
    text, starts, metadata = _window(own_pages)
    if not starts:
        return UNSPECIFIED, None, None, []
    markers = find_markers(text, starts, tier=1, metadata=metadata)
    valid = [m for m in markers if m.excluded is None]
    rule = "earliest_marker"
    if not valid:
        markers += find_markers(text, starts, tier=2, metadata=metadata)
        valid = [m for m in markers if m.excluded is None]
        rule = "earliest_marker_tier2"
    if not valid:
        return UNSPECIFIED, None, None, markers
    winner = valid[0]
    cls = winner.cls
    if cls == MASTER and any(
        m.marker == _MAS_MARKER and m.page == winner.page for m in valid
    ):
        # a MAS statement on the same page: continuing education, not the
        # consecutive master
        cls, rule = MAS, rule + "+mas_override"
    return cls, rule, winner, markers


class ClassifyThesisType(Module):
    spec = ModuleSpec(
        name="mod_classify_thesis_type",
        version="0.3.0",
        consumes=(artefact_kinds.RAW_TEXT,),
        produces_metrics=("thesis_type",),
    )

    def __init__(self, cover_rules: _titlepage.CoverRuleset | None = None):
        # ADR-0023: no cover rules by default; a researcher ruleset changes
        # the effective version so its runs are never mixed with default ones
        self.cover_rules = cover_rules
        if cover_rules is not None:
            self.spec = replace(
                type(self).spec, version=_titlepage.versioned(type(self).spec.version, cover_rules)
            )

    def run(self, ctx: RunContext) -> RunResult:
        text = ctx.artefacts[artefact_kinds.RAW_TEXT].read_text(encoding="utf-8")
        front = _titlepage.front_matter(text, self.cover_rules)
        decision, rule, winner, markers = classify(front.own_pages())
        diagnostics: dict[str, object] = {
            "thesis_type": decision,
            "rules": "type markers v1 (ADR-0019 rev. 3)",
            "window_pages": WINDOW_PAGES,
            "rule": rule,
            "winner": None
            if winner is None
            else {"class": winner.cls, "marker": winner.marker, "page": winner.page, "tier": winner.tier},
            "markers": [
                {
                    "class": m.cls,
                    "marker": m.marker,
                    "page": m.page,
                    "tier": m.tier,
                    "excluded": m.excluded,
                }
                for m in markers[:MAX_LISTED_MARKERS]
            ],
            **_titlepage.cover_diagnostics(front, self.cover_rules),
        }
        return RunResult(metrics={"thesis_type": decision}, diagnostics=diagnostics)
