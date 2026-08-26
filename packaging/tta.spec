# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Thesis Text Analyzer release binaries (ADR-0014).

Builds TWO --onefile executables from one analysis-shared base:

  * ``tta``     - the CLI       (tta.cli.main:main)
  * ``tta-gui`` - the Tk GUI    (tta.ui.tk.app:main)

Bundled data (must survive freezing - verified by the CLI smoke test):
  * NLTK ``punkt_tab`` tokenizer model -> ``nltk_data/tokenizers/punkt_tab``
    (mod_tokenize); a runtime hook prepends it to ``nltk.data.path``.
  * SQL migrations ``tta/core/db/migrations/*.sql`` (schema bootstrap).
  * Help markdown ``tta/core/help/**/*.md`` (CLI ``help`` / ``privacy``).

UPX is disabled (ADR-0014): it corrupts some shared objects and the size
win is not worth the flakiness.

Two ADR-0014 gates keep the binary's contents a function of the DECLARED
dependency set rather than of the build machine (QA-REPRO, SDD 10):

  * ``EXCLUDES`` below, applied to BOTH Analysis objects, keeps the numeric
    stack out. Several dependencies reach for it through function-level
    optional imports that PyInstaller's static analysis follows even in a
    clean environment (see the list's own comment).
  * The build must run with ``PYTHONNOUSERSITE=1`` so the builder's user
    site directory cannot contribute. The spec cannot enforce this itself,
    so it FAILS LOUDLY at freeze time if the user site is live (#52: the
    first release binary picked up llvmlite + numba from ~/.local).

Run from the repo root:

    PYTHONNOUSERSITE=1 pyinstaller packaging/tta.spec --noconfirm
"""

import os
import site

import nltk

block_cipher = None

# ---- clean-environment gate (ADR-0014, normative) -------------------------
# PyInstaller freezes whatever its module graph can reach on sys.path, so a
# stray package in the builder's *user* site directory silently ships. That
# is exactly how the first 212 MB binary acquired llvmlite (168 MB) and
# numba (10 MB) from ~/.local (#52). Refuse to build rather than produce an
# artefact whose contents depend on the build machine.
if site.ENABLE_USER_SITE:
    raise SystemExit(
        "packaging/tta.spec: refusing to build with the user site directory "
        "enabled (ADR-0014 clean-environment clause).\n"
        "  user site: %s\n"
        "  fix: PYTHONNOUSERSITE=1 pyinstaller packaging/tta.spec --noconfirm\n"
        "  (or build inside a venv created from pyproject.toml alone)"
        % site.getusersitepackages()
    )

# Paths in this spec are resolved relative to the spec's own directory by
# PyInstaller, so anchor everything at the repo root (parent of packaging/).
# ``SPECPATH`` is injected by PyInstaller at exec time.
ROOT = os.path.dirname(SPECPATH)


def _root(*parts):
    return os.path.join(ROOT, *parts)

# ---- locate the punkt_tab model on the build machine ----------------------
# nltk.data.find returns the resolved directory; we ship its *parent chain*
# (tokenizers/punkt_tab) so the frozen path matches what NLTK looks up.
_punkt_tab = str(nltk.data.find("tokenizers/punkt_tab"))

# ---- package data files (datas: (src, dest_dir_inside_bundle)) ------------
datas = [
    (_punkt_tab, os.path.join("nltk_data", "tokenizers", "punkt_tab")),
    (_root("tta", "core", "db", "migrations"),
     os.path.join("tta", "core", "db", "migrations")),
    (_root("tta", "core", "help"),
     os.path.join("tta", "core", "help")),
]

# ---- imports PyInstaller's static analysis tends to miss ------------------
# Scoped PER BINARY (ADR-0014). Sharing one list is why the CLI binary used
# to be LARGER than the GUI: it carried matplotlib (18.36 MB), mpl_toolkits,
# kiwisolver, contourpy, tksheet (1.18 MB) and _tcl_data (1.95 MB) that it
# can never execute - nothing under tta/core or tta/cli imports them, and
# the boundary invariant (SDD 5.2) guarantees it stays that way.
shared_hiddenimports = [
    "langdetect",                             # mod_classify_language
    "textstat",                               # mod_readability
    "pypdf",                                  # mod_count_images, pdf metadata
    "fitz",                                   # PyMuPDF (ADR-0017: may ship)
]
gui_hiddenimports = shared_hiddenimports + [
    "tkinter",                                # ADR-0001 toolkit
    "tksheet",                                # the data grid
    "matplotlib",                             # report view charts (ADR-0016)
    "matplotlib.backends.backend_tkagg",      # its Tk canvas backend
]

# ---- packages that must never enter either graph (ADR-0014) ---------------
# None of these is a declared dependency and no tta module imports one. They
# get collected anyway because dependencies reach for them from inside
# function bodies, which PyInstaller's static analysis follows:
#
#   pymupdf/table.py            "import pandas as pd"      (table extraction)
#   nltk/parse/transitionparser "from scipy import sparse"  (try/except)
#   pandas/core/missing.py      "scipy.interpolate"
#   numba  <- only via pandas.core._numba.*
#   llvmlite <- only via numba
#
# Uncompressed cost when they land: llvmlite 168 MB, scipy 85 MB, pandas
# 26 MB, numba 10 MB (#52). Excluding them is runtime-safe, not merely
# build-safe: every import site above is guarded or sits on a code path the
# application never enters. A future module that genuinely needs one must be
# declared in pyproject.toml AND dropped from this list in the same change.
EXCLUDES = [
    "pandas",
    "numba",
    "llvmlite",
    "scipy",
    "tqdm.gui",                               # pulls tkinter into the CLI
    "IPython",
]

# ---- additionally kept out of the CLI graph (ADR-0014) --------------------
# Dropping matplotlib/tksheet/tkinter from the CLI's hiddenimports is NOT
# enough on its own: nltk reaches for matplotlib from inside method bodies
# (nltk.probability.FreqDist.plot, nltk.tokenize.texttiling.demo,
# nltk.parse.dependencygraph.demo, nltk.sentiment.util, nltk.draw.*), and
# PyInstaller follows those, so a plotting stack the CLI can never reach was
# still landing in it - matplotlib 18.36 MB plus its own pillow / fontTools /
# kiwisolver / contourpy / freetype / harfbuzz tail.
#
# Safe to exclude: every one of those import sites is inside a try/except
# ImportError that raises a clear "requires matplotlib" message, or inside a
# demo()/__main__ block. ``tta`` uses exactly nltk.sent_tokenize and
# nltk.word_tokenize (tta/core/modules/tokenize.py), never a plot. And the
# CLI cannot acquire a real need for them later without breaking the
# hexagonal boundary invariant (SDD 5.2) that CI already enforces.
CLI_EXCLUDES = EXCLUDES + [
    "matplotlib",
    "mpl_toolkits",
    "tksheet",
    "tkinter",
]

# Spawn-method worker support (#32) is handled by PyInstaller's bundled
# ``pyi_rth_multiprocessing`` hook plus a ``multiprocessing.freeze_support()``
# call at the top of each entry point (tta.cli.main / tta.ui.tk.app); a
# user runtime hook cannot do it because user hooks run BEFORE that bundled
# hook patches ``freeze_support``.
runtime_hooks = [_root("packaging", "rthook_nltk.py")]

# ---- shared analysis: one dependency graph, two entry scripts -------------
cli_a = Analysis(
    [_root("tta", "cli", "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=shared_hiddenimports,
    hookspath=[],
    runtime_hooks=runtime_hooks,
    excludes=CLI_EXCLUDES,
    cipher=block_cipher,
    noarchive=False,
)
gui_a = Analysis(
    [_root("tta", "ui", "tk", "app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=gui_hiddenimports,
    hookspath=[],
    runtime_hooks=runtime_hooks,
    excludes=EXCLUDES,
    cipher=block_cipher,
    noarchive=False,
)

# Two independent --onefile binaries: each must be fully self-contained, so
# we deliberately do NOT MERGE() their graphs (MERGE makes the second exe
# depend on files extracted by the first, which breaks standalone onefile).
cli_pyz = PYZ(cli_a.pure, cli_a.zipped_data, cipher=block_cipher)
gui_pyz = PYZ(gui_a.pure, gui_a.zipped_data, cipher=block_cipher)

cli_exe = EXE(
    cli_pyz,
    cli_a.scripts,
    cli_a.binaries,
    cli_a.datas,
    [],
    name="tta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    gui_a.binaries,
    gui_a.datas,
    [],
    name="tta-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                            # windowed GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
