"""Locate the bundled third-party licence manifest (ADR-0014, SDD Sec. 9.2, #36).

``THIRD_PARTY_LICENSES.txt`` is generated for a build by
``packaging/gen_third_party_licenses.py`` and frozen into every release
binary by ``packaging/tta.spec``, at the root of the bundle. A frozen
``--onefile`` binary exposes that root as ``sys._MEIPASS`` - the same root
``packaging/rthook_nltk.py`` resolves the NLTK data against - so that is the
one place looked at. A run from source has no bundle and therefore no
manifest; callers get ``None`` and explain, rather than guessing a path into
the repository's ``build/`` tree, which may hold a stale or foreign file.

Toolkit-agnostic on purpose: the GUI shows the file, and nothing stops a
CLI command from doing the same later.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The manifest's file name, as the spec bundles it (``datas`` dest ``.``).
FILENAME = "THIRD_PARTY_LICENSES.txt"

#: The one in-app link target a help page may use (ADR-0012 rev. 4): the GUI
#: help viewer opens the third-party licence window for it.
LICENSES_URI = "app:third_party_licenses"


def bundle_root() -> Path | None:
    """The frozen bundle's extraction root, or None when running from source."""
    root = getattr(sys, "_MEIPASS", None)
    return Path(root) if root else None


def manifest_path() -> Path | None:
    """The bundled manifest, or None if this run has none."""
    root = bundle_root()
    if root is None:
        return None
    candidate = root / FILENAME
    return candidate if candidate.is_file() else None


def read_manifest() -> str | None:
    """The manifest's text, or None if absent or unreadable.

    Unreadable is treated like absent: the caller's explanation is a better
    outcome for the user than a traceback over a notice file.
    """
    path = manifest_path()
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
