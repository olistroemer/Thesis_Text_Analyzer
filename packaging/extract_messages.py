#!/usr/bin/env python
"""Extract translatable strings from tta/ into tta/locale/tta.pot (ADR-0020).

    python packaging/extract_messages.py            # write the .pot
    python packaging/extract_messages.py --check     # exit 1 if it is stale
    python packaging/extract_messages.py --update     # merge into every .po

An ``ast`` walk, not ``xgettext``: GNU gettext is not an installable Python
dependency and is absent on a stock Windows or macOS machine. Walking the AST
is also *stricter* than ``xgettext -L Python` in the way that matters here -
it only sees a real call to ``_``/``N_`` with a single string-literal
argument, so a msgid computed at run time cannot silently enter the catalog
and then fail to translate at the one moment it is needed.

Output is deterministic: entries in sorted msgid order, references sorted,
no timestamp in the header. That is what makes ``--check`` a usable CI gate.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pocatalog  # noqa: E402  - loaded by path, see the module docstring

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "tta"
POT_PATH = SOURCE_ROOT / "locale" / "tta.pot"

#: The two marker names. ``_`` translates at the call site; ``N_`` only marks
#: (for strings whose English form is the stored value, and for module-level
#: constants evaluated before a locale exists).
MARKERS = ("_", "N_")


def _literal(node: ast.AST) -> str | None:
    """The string value of a literal argument, or None if it is not one.

    Implicit concatenation ("a" "b") is already folded into one Constant by
    the parser, and an explicit ``"a" + "b"`` of literals folds here, because
    both are things a wrapped UI string legitimately looks like.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal(node.left), _literal(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def extract_file(path: pathlib.Path, relative_to: pathlib.Path) -> list[tuple[str, str]]:
    """[(msgid, "path:line")] for one source file, in source order."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    reference_path = path.relative_to(relative_to).as_posix()
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in MARKERS):
            continue
        if len(node.args) != 1 or node.keywords:
            continue
        text = _literal(node.args[0])
        if text:  # an empty msgid is the header entry; never extract one
            found.append((text, "%s:%d" % (reference_path, node.lineno)))
    return found


def build_catalog(source_root: pathlib.Path = SOURCE_ROOT) -> pocatalog.Catalog:
    """The .pot contents for every tracked ``*.py`` under ``source_root``."""
    catalog = pocatalog.Catalog()
    for path in sorted(source_root.rglob("*.py")):
        for msgid, reference in extract_file(path, source_root.parent):
            catalog.add(msgid, reference)
    return catalog


def render(source_root: pathlib.Path = SOURCE_ROOT) -> str:
    return pocatalog.write_po(build_catalog(source_root), template=True)


# -- catalog merge -------------------------------------------------------------


def merge(template: pocatalog.Catalog, existing: pocatalog.Catalog) -> pocatalog.Catalog:
    """Template msgids with the existing translations carried over.

    Adds msgids the source has gained (empty msgstr), keeps every translation
    whose msgid still exists, and DROPS entries the source no longer has -
    an obsolete msgstr is dead weight that makes the untranslated-count gate
    lie. References are refreshed from the template, since they are the
    source's business, not the translator's.
    """
    merged = pocatalog.Catalog(header=existing.header or template.header,
                               preamble=existing.preamble)
    for entry in template.sorted_entries():
        previous = existing.entries.get(entry.msgid)
        merged.entries[entry.msgid] = pocatalog.Entry(
            msgid=entry.msgid,
            msgstr=previous.msgstr if previous is not None else "",
            references=entry.references,
            comments=entry.comments,
        )
    return merged


def catalog_paths(source_root: pathlib.Path = SOURCE_ROOT) -> list[pathlib.Path]:
    return sorted((source_root / "locale").glob("*/LC_MESSAGES/tta.po"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="do not write; exit 1 if the committed .pot is out of date",
    )
    parser.add_argument(
        "--update", action="store_true",
        help="also merge new msgids into every tta/locale/*/LC_MESSAGES/tta.po",
    )
    args = parser.parse_args(argv)

    template_text = render()
    if args.check:
        current = POT_PATH.read_text(encoding="utf-8") if POT_PATH.is_file() else ""
        if current == template_text:
            print("%s is up to date" % POT_PATH.relative_to(REPO_ROOT))
            return 0
        print(
            "%s is STALE - run: python packaging/extract_messages.py"
            % POT_PATH.relative_to(REPO_ROOT),
            file=sys.stderr,
        )
        return 1

    POT_PATH.parent.mkdir(parents=True, exist_ok=True)
    POT_PATH.write_text(template_text, encoding="utf-8")
    template = pocatalog.read_po(template_text, origin=str(POT_PATH))
    print("wrote %s (%d messages)" % (POT_PATH.relative_to(REPO_ROOT), len(template.entries)))

    if args.update:
        for path in catalog_paths():
            existing = pocatalog.read_po(path.read_text(encoding="utf-8"), origin=str(path))
            merged = merge(template, existing)
            path.write_text(pocatalog.write_po(merged, template=False), encoding="utf-8")
            missing = merged.untranslated()
            print(
                "updated %s (%d messages, %d untranslated)"
                % (path.relative_to(REPO_ROOT), len(merged.entries), len(missing))
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
