# ADR-0014: Distribution as single-file standalone binary

**Status:** Accepted (revised — per **US-PROF-NO-TRACES**, no per-user state is written outside the project folder by default; the `~/.config` recent-projects file is removed; revised again 2026-08-26 to add the normative **clean-environment build** clause and the **size gate**, after #52 found the first release binary contaminated by undeclared packages). The **AGPL release gate** in the build pipeline is **superseded by [ADR-0017](0017-license.md)** (the project adopts copyleft; PyMuPDF may ship).
**Date:** 2026-06-03
**Drivers:** US-ALL-OFFLINE, US-RES-LOW-FRICTION (step 1 = "start the app", not "start the app and then pick a folder"), US-PROF-AUTO-OPEN, US-PROF-NO-TRACES, QA-PORT.

## Decision

Build per-OS single-file executables with **PyInstaller `--onefile`**. Cross-OS build matrix on CI. Binary is stateless; all persistent data lives in a project directory the user picks on first run (with sensible defaults). **No auto-update**; new versions distributed out-of-band.

## Project-directory model

```
<project>/
├── tta.toml          # configuration
├── tta.sqlite        # the database
└── artefacts/        # cached files
```

The binary itself is stateless. On first launch the app creates `~/TTA-Theses/` (or platform equivalent) as the default project and shows a dismissible banner naming the path. **By default the app writes nothing outside the chosen project folder (US-PROF-NO-TRACES).** Subsequent launches auto-open the default project; if the user has opened a different project, the pointer to it is stored *inside the default project folder* (not under `~/.config`), so removing the project folders removes the application's data and every trace of it (US-PROF-AUTO-OPEN). No `~/.config/tta` file is created.

This keeps the professor's happy-path step 1 as "start the app" — never "start the app, then pick a folder".

## Build pipeline

CI matrix builds release binaries on Windows, macOS (arm64 + amd64), and Linux. Tag-triggered. ~~The AGPL release gate (CI grep for `import fitz`/`import pymupdf` under `tta/core/`) blocks the build if PyMuPDF leaks.~~ (Retired by [ADR-0017](0017-license.md) — PyMuPDF may ship under the project's copyleft licence.) NLTK data bundled via PyInstaller `--add-data`. UPX disabled (antivirus false positives).

Approximate release-build size: ~100 MB per OS. The two gates that keep that number honest — a clean build environment and a hard size ceiling — are specified below; they are what makes the frozen binary a function of the declared dependency set rather than of the builder's machine (**QA-REPRO**, SDD §10).

### Clean-environment build (normative)

**A release binary is only valid if it was frozen in an environment that contains the declared dependency set and nothing else.** PyInstaller freezes whatever its module graph can reach on the build machine's `sys.path`, so a stray package in the builder's *user* site directory silently becomes part of the shipped artefact. This is not hypothetical: the first 212 MB Linux build (#52) carried `llvmlite` (168 MB uncompressed), `scipy` (85 MB), `pandas` (26 MB) and `numba` (10 MB) — ~288 MB of 533 MB uncompressed, **none of them a declared dependency**. `llvmlite` and `numba` were resolved from `~/.local/lib/python3.12/site-packages`, i.e. leftovers from the unrelated exploration work.

Two independent mechanisms let that happen, so the ADR mandates two independent defences:

1. **The user site directory must be disabled at freeze time.** Builds run with **`PYTHONNOUSERSITE=1`** set (equivalently `python -Es`), in a dedicated virtualenv created from `pyproject.toml` alone. A build that can see `~/.local` is not reproducible and must not be released.
2. **The numeric stack is excluded explicitly in the spec.** Several dependencies contain *function-level* opportunistic imports that PyInstaller's static analysis follows even in a clean environment: `pymupdf/table.py` does `import pandas`, `nltk/parse/transitionparser.py` does `from scipy import sparse`, `pandas.core.missing` pulls `scipy.interpolate`, and `numba`/`llvmlite` enter only through `pandas.core._numba`. `packaging/tta.spec` therefore passes `excludes = ["pandas", "numba", "llvmlite", "scipy", "tqdm.gui", "IPython"]` to **both** `Analysis` calls. This is runtime-safe rather than merely build-safe: every one of those import sites is inside a `try`/`except ImportError` or a code path the application never enters (PyMuPDF table extraction, the NLTK transition parser). No `tta` module imports any of them.

**Per-binary dependency scoping.** The spec builds two executables from two `Analysis` objects. Their `hiddenimports` are *not* shared: `tksheet`, `tkinter`, `matplotlib` and the Tk backend belong to the GUI graph only. Sharing the list made the CLI binary *larger than the GUI* by carrying 18 MB of matplotlib, plus `mpl_toolkits`, kiwisolver, contourpy, tksheet and `_tcl_data`, which it never executes.

### Size gate (normative)

CI **fails the build** if either produced executable exceeds a per-OS ceiling. The ceiling is a regression tripwire, not a target: it sits above the measured clean-build size with enough headroom to absorb ordinary dependency drift, and low enough that a re-contaminated build cannot pass.

| target | ceiling (per executable) |
|---|---|
| Linux x86_64 | **150 MB** |

Measured on the build that introduced the gate (Linux x86_64, PyInstaller 6.21, `--onefile`, UPX off, CPython 3.12.13):

| | `tta` (CLI) | `tta-gui` | uncompressed graph |
|---|---|---|---|
| contaminated build (before) | 212,449,248 B / 202.6 MiB | 211,666,400 B / 201.9 MiB | 590 MB |
| clean build + excludes (after) | 113,340,488 B / 108.1 MiB | 110,054,328 B / 105.0 MiB | 298 MB |
| **saved** | **-99.1 MB (-46.7 %)** | **-101.6 MB (-48.0 %)** | **-292 MB** |

No feature was removed and no dependency was dropped to get there. The ceiling sits ~39 % above the larger measured binary, which absorbs ordinary dependency drift while leaving no room for the numeric stack to return (`scipy` alone is 85 MB uncompressed). Raising a ceiling requires an ADR revision that states why the growth is a genuine dependency cost; the reflex on a failure is to inspect the build's `Analysis-*.toc` for undeclared packages *first*.

**The `hiddenimports` split is necessary but not sufficient.** `nltk` reaches for matplotlib from *inside method bodies* (`nltk.probability.FreqDist.plot`, `nltk.tokenize.texttiling.demo`, `nltk.parse.dependencygraph.demo`, `nltk.sentiment.util`, `nltk.draw.*`), so the CLI graph kept collecting the whole plotting stack -- matplotlib 18.4 MB plus its pillow / fontTools / kiwisolver / contourpy / freetype / harfbuzz tail -- even after the split. The spec therefore gives the CLI its own `CLI_EXCLUDES = EXCLUDES + [matplotlib, mpl_toolkits, tksheet, tkinter]`. This is safe for the same reason as the numeric stack: every one of those nltk import sites is inside a `try`/`except ImportError` that raises a "requires matplotlib" message, or inside a `demo()`/`__main__` block, and `tta` uses exactly `nltk.sent_tokenize` and `nltk.word_tokenize`. It stays safe because [ADR-0002](0002-ui-core-boundary.md)'s boundary invariant forbids `tta/core` and `tta/cli` from importing `tta.ui`, so the CLI cannot acquire a genuine need for a GUI dependency without a CI failure first.

The gate is enforced in `.github/workflows/ci.yml` (`build-linux`) rather than in `pytest`, because it is a property of a produced artefact, not of the source tree. What `pytest` *does* assert is the build **contract** — that the spec still carries the excludes, still keeps the GUI-only imports out of the CLI graph, and that CI still sets `PYTHONNOUSERSITE` — so a regression is caught in the fast suite even when no binary is built (`tests/packaging/`).

## Code signing

MVP ships **unsigned**. Workarounds (SmartScreen "More info → Run anyway", Gatekeeper right-click → Open) documented in release notes. Signing is revisited when deployment to multiple institutions warrants the cost.

## Migrations on launch

DB schema migrations run on app startup against the project's `tta.sqlite`. Before migration, a defensive backup is written to `tta.sqlite.bak.<version>`. Migrations are forward-only. If migration fails, the backup remains and the binary refuses to open the project.

## Alternatives considered

- **Briefcase / native installers**: contradicts "no installer" requirement.
- **Nuitka compiled**: smaller, faster start, but more fragile with tkinter / tksheet / NLTK hooks. Revisit if size or startup become complaints.
- **Onedir distribution** (folder, not single file): smaller and faster but contradicts "single file" requirement.

## Consequences

- ✅ One file to distribute; no installation step.
- ✅ Project folder is the entire state — easy to back up, copy, move.
- ✅ Nothing is written outside the project folder by default (US-PROF-NO-TRACES): deleting the folder removes the app's data and every trace.
- ⚠️ A custom project location is remembered only via a pointer *inside* the default project; if both are deleted, the next launch falls back to the default project — accepted, since the no-traces guarantee takes priority.
- ✅ Step 1 of the professor's happy path stays "start the app".
- ✅ Schema migrations gated behind a defensive backup.
- ✅ Binary contents are a function of the declared dependency set, not of the build machine (QA-REPRO); the size gate makes a re-contaminated build a CI failure rather than a shipped 212 MB download.
- ⚠️ Startup ~1–3 s due to PyInstaller unpacking.
- ⚠️ Binary size ~100 MB; CI ceiling 150 MB per executable.
- ⚠️ The `excludes` list is a standing maintenance item: a future module that genuinely needs `pandas`/`scipy` must be declared in `pyproject.toml` **and** removed from the spec's excludes in the same change, or it will fail only in the frozen binary.
- ⚠️ Unsigned binary → first-run warnings on Windows / macOS (workaround documented).
- ⚠️ Per-OS CI build matrix required.

## Revisit when

- Code signing becomes affordable / institutionally required (see SDD §12).
- Startup becomes a complaint (consider Nuitka).
- A declared dependency legitimately pushes a binary past its ceiling — raise the ceiling here, with the measurement, rather than in CI.
- The build matrix gains macOS/Windows — each needs its own measured ceiling row.
