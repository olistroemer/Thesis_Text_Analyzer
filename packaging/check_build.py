#!/usr/bin/env python3
"""ADR-0014 build gates for the frozen release binaries.

Two things can go wrong with a PyInstaller build in a way that no unit test
of application code would ever notice:

  1. The binary grows because the build machine leaked packages into it.
     The first Linux release was 212 MB, of which ~288 MB uncompressed came
     from llvmlite / scipy / pandas / numba - none of them a declared
     dependency, two of them resolved from the builder's ~/.local (#52).
  2. The CLI binary carries the GUI's dependency stack (matplotlib, tksheet,
     Tcl/Tk) because the spec shared one ``hiddenimports`` list, which made
     the CLI *larger* than the GUI.

This script checks both against a finished build tree and exits non-zero on
any violation, so CI fails instead of publishing the artefact. Run it from
the repo root after PyInstaller:

    python packaging/check_build.py --dist dist --build build/tta \\
        --max-bytes 157286400

The size ceiling is a regression tripwire, not a target (ADR-0014). Raising
it requires an ADR revision that states why the growth is a genuine
dependency cost. On a failure, look for undeclared packages FIRST.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

# Packages that must not appear in EITHER dependency graph. Not declared in
# pyproject.toml and not imported by any tta module; they arrive through
# function-level optional imports inside pymupdf / nltk / pandas that
# PyInstaller's static analysis follows. See packaging/tta.spec EXCLUDES.
FORBIDDEN = ("pandas", "numba", "llvmlite", "scipy")

# Packages the GUI binary legitimately needs and the CLI binary must never
# carry. The hexagonal boundary (SDD 5.2, ADR-0002) is what makes this
# checkable: nothing under tta/core or tta/cli may import tta.ui.
GUI_ONLY = ("matplotlib", "mpl_toolkits", "tksheet", "kiwisolver", "contourpy")

# Third element of a PyInstaller TOC entry.
TOC_KINDS = frozenset(
    (
        "PYMODULE",
        "PYSOURCE",
        "PYZ",
        "BINARY",
        "EXTENSION",
        "DATA",
        "SYMLINK",
        "OPTION",
        "DEPENDENCY",
        "EXECUTABLE",
    )
)

MIB = 1024 * 1024


def _walk_entries(node):
    """Yield every (dest, source, kind) TOC entry anywhere inside ``node``.

    A PyInstaller ``Analysis-NN.toc`` is the repr of a 20-element tuple whose
    layout is an implementation detail (scripts, pathex, hiddenimports, ...,
    then the collected pure/binaries/datas TOCs). Walking the whole structure
    for TOC-shaped tuples keeps this robust across PyInstaller versions
    instead of hard-coding indices.
    """
    if isinstance(node, tuple) and len(node) == 3:
        dest, source, kind = node
        if isinstance(kind, str) and kind in TOC_KINDS and isinstance(dest, str):
            yield (dest, source if isinstance(source, str) else "", kind)
            return
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from _walk_entries(child)


def read_toc(path):
    """Parse an Analysis TOC file into a list of (dest, source, kind)."""
    with open(path, "r", encoding="utf-8") as handle:
        return list(_walk_entries(ast.literal_eval(handle.read())))


def top_level(dest):
    """The top-level package a TOC destination belongs to.

    Handles both module names ('scipy.interpolate') and bundled file paths
    ('scipy.libs/libopenblas.so', 'matplotlib/mpl-data/fonts/x.ttf').
    """
    head = dest.replace("\\", "/").split("/", 1)[0]
    return head.split(".", 1)[0]


def offenders(entries, packages):
    """Map package -> sorted sample of TOC destinations attributed to it."""
    wanted = set(packages)
    found = {}
    for dest, _source, _kind in entries:
        pkg = top_level(dest)
        if pkg in wanted:
            found.setdefault(pkg, set()).add(dest)
    return {pkg: sorted(dests) for pkg, dests in found.items()}


def user_site_sources(entries):
    """TOC entries collected from a per-user site-packages directory.

    Direct evidence of the contamination in #52: a release build must draw
    every file from the build environment, never from ``~/.local``.
    """
    marker = os.path.join(".local", "lib")
    return sorted(
        {source for _dest, source, _kind in entries if marker in source}
    )


def classify_tocs(paths):
    """Split Analysis TOCs into (cli_tocs, gui_tocs) by their entry script.

    The GUI graph is rooted at tta/ui/tk/app.py, the CLI graph at
    tta/cli/main.py; the boundary invariant guarantees neither contains the
    other's entry point, so this never depends on Analysis-NN ordering.
    """
    cli, gui = [], []
    for path in paths:
        entries = read_toc(path)
        sources = " ".join(source for _d, source, _k in entries)
        is_gui = "tta/ui/tk/app.py" in sources.replace("\\", "/")
        (gui if is_gui else cli).append((path, entries))
    return cli, gui


def check(dist_dir, build_dir, max_bytes, executables=("tta", "tta-gui")):
    """Run every gate. Returns a list of human-readable failure strings."""
    failures = []

    # ---- gate 1: size ceiling --------------------------------------------
    for name in executables:
        path = os.path.join(dist_dir, name)
        if not os.path.exists(path):
            failures.append("missing executable: %s" % path)
            continue
        size = os.path.getsize(path)
        print(
            "%-28s %12d bytes  %6.1f MiB  (ceiling %.1f MiB)"
            % (path, size, size / MIB, max_bytes / MIB)
        )
        if size > max_bytes:
            failures.append(
                "%s is %d bytes (%.1f MiB), over the ADR-0014 ceiling of "
                "%d bytes (%.1f MiB)"
                % (path, size, size / MIB, max_bytes, max_bytes / MIB)
            )

    # ---- gate 2 + 3: dependency-graph purity ------------------------------
    toc_paths = sorted(
        os.path.join(build_dir, name)
        for name in os.listdir(build_dir)
        if name.startswith("Analysis-") and name.endswith(".toc")
    ) if os.path.isdir(build_dir) else []
    if not toc_paths:
        failures.append("no Analysis-*.toc found under %s" % build_dir)
        return failures

    cli_tocs, gui_tocs = classify_tocs(toc_paths)
    if not cli_tocs or not gui_tocs:
        failures.append(
            "expected one CLI and one GUI Analysis TOC under %s, got "
            "cli=%d gui=%d" % (build_dir, len(cli_tocs), len(gui_tocs))
        )

    for path, entries in cli_tocs + gui_tocs:
        label = os.path.basename(path)

        found = offenders(entries, FORBIDDEN)
        if found:
            for pkg in sorted(found):
                failures.append(
                    "%s carries excluded package %r (%d entries, e.g. %s) - "
                    "ADR-0014 clean-environment clause"
                    % (label, pkg, len(found[pkg]), found[pkg][0])
                )

        leaked = user_site_sources(entries)
        if leaked:
            failures.append(
                "%s collected %d file(s) from a user site directory, e.g. %s "
                "- build with PYTHONNOUSERSITE=1 (ADR-0014)"
                % (label, len(leaked), leaked[0])
            )

    for path, entries in cli_tocs:
        found = offenders(entries, GUI_ONLY)
        if found:
            failures.append(
                "%s (the CLI graph) carries GUI-only packages %s - split the "
                "spec's hiddenimports (ADR-0014)"
                % (os.path.basename(path), ", ".join(sorted(found)))
            )

    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", default="dist", help="PyInstaller distpath")
    parser.add_argument(
        "--build",
        default=os.path.join("build", "tta"),
        help="PyInstaller workpath subdirectory holding Analysis-*.toc",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        required=True,
        help="per-executable size ceiling in bytes (ADR-0014 size gate)",
    )
    parser.add_argument(
        "--exe",
        action="append",
        default=None,
        help="executable name to size-check (repeatable; default tta, tta-gui)",
    )
    args = parser.parse_args(argv)

    failures = check(
        args.dist,
        args.build,
        args.max_bytes,
        tuple(args.exe) if args.exe else ("tta", "tta-gui"),
    )
    for line in failures:
        print("ERROR: %s" % line, file=sys.stderr)
        # GitHub Actions annotation.
        if os.environ.get("GITHUB_ACTIONS"):
            print("::error::%s" % line)
    if failures:
        print(
            "\n%d ADR-0014 build gate failure(s). Inspect the Analysis TOCs "
            "for undeclared packages before raising any ceiling." % len(failures),
            file=sys.stderr,
        )
        return 1
    print("\nADR-0014 build gates: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
