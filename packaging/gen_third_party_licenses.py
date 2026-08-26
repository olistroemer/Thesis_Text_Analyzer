#!/usr/bin/env python3
"""Generate THIRD_PARTY_LICENSES.txt for the frozen binaries (ADR-0014, #4).

A ``--onefile`` executable is a redistribution of every library inside it.
The MIT / BSD / Apache-2.0 / PSF licences in this project's dependency set
all require their notice and licence text to accompany a binary, and
PyMuPDF's AGPL-3.0 (section 4) requires the same. Freezing them into an
opaque executable with no notices attached is a licence violation however
permissive the licences are, so ADR-0014 makes this file a build gate:
``packaging/tta.spec`` refuses to build without it.

Run in the SAME clean environment that the freeze uses (ADR-0014
clean-environment clause) - the inventory is read from the installed
distributions, so a contaminated environment over-reports:

    python packaging/gen_third_party_licenses.py \\
        --output build/licenses/THIRD_PARTY_LICENSES.txt
    PYTHONNOUSERSITE=1 pyinstaller packaging/tta.spec --noconfirm

Two things ``pip-licenses`` cannot supply, which this script adds:

  * This program's own licence and the **Corresponding Source** pointer that
    GPL-3.0-or-later obliges us to convey (ADR-0017 section 3).
  * **PyMuPDF's AGPL-3.0 text.** Its dist-info carries a 64-character
    ``COPYING`` that merely names the "AGPL-3.0 or Artifex Commercial" dual
    licence, so the verbatim text is committed at
    ``packaging/licenses/AGPL-3.0.txt`` and appended here. Committing it
    keeps the build offline and reproducible (QA-REPRO).
"""

from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import json
import os
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
AGPL_TEXT_PATH = REPO_ROOT / "packaging" / "licenses" / "AGPL-3.0.txt"

# The public repository is the Corresponding Source under GPL-3.0-or-later
# (ADR-0017 section 3): distributing the binary alongside a pointer to the
# tagged commit satisfies the obligation. Overridable with --source-url.
DEFAULT_SOURCE_URL = "https://github.com/olistroemer/Thesis_Text_Analyzer"

# Tooling that runs the build WITHOUT contributing code to the binary, so
# its licences do not belong in a notice file. Names are compared
# case-insensitively after normalising -/_ /. separators.
#
# Kept deliberately short. Measured against a real build's Analysis TOCs,
# setuptools, packaging, wheel, pyinstaller and pyinstaller-hooks-contrib DO
# contribute files to the frozen binary (via the setuptools/pkg_resources
# runtime hook and PyInstaller's own bootstrap modules), so denylisting them
# would UNDER-report - the one direction that is an actual violation. Only
# packages proven absent from the graph are listed here, and
# check_build.py's manifest-coverage gate re-proves it on every build.
BUILD_ONLY = frozenset(
    (
        "tta",                 # this program - covered by its own section
        "pip-licenses",        # generates this file; never bundled
        "prettytable",         # pip-licenses dependency
        "wcwidth",             # prettytable dependency
        "pip",
        "altgraph",            # PyInstaller build-graph dep, not frozen in
        "macholib",            # PyInstaller, macOS build host only
        "pefile",              # PyInstaller, Windows build host only
        "pywin32-ctypes",      # PyInstaller, Windows build host only
        "pytest",              # dev extra
        "iniconfig",
        "pluggy",
    )
)

# The one bundled dependency whose licence imposes obligations on anyone who
# redistributes this binary further, so it gets its own prominent section.
COPYLEFT_NOTICE = """\
PyMuPDF (and the MuPDF library it wraps, (C) Artifex Software, Inc.) is
dual-licensed: GNU Affero General Public License v3.0, or a commercial
licence from Artifex. THIS DISTRIBUTION RELIES ON THE AGPL-3.0 OPTION.

If you redistribute this binary, AGPL-3.0 obligations travel with it. The
full licence text is reproduced in Appendix A. PyMuPDF's own source is at
https://github.com/pymupdf/pymupdf ; this program's Corresponding Source is
named in section 1 above.
"""

RULE = "=" * 78
THIN = "-" * 78


def normalise(name):
    """PEP 503-ish name normalisation, for comparing distribution names."""
    return name.strip().lower().replace("_", "-").replace(".", "-")


def parse_requirement(spec):
    """(name, extra_marker) from a PEP 508 requirement string.

    Deliberately small: the only marker this needs to understand is
    ``extra == "..."``, because that is what decides whether an optional
    dependency is part of the shipped closure. Every other marker (platform,
    python_version) is treated as satisfied, which over-includes rather than
    under-includes - the safe direction for a notice file.
    """
    text = spec.strip()
    marker = ""
    if ";" in text:
        text, marker = text.split(";", 1)
    name = re.split(r"[\s\[(<>=!~;]", text.strip(), maxsplit=1)[0]
    extras = re.findall(r"extra\s*==\s*[\"']([^\"']+)[\"']", marker)
    return name, extras


def declared_closure(root="tta", extras=("pymupdf",)):
    """Transitive closure of the DECLARED dependencies of ``root``.

    This is the set of components the binary is *supposed* to contain, read
    from installed metadata (i.e. from pyproject.toml). It is used to
    annotate the inventory: anything installed but outside this closure is a
    sign the generation environment was not clean (ADR-0014), and a notice
    file that silently claims such a package is "redistributed inside the
    executables" would be stating something false.
    """
    closure = set()
    queue = [(root, tuple(extras))]
    while queue:
        name, wanted_extras = queue.pop()
        key = normalise(name)
        if key in closure:
            continue
        closure.add(key)
        try:
            requires = importlib.metadata.requires(name) or []
        except importlib.metadata.PackageNotFoundError:
            continue
        for spec in requires:
            dep_name, dep_extras = parse_requirement(spec)
            if dep_extras and not set(dep_extras) & set(wanted_extras):
                continue
            if dep_name:
                queue.append((dep_name, wanted_extras))
    closure.discard(normalise(root))
    return closure


def collect(python=None):
    """Inventory the installed distributions via pip-licenses.

    Returns the raw list of dicts. pip-licenses is declared in the ``build``
    extra; a missing one is a hard error rather than a silent empty manifest,
    because an empty notice file is worse than no build.
    """
    command = [
        python or sys.executable,
        "-m",
        "piplicenses",
        "--format=json",
        "--with-urls",
        "--with-authors",
        "--with-license-file",
        "--no-license-path",
        # setuptools and wheel are "system packages" that pip-licenses hides
        # by default, but a real build's Analysis TOC shows both contributing
        # files to the binary (via the setuptools/pkg_resources runtime
        # hook). Without this flag their notices go missing, which
        # check_build.py's coverage gate catches - ask for them up front.
        "--with-system",
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=True
        )
    except FileNotFoundError as exc:  # pragma: no cover - env-specific
        raise SystemExit(
            "gen_third_party_licenses: cannot run pip-licenses (%s).\n"
            "  fix: pip install -e '.[build]'" % exc
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "gen_third_party_licenses: pip-licenses failed (exit %d).\n%s"
            % (exc.returncode, exc.stderr.strip())
        )
    return json.loads(completed.stdout)


def redistributed(packages, build_only=BUILD_ONLY):
    """Drop build-only tooling; sort by normalised name for a stable file.

    Over-reporting is deliberate (ADR-0014): one manifest is bundled into
    both binaries even though the CLI no longer carries the plotting stack.
    A surplus notice is harmless; a missing one is the violation.
    """
    denied = {normalise(name) for name in build_only}
    kept = [p for p in packages if normalise(p.get("Name", "")) not in denied]
    return sorted(kept, key=lambda p: normalise(p.get("Name", "")))


def _field(package, key, default="UNKNOWN"):
    value = (package.get(key) or "").strip()
    return value if value and value != "UNKNOWN" else default


def render(
    packages,
    *,
    app_version,
    source_url,
    source_ref,
    agpl_text,
    generated_at,
    closure=None,
):
    """Compose the manifest. Pure function of its inputs, so it is testable.

    ``closure`` is the declared-dependency set from :func:`declared_closure`.
    Components outside it are flagged rather than dropped: they may be
    genuinely bundled (a dependency reached through a runtime hook), or they
    may be evidence that this file was generated in a contaminated
    environment (ADR-0014). Either way, saying so beats silently asserting
    that all 46 packages in someone's exploration env ship in the binary.
    """
    out = []
    add = out.append

    add(RULE)
    add("Thesis Text Analyzer (tta) %s - THIRD-PARTY LICENCE NOTICES" % app_version)
    add(RULE)
    add("")
    add("Generated %s by packaging/gen_third_party_licenses.py (ADR-0014)." % generated_at)
    add("This file lists every third-party component redistributed inside the")
    add("tta / tta-gui executables, with its licence. It may over-report: one")
    add("manifest is bundled into both binaries, and a surplus notice is")
    add("harmless where a missing one would be a licence violation.")
    add("")
    if closure:
        outside = [
            _field(p, "Name")
            for p in packages
            if normalise(p.get("Name", "")) not in closure
        ]
        if outside:
            add("NOTE: %d component(s) below are marked [undeclared]. They are not"
                % len(outside))
            add("in this project's declared dependency closure, so they are either")
            add("reached through a runtime hook or left over from an unclean build")
            add("environment (ADR-0014). They are listed rather than dropped so no")
            add("notice can go missing.")
            add("")

    # ---- 1. this program ---------------------------------------------------
    add(RULE)
    add("1. THIS PROGRAM")
    add(RULE)
    add("")
    add("Thesis Text Analyzer (tta) %s" % app_version)
    add("Licence: GPL-3.0-or-later (see the LICENSE file in the source tree).")
    add("")
    add("CORRESPONDING SOURCE. GPL-3.0-or-later obliges us to convey the source")
    add("for this binary. It is the public repository at:")
    add("")
    add("    %s" % source_url)
    add("    release ref: %s" % source_ref)
    add("")
    add("The tagged commit above is the exact source this binary was built")
    add("from (ADR-0017 section 3).")
    add("")

    # ---- 2. copyleft dependency -------------------------------------------
    add(RULE)
    add("2. IMPORTANT NOTICE - PyMuPDF / MuPDF (AGPL-3.0)")
    add(RULE)
    add("")
    add(COPYLEFT_NOTICE.rstrip())
    add("")

    # ---- 3. inventory ------------------------------------------------------
    add(RULE)
    add("3. BUNDLED COMPONENTS (%d)" % len(packages))
    add(RULE)
    add("")
    if packages:
        width = max(len(_field(p, "Name")) for p in packages)
        width = max(width, len("Component"))
        add("%-*s  %-12s  %s" % (width, "Component", "Version", "Licence"))
        add("%-*s  %-12s  %s" % (width, "-" * width, "-" * 12, "-" * 30))
        for package in packages:
            flag = ""
            if closure and normalise(package.get("Name", "")) not in closure:
                flag = "  [undeclared]"
            add(
                "%-*s  %-12s  %s%s"
                % (
                    width,
                    _field(package, "Name"),
                    _field(package, "Version"),
                    _field(package, "License"),
                    flag,
                )
            )
    else:
        add("(none)")
    add("")

    # ---- 4. per-package detail + licence texts -----------------------------
    add(RULE)
    add("4. LICENCE TEXTS AND NOTICES, PER COMPONENT")
    add(RULE)
    add("")
    add("Texts below are reproduced from each distribution's own metadata.")
    add("Where a distribution ships no licence text, its declared licence and")
    add("project URL are given so the text can be obtained from the source.")
    add("")
    for package in packages:
        name = _field(package, "Name")
        add(THIN)
        add("%s %s" % (name, _field(package, "Version")))
        add(THIN)
        add("Licence: %s" % _field(package, "License"))
        author = _field(package, "Author", "")
        if author:
            add("Author:  %s" % author)
        url = _field(package, "URL", "")
        if url:
            add("URL:     %s" % url)
        add("")
        text = (package.get("LicenseText") or "").strip()
        if text and text.upper() != "UNKNOWN":
            add(text)
        else:
            add("[No licence text in this distribution's metadata. See the")
            add(" project URL above, or Appendix A if the licence named is")
            add(" AGPL-3.0.]")
        add("")

    # ---- appendix ----------------------------------------------------------
    add(RULE)
    add("APPENDIX A - GNU AFFERO GENERAL PUBLIC LICENSE v3.0")
    add(RULE)
    add("")
    add("Reproduced in full because PyMuPDF is distributed here under its")
    add("AGPL-3.0 option and section 4 of that licence requires the text to")
    add("accompany the binary. PyMuPDF's own dist-info does not carry it.")
    add("")
    add(agpl_text.rstrip("\n"))
    add("")
    add(RULE)
    add("End of third-party licence notices.")
    add(RULE)
    return "\n".join(out) + "\n"


def resolve_source_ref(explicit=None):
    """The release ref to name as Corresponding Source.

    Prefers an explicit value (a CI tag), then ``git describe``, and says so
    plainly when it cannot tell - never invents a version.
    """
    if explicit:
        return explicit
    for env_var in ("TTA_RELEASE_REF", "GITHUB_REF_NAME"):
        value = os.environ.get(env_var)
        if value:
            return value
    try:
        completed = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=True,
        )
        described = completed.stdout.strip()
        if described:
            return described
    except (OSError, subprocess.CalledProcessError):
        pass
    return "unknown (built outside a git checkout)"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        default=os.path.join("build", "licenses", "THIRD_PARTY_LICENSES.txt"),
        help="where to write the manifest (default: %(default)s)",
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="public repository conveyed as Corresponding Source",
    )
    parser.add_argument(
        "--source-ref",
        default=None,
        help="release tag/ref (default: TTA_RELEASE_REF, then git describe)",
    )
    parser.add_argument(
        "--agpl-text",
        default=str(AGPL_TEXT_PATH),
        help="verbatim AGPL-3.0 text to append as Appendix A",
    )
    args = parser.parse_args(argv)

    agpl_path = pathlib.Path(args.agpl_text)
    if not agpl_path.is_file():
        raise SystemExit(
            "gen_third_party_licenses: missing AGPL-3.0 text at %s.\n"
            "  PyMuPDF ships under AGPL-3.0 here and its own metadata does "
            "not carry the text; ADR-0014 requires it in the manifest." % agpl_path
        )
    agpl_text = agpl_path.read_text(encoding="utf-8")
    if "GNU AFFERO GENERAL PUBLIC LICENSE" not in agpl_text:
        raise SystemExit(
            "gen_third_party_licenses: %s does not look like the AGPL-3.0 "
            "text." % agpl_path
        )

    try:
        import tta

        app_version = tta.__version__
    except Exception:  # pragma: no cover - only if the tree is unimportable
        app_version = "unknown"

    packages = redistributed(collect())
    if not packages:
        raise SystemExit(
            "gen_third_party_licenses: pip-licenses reported no "
            "redistributable packages. That cannot be right - refusing to "
            "write an empty notice file."
        )

    closure = declared_closure()
    outside = sorted(
        _field(p, "Name")
        for p in packages
        if normalise(p.get("Name", "")) not in closure
    )
    if outside:
        print(
            "warning: %d installed package(s) are outside the declared "
            "dependency closure and are marked [undeclared] in the manifest: "
            "%s" % (len(outside), ", ".join(outside)),
            file=sys.stderr,
        )
        print(
            "warning: generate this file in the clean build environment "
            "(ADR-0014) if that list is not what you expect.",
            file=sys.stderr,
        )

    manifest = render(
        packages,
        app_version=app_version,
        source_url=args.source_url,
        source_ref=resolve_source_ref(args.source_ref),
        agpl_text=agpl_text,
        closure=closure,
        generated_at=datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        ),
    )

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(manifest, encoding="utf-8")
    print(
        "wrote %s (%d components, %d bytes)"
        % (output, len(packages), len(manifest.encode("utf-8")))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
