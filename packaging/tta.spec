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
win is not worth the flakiness. Run from the repo root:

    pyinstaller packaging/tta.spec --noconfirm
"""

import os

import nltk

block_cipher = None

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
hiddenimports = [
    "tksheet",
    "langdetect",
    "textstat",
    "pypdf",
    "fitz",                                   # PyMuPDF (ADR-0017: may ship)
    "tkinter",
    "matplotlib",
    "matplotlib.backends.backend_tkagg",
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
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=runtime_hooks,
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
gui_a = Analysis(
    [_root("tta", "ui", "tk", "app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=runtime_hooks,
    excludes=[],
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
