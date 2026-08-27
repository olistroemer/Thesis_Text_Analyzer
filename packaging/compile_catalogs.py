#!/usr/bin/env python
"""Compile tta/locale/*/LC_MESSAGES/tta.po to tta.mo (ADR-0020).

    python packaging/compile_catalogs.py            # write every .mo
    python packaging/compile_catalogs.py --check     # exit 1 if any is stale

A pure-Python GNU MO writer, because ``msgfmt`` ships with GNU gettext and is
not an installable Python dependency. Both the .po and the compiled .mo are
committed: ``gettext`` needs the .mo at run time, a from-source checkout has
no build step to produce one, and a missing catalog fails *silently* - the
German-first application would just come up in English. ``--check`` is the
gate that stops the committed binary from drifting from its source.

The output is a pure function of the .po, so --check is a byte comparison.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pocatalog  # noqa: E402  - loaded by path, see pocatalog's docstring

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCALE_ROOT = REPO_ROOT / "tta" / "locale"


def po_paths(locale_root: pathlib.Path = LOCALE_ROOT) -> list[pathlib.Path]:
    return sorted(locale_root.glob("*/LC_MESSAGES/tta.po"))


def compile_po(path: pathlib.Path) -> bytes:
    """One .po file's compiled bytes."""
    catalog = pocatalog.read_po(path.read_text(encoding="utf-8"), origin=str(path))
    return pocatalog.write_mo(catalog)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="do not write; exit 1 if any committed .mo is out of date",
    )
    args = parser.parse_args(argv)

    paths = po_paths()
    if not paths:
        print("no catalogs under %s" % LOCALE_ROOT.relative_to(REPO_ROOT), file=sys.stderr)
        return 0

    stale = []
    for path in paths:
        target = path.with_suffix(".mo")
        payload = compile_po(path)
        relative = target.relative_to(REPO_ROOT)
        if args.check:
            current = target.read_bytes() if target.is_file() else b""
            if current == payload:
                print("%s is up to date" % relative)
            else:
                stale.append(relative)
            continue
        target.write_bytes(payload)
        print("wrote %s (%d bytes)" % (relative, len(payload)))

    if stale:
        print(
            "STALE: %s - run: python packaging/compile_catalogs.py"
            % ", ".join(str(p) for p in stale),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
