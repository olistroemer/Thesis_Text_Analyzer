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
     the CLI *larger* than the GUI. Or the mirror image: the excludes that
     keep that stack out of the CLI get applied to the GUI too, and the
     report view dies on first open in a binary that passed every size gate.

  3. A bundled library's licence notice is missing from
     THIRD_PARTY_LICENSES.txt (#4). The manifest is generated from the build
     environment's installed distributions, so a package the binary picks up
     through a runtime hook can end up frozen in with no notice attached -
     which is the direction that is an actual licence violation.

This script checks all of them against a finished build tree and exits
non-zero on any violation, so CI fails instead of publishing the artefact.
Run it from the repo root after PyInstaller:

    python packaging/check_build.py --dist dist --build build/tta \\
        --max-bytes 157286400 \\
        --manifest build/licenses/THIRD_PARTY_LICENSES.txt

The size ceiling is a regression tripwire, not a target (ADR-0014). Raising
it requires an ADR revision that states why the growth is a genuine
dependency cost. On a failure, look for undeclared packages FIRST.
"""

from __future__ import annotations

import argparse
import ast
import importlib.metadata
import os
import re
import site
import sys

# Packages that must not appear in EITHER dependency graph. Not declared in
# pyproject.toml and not imported by any tta module; they arrive through
# function-level optional imports inside pymupdf / nltk / pandas that
# PyInstaller's static analysis follows. See packaging/tta.spec EXCLUDES.
# matplotlib joined this list in #53: since the report became inline SVG
# (ADR-0016 rev. 2) nothing under tta/ imports it, so it belongs in neither
# binary. It is checked rather than merely undeclared because nltk reaches
# for it from inside method bodies, which PyInstaller follows.
# PIL joined in #85: pypdf needs Pillow only to decode images, which
# mod_count_images no longer does (ADR-0021); see packaging/tta.spec.
# "pillow" catches its vendored native libraries (pillow.libs/ on Linux).
# plotly joined in #84: the report embeds the plotly.js bundle (ADR-0016
# rev. 3); the Python package in either graph is contamination.
FORBIDDEN = (
    "pandas", "numba", "llvmlite", "scipy", "matplotlib", "mpl_toolkits", "PIL", "pillow",
    "plotly",
)

# Packages the GUI binary legitimately needs and the CLI binary must never
# carry. The hexagonal boundary (SDD 5.2, ADR-0002) is what makes this
# checkable: nothing under tta/core or tta/cli may import tta.ui.
GUI_ONLY = ("tksheet",)

# ...and the other direction, which is the failure the size gate would
# happily reward: the excludes that keep the plotting stack out of the CLI
# are one edit away from being applied to the GUI too, and the result would
# be a smaller binary that dies the moment the report view opens (ADR-0016).
# Only the GUI *launch* check in CI would otherwise notice, and it runs on
# one of the four targets.
GUI_REQUIRED = ("tksheet", "tkinter")

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

# The licence manifest's bundled filename (ADR-0014, #4).
MANIFEST_NAME = "THIRD_PARTY_LICENSES.txt"


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


def user_site_markers():
    """Lower-cased path fragments that identify a per-user site directory.

    The build matrix runs on three platforms and each puts the user site
    somewhere different, so matching only POSIX ``~/.local/lib`` would have
    made this gate a no-op on Windows and macOS - i.e. green for the exact
    reason it exists. ``site.getusersitepackages()`` is the authoritative
    answer for the interpreter running the check; the literals cover the
    other platforms' conventions, so the gate still bites when the checker
    runs somewhere other than the machine that froze the binary.
    """
    markers = ["/.local/lib/", "/library/python/", "/appdata/roaming/python/"]
    try:
        own = site.getusersitepackages()
    except Exception:  # pragma: no cover - defensive; not raised in practice
        own = None
    if isinstance(own, str) and own:
        markers.append(own.replace("\\", "/").rstrip("/").lower() + "/")
    elif isinstance(own, (list, tuple)):  # pragma: no cover - old platforms
        markers.extend(
            p.replace("\\", "/").rstrip("/").lower() + "/" for p in own
        )
    return tuple(dict.fromkeys(markers))


def user_site_sources(entries, markers=None):
    """TOC entries collected from a per-user site directory.

    Direct evidence of the contamination in #52: a release build must draw
    every file from the build environment, never from the builder's own
    ``~/.local`` (or ``~/Library/Python``, or ``%APPDATA%\\Python``).
    """
    if markers is None:
        markers = user_site_markers()
    hits = set()
    for _dest, source, _kind in entries:
        if not source:
            continue
        probe = source.replace("\\", "/").lower()
        if any(marker in probe for marker in markers):
            hits.add(source)
    return sorted(hits)


# Directory names under site-packages that are not importable packages and
# so cannot be mapped to a distribution by import name.
_NOT_A_PACKAGE = re.compile(
    r"(\.dist-info|\.egg-info|\.egg-link|\.pth|\.libs|__pycache__)$"
)


def normalise_dist(name):
    """PEP 503-ish normalisation, so 'PyYAML' and 'pyyaml' compare equal."""
    return name.strip().lower().replace("_", "-").replace(".", "-")


def bundled_distributions(entries, mapping=None):
    """Distribution names for every site-packages file in a dependency graph.

    Attribution goes through the top-level import name, because that is all a
    TOC records. ``importlib.metadata.packages_distributions()`` supplies the
    import-name -> distribution mapping, which is why this has to run in the
    same environment the freeze used.

    Returns (distributions, unattributed): the second set holds top-level
    names no installed distribution claims (PyInstaller's own bootstrap
    modules, vendored shims, hash-named mypyc extensions). Those are
    reported, not failed on - guessing at them would make the gate flaky.
    """
    if mapping is None:  # pragma: no cover - environment-dependent
        mapping = importlib.metadata.packages_distributions()
    lookup = {normalise_dist(k): v for k, v in mapping.items()}

    distributions, unattributed = set(), set()
    for _dest, source, _kind in entries:
        path = source.replace("\\", "/")
        if "site-packages/" not in path:
            continue
        head = path.split("site-packages/", 1)[1].split("/", 1)[0]
        if _NOT_A_PACKAGE.search(head):
            continue
        top = head[:-3] if head.endswith(".py") else head
        top = top.split(".", 1)[0]
        if not top or top.startswith("-"):
            continue
        claimed = lookup.get(normalise_dist(top))
        if claimed:
            distributions.update(normalise_dist(d) for d in claimed)
        else:
            unattributed.add(top)
    return distributions, unattributed


def manifest_gaps(entries, manifest_text, mapping=None):
    """Bundled distributions with no notice in the licence manifest (#4).

    The manifest names each component in its inventory table, so a substring
    search on the normalised text is enough and stays robust to layout
    changes in the generator.
    """
    distributions, unattributed = bundled_distributions(entries, mapping)
    haystack = normalise_dist(re.sub(r"\s+", " ", manifest_text))
    missing = sorted(
        dist for dist in distributions if normalise_dist(dist) not in haystack
    )
    return missing, sorted(unattributed)


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


def check(
    dist_dir,
    build_dir,
    max_bytes,
    executables=("tta", "tta-gui"),
    manifest=None,
    mapping=None,
):
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

    for path, entries in gui_tocs:
        present = set(offenders(entries, GUI_REQUIRED))
        missing = [pkg for pkg in GUI_REQUIRED if pkg not in present]
        if missing:
            failures.append(
                "%s (the GUI graph) is MISSING %s - the CLI excludes have "
                "over-shot into the GUI, whose report view needs them "
                "(ADR-0014, ADR-0016)"
                % (os.path.basename(path), ", ".join(missing))
            )

    # ---- gate 4: every bundled distribution has a licence notice ----------
    if manifest is not None:
        if not os.path.isfile(manifest):
            failures.append(
                "licence manifest not found at %s - generate it with "
                "packaging/gen_third_party_licenses.py (ADR-0014, #4)" % manifest
            )
        else:
            with open(manifest, "r", encoding="utf-8") as handle:
                manifest_text = handle.read()

            # It must also be BUNDLED, in both graphs - a manifest sitting on
            # the build machine protects nobody.
            for path, entries in cli_tocs + gui_tocs:
                if not any(
                    os.path.basename(dest.replace("\\", "/")) == MANIFEST_NAME
                    for dest, _source, _kind in entries
                ):
                    failures.append(
                        "%s does not bundle %s - add it to the spec's datas "
                        "(ADR-0014, #4)"
                        % (os.path.basename(path), MANIFEST_NAME)
                    )

            all_entries = [e for _p, entries in cli_tocs + gui_tocs for e in entries]
            missing, unattributed = manifest_gaps(
                all_entries, manifest_text, mapping
            )
            if missing:
                failures.append(
                    "THIRD_PARTY_LICENSES.txt has no notice for %d bundled "
                    "distribution(s): %s - a frozen binary redistributes them, "
                    "so their licences must accompany it (ADR-0014, #4)"
                    % (len(missing), ", ".join(missing))
                )
            if unattributed:
                print(
                    "note: %d bundled top-level name(s) map to no installed "
                    "distribution and were not licence-checked: %s"
                    % (len(unattributed), ", ".join(unattributed))
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
    parser.add_argument(
        "--manifest",
        default=None,
        help="THIRD_PARTY_LICENSES.txt to check for licence coverage (#4); "
        "omitted skips that gate",
    )
    args = parser.parse_args(argv)

    failures = check(
        args.dist,
        args.build,
        args.max_bytes,
        tuple(args.exe) if args.exe else ("tta", "tta-gui"),
        manifest=args.manifest,
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
