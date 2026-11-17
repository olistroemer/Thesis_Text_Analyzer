"""Researcher rulesets: loading and validation (ADR-0023, #81, #82).

A researcher ruleset holds the rules that are derived from a particular
repository's or institution's layout: cover pages a repository prepends on
download, metadata pages, form texts that list every paper type. The shipped
app applies **none** of them - without a ruleset the thesis text is processed
unmodified. Rulesets are data files kept outside the `tta` package
(``research/cover_rules/`` in the repository, never bundled into a binary) and
are loaded only when a researcher passes one explicitly (``tta run
--cover-rules FILE``). The GUI never offers one (ADR-0003 rev. 2026-11-17: the
CLI's feature set is a superset of the GUI's). The option keeps its first
name, "cover rules", although a ruleset now does more than skip cover pages.

File format (TOML, read with the stdlib ``tomllib``)::

    id = "example-repository"           # required, names the set
    version = "1"                       # required, bump on every change
    description = "..."                 # optional
    max_pages = 3                       # optional, cover pages skipped at most

    [[covers]]                          # leading pages to skip
    id = "example-download-cover"       # required, unique in the file
    all_of = ["Downloaded from the Example Repository"]
    any_of = []                         # optional
    min_any = 1                         # optional, how many any_of must occur
    description = "..."                 # optional
    evidence = "..."                    # optional, free text

    [[not_evidence_pages]]              # pages kept, but no date / type marker
    id = "example-metadata-page"
    any_of = ["Deposited:", "Licence:", "Persistent ID:"]
    min_any = 2

    [[date_cues]]                       # extra negative cue before a date
    id = "example-deposit-label"
    pattern = "deposited"               # regex, case-insensitive, raw text

    [[type_passages]]                   # passages whose type markers do not count
    id = "example-form"
    pattern = "this form applies to every (?:thesis|paper)"
    tail = 40                           # optional, characters after the match

Page rules (``covers``, ``not_evidence_pages``) compare their strings after
`_titlepage.normalise` (case, accents and whitespace folded). ``date_cues``
patterns are searched case-insensitively in the raw text before a date (same
line, or a label line ending in ":" directly above), like the built-in cues.
``type_passages`` patterns run on the normalised type window, so write them in
that form (lower case, no accents, "ss" for the eszett). A ruleset needs at
least one rule; unknown keys are an error, so a typo cannot silently disable a
rule.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tta.core.modules._titlepage import CoverRule, CoverRuleset, PatternRule

_TOP_KEYS = {
    "id",
    "version",
    "description",
    "max_pages",
    "covers",
    "not_evidence_pages",
    "date_cues",
    "type_passages",
}
_PAGE_KEYS = {"id", "description", "all_of", "any_of", "min_any", "evidence"}
_PATTERN_KEYS = {"id", "description", "pattern", "tail", "evidence"}


class CoverRulesError(ValueError):
    """A researcher ruleset file that cannot be used as written."""


def _strings(value, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(s, str) and s.strip() for s in value):
        raise CoverRulesError(f"{where} must be a list of non-empty strings")
    return tuple(value)


def _int(value, where: str, lo: int, hi: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise CoverRulesError(f"{where} must be an integer from {lo} to {hi}")
    return value


def _tables(data: dict, key: str) -> list[dict]:
    raw = data.get(key, [])
    if not isinstance(raw, list) or not all(isinstance(t, dict) for t in raw):
        raise CoverRulesError(f"'{key}' must be a list of [[{key}]] tables")
    return raw


def _rule_id(raw: dict, where: str, seen: set[str]) -> str:
    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise CoverRulesError(f"{where} needs a non-empty 'id'")
    if rule_id in seen:
        raise CoverRulesError(f"duplicate rule id {rule_id!r}")
    seen.add(rule_id)
    return rule_id


def _page_rule(raw: dict, where: str, seen: set[str]) -> CoverRule:
    unknown = set(raw) - _PAGE_KEYS
    if unknown:
        raise CoverRulesError(f"unknown key(s) {sorted(unknown)} in {where}")
    rule_id = _rule_id(raw, where, seen)
    all_of = _strings(raw.get("all_of", []), f"{where}.all_of")
    any_of = _strings(raw.get("any_of", []), f"{where}.any_of")
    if not all_of and not any_of:
        raise CoverRulesError(f"{where} needs 'all_of' or 'any_of'")
    min_any = _int(raw.get("min_any", 1), f"{where}.min_any", 1, max(1, len(any_of)))
    return CoverRule(
        id=rule_id,
        all_of=all_of,
        any_of=any_of,
        min_any=min_any,
        description=str(raw.get("description", "")),
    )


def _pattern_rule(raw: dict, where: str, seen: set[str]) -> PatternRule:
    unknown = set(raw) - _PATTERN_KEYS
    if unknown:
        raise CoverRulesError(f"unknown key(s) {sorted(unknown)} in {where}")
    rule_id = _rule_id(raw, where, seen)
    pattern = raw.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        raise CoverRulesError(f"{where} needs a non-empty 'pattern'")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise CoverRulesError(f"{where}.pattern is not a valid regular expression: {exc}") from exc
    return PatternRule(
        id=rule_id,
        pattern=pattern,
        tail=_int(raw.get("tail", 0), f"{where}.tail", 0, 1000),
        description=str(raw.get("description", "")),
    )


def parse_cover_ruleset(data: dict, source: str = "") -> CoverRuleset:
    """Validate parsed TOML ``data`` into a :class:`CoverRuleset`."""
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise CoverRulesError(f"unknown key(s) {sorted(unknown)} in the ruleset")
    for key in ("id", "version"):
        if not isinstance(data.get(key), (str, int)) or not str(data.get(key)).strip():
            raise CoverRulesError(f"the ruleset needs a non-empty '{key}'")
    max_pages = _int(data.get("max_pages", 3), "'max_pages'", 1, 10)
    seen: set[str] = set()
    groups = {}
    for key, build in (
        ("covers", _page_rule),
        ("not_evidence_pages", _page_rule),
        ("date_cues", _pattern_rule),
        ("type_passages", _pattern_rule),
    ):
        groups[key] = tuple(
            build(raw, f"{key}[{index}]", seen) for index, raw in enumerate(_tables(data, key))
        )
    if not any(groups.values()):
        raise CoverRulesError(
            "the ruleset needs at least one rule "
            "([[covers]], [[not_evidence_pages]], [[date_cues]] or [[type_passages]])"
        )
    return CoverRuleset(
        id=str(data["id"]),
        version=str(data["version"]),
        covers=groups["covers"],
        not_evidence_pages=groups["not_evidence_pages"],
        date_cues=groups["date_cues"],
        type_passages=groups["type_passages"],
        max_pages=max_pages,
        source=source,
    )


def load_cover_ruleset(path: Path | str) -> CoverRuleset:
    """Read and validate a ruleset file (raises :class:`CoverRulesError`)."""
    path = Path(path)
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise CoverRulesError(f"cannot read ruleset {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CoverRulesError(f"ruleset {path} is not valid TOML: {exc}") from exc
    return parse_cover_ruleset(data, source=path.name)
