"""Researcher cover-page rulesets: loading and validation (ADR-0023, #81, #82).

A cover ruleset tells the two title-page modules which leading pages a
repository prepended on download (e.g. a generated cover page), so they read
the thesis's own title page instead. The shipped app applies **no** cover rule:
rulesets are data files kept outside the `tta` package (``research/cover_rules/``
in the repository, never bundled into a binary) and are loaded only when a
researcher passes one explicitly (``tta run --cover-rules FILE``). The GUI never
offers one (ADR-0003 rev. 2026-11-17: the CLI's feature set is a superset of
the GUI's).

File format (TOML, read with the stdlib ``tomllib``)::

    id = "example-repository"           # required, names the set
    version = "1"                       # required, bump on every change
    description = "..."                 # optional
    max_pages = 3                       # optional, leading pages at most

    [[rules]]
    id = "example-download-cover"       # required, unique in the file
    all_of = ["Downloaded from the Example Repository"]
    any_of = []                         # optional
    description = "..."                 # optional
    evidence = "..."                    # optional, free text

A page matches a rule when it contains every ``all_of`` string and, if given,
one of the ``any_of`` strings, compared after `_titlepage.normalise` (case,
accents and whitespace folded). Unknown keys are an error, so a typo cannot
silently disable a rule.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from tta.core.modules._titlepage import CoverRule, CoverRuleset

_TOP_KEYS = {"id", "version", "description", "max_pages", "rules"}
_RULE_KEYS = {"id", "description", "all_of", "any_of", "evidence"}


class CoverRulesError(ValueError):
    """A cover ruleset file that cannot be used as written."""


def _strings(value, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(s, str) and s.strip() for s in value):
        raise CoverRulesError(f"{where} must be a list of non-empty strings")
    return tuple(value)


def parse_cover_ruleset(data: dict, source: str = "") -> CoverRuleset:
    """Validate parsed TOML ``data`` into a :class:`CoverRuleset`."""
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise CoverRulesError(f"unknown key(s) {sorted(unknown)} in cover ruleset")
    for key in ("id", "version"):
        if not isinstance(data.get(key), (str, int)) or not str(data.get(key)).strip():
            raise CoverRulesError(f"cover ruleset needs a non-empty '{key}'")
    max_pages = data.get("max_pages", 3)
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 10:
        raise CoverRulesError("'max_pages' must be an integer from 1 to 10")
    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise CoverRulesError("cover ruleset needs at least one [[rules]] entry")
    rules, seen = [], set()
    for index, raw in enumerate(raw_rules):
        where = f"rules[{index}]"
        if not isinstance(raw, dict):
            raise CoverRulesError(f"{where} must be a table")
        unknown = set(raw) - _RULE_KEYS
        if unknown:
            raise CoverRulesError(f"unknown key(s) {sorted(unknown)} in {where}")
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise CoverRulesError(f"{where} needs a non-empty 'id'")
        if rule_id in seen:
            raise CoverRulesError(f"duplicate rule id {rule_id!r}")
        seen.add(rule_id)
        all_of = _strings(raw.get("all_of", []), f"{where}.all_of")
        any_of = _strings(raw.get("any_of", []), f"{where}.any_of")
        if not all_of and not any_of:
            raise CoverRulesError(f"{where} needs 'all_of' or 'any_of'")
        rules.append(
            CoverRule(
                id=rule_id,
                all_of=all_of,
                any_of=any_of,
                description=str(raw.get("description", "")),
            )
        )
    return CoverRuleset(
        id=str(data["id"]),
        version=str(data["version"]),
        rules=tuple(rules),
        max_pages=max_pages,
        source=source,
    )


def load_cover_ruleset(path: Path | str) -> CoverRuleset:
    """Read and validate a cover ruleset file (raises :class:`CoverRulesError`)."""
    path = Path(path)
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise CoverRulesError(f"cannot read cover ruleset {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CoverRulesError(f"cover ruleset {path} is not valid TOML: {exc}") from exc
    return parse_cover_ruleset(data, source=path.name)
