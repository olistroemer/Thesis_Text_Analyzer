# ADR-0014: Distribution as single-file standalone binary

**Status:** Accepted (revised — per **US-PROF-NO-TRACES**, no per-user state is written outside the project folder by default; the `~/.config` recent-projects file is removed; revised again 2026-08-26 to add the normative **clean-environment build** clause, the **size gate**, and the **third-party licence manifest**, after #52 found the first release binary contaminated by undeclared packages; and to record the implemented **per-OS build matrix** with its **packaged-binary acceptance** gates, #4). The **AGPL release gate** in the build pipeline is **superseded by [ADR-0017](0017-license.md)** (the project adopts copyleft; PyMuPDF may ship).
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

The matrix in `.github/workflows/ci.yml` (`build`) is one job per target, each running the same steps from `packaging/tta.spec`:

| target | runner | executables |
|---|---|---|
| `linux-x86_64` | `ubuntu-latest` | `tta`, `tta-gui` |
| `windows-x86_64` | `windows-latest` | `tta.exe`, `tta-gui.exe` |
| `macos-arm64` | `macos-14` | `tta`, `tta-gui` |
| `macos-x86_64` | `macos-15-intel` | `tta`, `tta-gui` |

**Revision (2026-10-12): `macos-13` -> `macos-15-intel`.** GitHub retired the `macos-13` runner image, so the `macos-x86_64` job no longer failed - it never *started*: it sat queued until the run was cancelled hours later, and the `release` job that `needs` it was cancelled with it. `macos-15-intel` is GitHub's remaining Intel macOS image. The target is unchanged; only the machine that freezes it moved. The SDD's macOS 12+ floor is a property of the Python build the binary embeds, not of the runner's OS, and is not re-measured by this change.

Every push and pull request builds all four (a build that only runs on tags is a build that is broken on tag day). `fail-fast` is off, so one platform's failure still yields evidence about the other three. A push of a `v*` tag additionally runs a `release` job that collects the four artefacts and opens a **draft** GitHub release. The draft is deliberate: publishing is the step that needs the #8 licence sign-off and the #6 GDPR statement, and those are human decisions, not CI's.

**Revision (2026-10-12): every push builds; only tags and manual runs upload.** The binaries are built, gated and smoke-tested on every push as before, but the `actions/upload-artifact` step runs only for a `v*` tag (the `release` job needs the four artefacts) and for a manual `workflow_dispatch` run (to fetch a binary for testing, e.g. a Windows `.exe`), and those artefacts expire after 3 days. The reason is storage: the repository is private, so artefacts count against the account's Actions storage quota, and one run's four zipped targets (~200 MB each; the Linux one alone was 217 MB) exceed the free plan's 500 MB. Uploading on every push made jobs on a clean binary fail with "Artifact storage quota has been hit". Release assets are stored separately and do not expire with the artefacts.

**Revision (2026-10-12): only `tta-gui` is uploaded and released.** Both executables in the table above are still frozen, size-gated, graph-checked and manifest-checked on every target, and the CLI is still the binary the acceptance smoke drives (below). But only `tta-gui` (plus `THIRD_PARTY_LICENSES.txt`) is uploaded, and therefore only it reaches the draft release: the CLI's users run it from source ([ADR-0003](0003-cli-first-class.md) revision 2026-10-12). This also roughly halves a tag run's artefact volume (each executable is ~70 MB, Linux measurement below), which is what keeps the four targets inside the storage quota.

Approximate release-build size: ~100 MB per OS. The two gates that keep that number honest — a clean build environment and a hard size ceiling — are specified below; they are what makes the frozen binary a function of the declared dependency set rather than of the builder's machine (**QA-REPRO**, SDD §10).

### Clean-environment build (normative)

**A release binary is only valid if it was frozen in an environment that contains the declared dependency set and nothing else.** PyInstaller freezes whatever its module graph can reach on the build machine's `sys.path`, so a stray package in the builder's *user* site directory silently becomes part of the shipped artefact. This is not hypothetical: the first 212 MB Linux build (#52) carried `llvmlite` (168 MB uncompressed), `scipy` (85 MB), `pandas` (26 MB) and `numba` (10 MB) — ~288 MB of 533 MB uncompressed, **none of them a declared dependency**. `llvmlite` and `numba` were resolved from `~/.local/lib/python3.12/site-packages`, i.e. leftovers from the unrelated exploration work.

Two independent mechanisms let that happen, so the ADR mandates two independent defences:

1. **The user site directory must be disabled at freeze time.** Builds run with **`PYTHONNOUSERSITE=1`** set (equivalently `python -Es`), in a dedicated virtualenv created from `pyproject.toml` alone. A build that can see `~/.local` is not reproducible and must not be released. The check that enforces this has to be per-platform: the matrix freezes on three operating systems and each keeps the per-user site somewhere else (`~/.local/lib`, `~/Library/Python`, `%APPDATA%\Python`), so `packaging/check_build.py` recognises all three plus the freezing interpreter's own answer from `site.getusersitepackages()`. A POSIX-only check would have been green on three of the four targets for precisely the reason this clause exists.
2. **The numeric stack is excluded explicitly in the spec.** Several dependencies contain *function-level* opportunistic imports that PyInstaller's static analysis follows even in a clean environment: `pymupdf/table.py` does `import pandas`, `nltk/parse/transitionparser.py` does `from scipy import sparse`, `pandas.core.missing` pulls `scipy.interpolate`, and `numba`/`llvmlite` enter only through `pandas.core._numba`. `packaging/tta.spec` therefore passes `excludes = ["pandas", "numba", "llvmlite", "scipy", "tqdm.gui", "IPython"]` to **both** `Analysis` calls. This is runtime-safe rather than merely build-safe: every one of those import sites is inside a `try`/`except ImportError` or a code path the application never enters (PyMuPDF table extraction, the NLTK transition parser). No `tta` module imports any of them.

**Per-binary dependency scoping.** The spec builds two executables from two `Analysis` objects. Their `hiddenimports` are *not* shared: `tksheet` and `tkinter` belong to the GUI graph only. (`matplotlib` and its Tk backend were GUI-only too until #53 removed the dependency outright; both binaries now exclude it.) Sharing the list made the CLI binary *larger than the GUI* by carrying 18 MB of matplotlib, plus `mpl_toolkits`, kiwisolver, contourpy, tksheet and `_tcl_data`, which it never executes.

### Size gate (normative)

CI **fails the build** if either produced executable exceeds a per-OS ceiling. The ceiling is a regression tripwire, not a target: it sits above the measured clean-build size with enough headroom to absorb ordinary dependency drift, and low enough that a re-contaminated build cannot pass.

| target | ceiling (per executable) | basis |
|---|---|---|
| Linux x86_64 | **100 MB** | measured: 69.3 MiB CLI / 70.7 MiB GUI (below) |
| Windows x86_64 | **200 MB** | **provisional** — no measurement yet |
| macOS arm64 | **200 MB** | **provisional** — no measurement yet |
| macOS x86_64 | **200 MB** | **provisional** — no measurement yet |

The three provisional ceilings are placeholders with a job to do, not estimates: nobody has yet frozen this application on Windows or macOS, so the honest number is unknown, and a ceiling chosen by analogy would be a guess dressed as a measurement. 200 MB is loose enough that a legitimate first build (Tcl/Tk frameworks, larger platform wheels) will not fail on arrival, and still tight enough to catch the failure it exists for — the contaminated Linux build measured 202.9 MiB, so the numeric stack returning would trip it. **The first green matrix run replaces each provisional row with its measurement**, and the ceiling is then re-tightened to the same ~40 % headroom the Linux row has.

Measured on the build that introduced the gate (Linux x86_64, PyInstaller 6.21.0, `--onefile`, UPX off, CPython 3.12.13). Both rows are real freezes of the *same* tree on the same machine: "before" re-runs the pre-#52 spec with the user site live, "after" is `PYTHONNOUSERSITE=1` plus the excludes below.

| | `tta` (CLI) | `tta-gui` (GUI) |
|---|---|---|
| contaminated build (before) | 212,788,216 B / 202.9 MiB | 212,005,368 B / 202.2 MiB |
| clean build + excludes (#52) | 97,539,152 B / 93.0 MiB | 109,881,080 B / 104.8 MiB |
| matplotlib dropped (#53) | **72,700,872 B / 69.3 MiB** | **74,118,464 B / 70.7 MiB** |
| **saved overall** | **-140.1 MB (-65.8 %)** | **-137.9 MB (-65.0 %)** |

The dependency graphs behind those numbers, uncompressed, per binary:

| graph | before | after | dropped from it |
|---|---|---|---|
| CLI (`Analysis-00.toc`) | 591.3 MB / 4734 entries | 264.5 MB / 2642 entries | llvmlite 168.04, scipy 84.60, pandas 26.07, numba 9.66 (undeclared) + matplotlib 18.36, kiwisolver 5.74, tksheet 1.18, contourpy 1.03, mpl_toolkits 0.24 (GUI-only), in MB |
| GUI (`Analysis-01.toc`) | 589.6 MB / 4562 entries | 291.3 MB / 2830 entries | the undeclared numeric stack only — the plotting and grid stack stays, because the report view executes it |

**On reproducing these numbers.** The "after" figures above were re-measured independently on 2026-08-26 in a throwaway `python -m venv` with `PYTHONNOUSERSITE=1`, via `python packaging/gen_third_party_licenses.py && pyinstaller packaging/tta.spec`. They came out 1.5 MB (CLI) and 0.3 MB (GUI) below the first recorded measurement. Exact byte counts are a function of the resolved wheel versions in the build environment, so they will drift between builds and between builders and are recorded here as evidence, not as a contract. **The contract is the ceiling table above**, which is why the gate in `packaging/check_build.py` asserts a ceiling and the absence of undeclared packages rather than an exact size.

**345 files in each "before" graph were collected from `~/.local/lib/python3.12/site-packages`** (llvmlite and numba). The "after" graphs collect nothing from a user site directory; `packaging/check_build.py` gates on exactly that, and on the absence of the four undeclared packages.

Note the ordering flip, which is what the per-binary scoping buys: before the fix the CLI was the *larger* of the two binaries; after it the CLI was 12.3 MB *smaller* than the GUI. Since #53 removed matplotlib the gap is only 1.4 MB, which is Tk plus tksheet - matplotlib and the numeric/imaging tail it required were most of what the GUI carried alone.

No feature was removed and no dependency was dropped to get there. The Linux ceiling sits ~43 % above the larger measured binary, which absorbs ordinary dependency drift while leaving no room for the numeric stack to return (`scipy` alone is 85 MB uncompressed, and a re-contaminated build lands at ~203 MiB, well over the ceiling). Raising a ceiling requires an ADR revision that states why the growth is a genuine dependency cost; the reflex on a failure is to inspect the build's `Analysis-*.toc` for undeclared packages *first*.

**The `hiddenimports` split is necessary but not sufficient.** `nltk` reaches for matplotlib from *inside method bodies* (`nltk.probability.FreqDist.plot`, `nltk.tokenize.texttiling.demo`, `nltk.parse.dependencygraph.demo`, `nltk.sentiment.util`, `nltk.draw.*`), so the CLI graph kept collecting the whole plotting stack -- matplotlib 18.4 MB plus its pillow / fontTools / kiwisolver / contourpy / freetype / harfbuzz tail -- even after the split. The spec therefore excludes the plotting stack. Since #53 no part of `tta` imports matplotlib, so `matplotlib` and `mpl_toolkits` sit in the **shared** `EXCLUDES` and `CLI_EXCLUDES` adds only `tksheet` and `tkinter`. This is safe for the same reason as the numeric stack: every one of those nltk import sites is inside a `try`/`except ImportError` that raises a "requires matplotlib" message, or inside a `demo()`/`__main__` block, and `tta` uses exactly `nltk.sent_tokenize` and `nltk.word_tokenize`. It stays safe because [ADR-0002](0002-ui-core-boundary.md)'s boundary invariant forbids `tta/core` and `tta/cli` from importing `tta.ui`, so the CLI cannot acquire a genuine need for a GUI dependency without a CI failure first.

The gate is enforced in `.github/workflows/ci.yml` (the `build` matrix) rather than in `pytest`, because it is a property of a produced artefact, not of the source tree. What `pytest` *does* assert is the build **contract** — that the spec still carries the excludes, still keeps the GUI-only imports out of the CLI graph, and that CI still sets `PYTHONNOUSERSITE` — so a regression is caught in the fast suite even when no binary is built (`tests/packaging/`).

### Packaged-binary acceptance (normative)

A build that compiles is not a build that works: the failures freezing introduces — a missing data file, a hook that did not run, an import resolved at build time but absent at run time — appear only when the produced executable is executed. Every matrix job therefore runs the produced binaries before its artefact is uploaded, and a failure fails the build.

**Bundled NLTK data is `punkt_tab` *and* `cmudict`.** `punkt_tab` is `mod_tokenize`'s sentence model; `cmudict` is the English syllable dictionary `textstat` needs for Flesch. Shipping only the first was a live QA-PRIV defect (#75): textstat downloads `cmudict` itself when it is missing, so the binary both reached out and failed English readability outright. Both are collected into `nltk_data/` and reached through the runtime hook that prepends it to `nltk.data.path`.

**The CLI binary is driven end to end** on every target: `version`, `module list`, `--help`, then a real project — `run` over a generated sample PDF, `list --format json`, and `export` — asserting that the run reports zero module errors (read from `run --format json`, never from the human summary line: that line is localised and defaults to German per [ADR-0020](0020-i18n-mechanism.md), so a match on the English `0 errors` failed every target the day the catalogue landed, against a binary that had run cleanly), that the thesis shows successful module runs, and that the export is a SQLite file containing metric rows. That covers the acceptance path of #4 for the CLI, and it is what proves the *bundled* payload works: the NLTK `punkt_tab` model, the SQL migrations, the help markdown, and PyMuPDF extraction are all exercised, not merely present. Measured on the Linux build that introduced this clause: 12 modules ok, 0 errors, 29 metric values exported.

**The GUI binary is launched** under `xvfb-run` on the Linux job with `HOME` pointed at a scratch directory: it must still be running when a timeout kills it (exit status 124, captured with `|| rc=$?`: Actions runs `bash -e`, which would otherwise abort the step on the very status that means "pass"), and it must have created its default project database. That is the check that would have caught a GUI binary whose Tk, tksheet or matplotlib payload did not survive freezing — the stack the CLI deliberately no longer carries, and therefore the stack no other gate touches. Complementing it, `packaging/check_build.py` asserts that the GUI dependency graph *does* contain tksheet and tkinter, so the per-binary scoping cannot over-shoot and strip the GUI's own stack. matplotlib is deliberately **not** on that list any more (#53): it must be absent from both graphs, which the undeclared-package check now enforces.

Two limits are worth stating rather than implying:

- The GUI launch runs on Linux only. Windows and macOS runners have no equivalent of `xvfb-run`, so on those targets the GUI binary is built, size-gated and graph-checked, but never executed. A packaging fault specific to a Windows or macOS Tk build would survive CI.
- "Launch → add → run → **report** → export" is covered up to the report *view*: the report is a GUI surface (ADR-0016), and driving its widget tree inside a frozen windowed binary is beyond what a headless runner can assert. The view itself is covered by `tests/ui` under Xvfb (source, not frozen), and the data it renders is covered by the CLI export above.

### Third-party licence manifest (normative)

**Every distributed binary ships a `THIRD_PARTY_LICENSES.txt`.** This is a licence-compliance requirement, not a nicety. A `--onefile` executable is a distribution of every library inside it, and most of those libraries (MIT, BSD, Apache-2.0, PSF) require their notice and licence text to accompany binary redistribution. Freezing them into an opaque executable with no notices attached is a plain violation, however permissive the licence.

The manifest is **generated at build time**, before PyInstaller runs, and bundled through the spec's `datas`; `packaging/tta.spec` **refuses to build if it is absent**, so a release cannot silently ship without it:

```
python packaging/gen_third_party_licenses.py --output build/licenses/THIRD_PARTY_LICENSES.txt
PYTHONNOUSERSITE=1 pyinstaller packaging/tta.spec --noconfirm
```

`pip-licenses` (declared in the `build` extra) supplies the inventory — name, version, licence, project URL, and the licence text from each distribution's own metadata — which is why the manifest must be generated in the same clean environment that the freeze uses. Build-only tooling (PyInstaller, pip-licenses, setuptools and their dependencies) is filtered out: it is not redistributed. That filter is a **per-platform claim** - `pefile` and `pywin32-ctypes` are named as Windows build-host-only, `macholib` as macOS - and `check_build.py` re-proves it on every build: if one of them turns out to be frozen into a Windows or macOS binary, that build **fails** with the distribution named. The fix in that case is to remove the name from the generator's filter, never to weaken the gate; a missing notice is the direction that is an actual violation. The manifest deliberately **over-reports** rather than under-reports — one file is bundled into both binaries even though the CLI no longer carries the plotting stack, since a surplus notice is harmless and a missing one is the violation.

Three things the inventory alone does not cover, which the generator adds explicitly:

1. **This program's own licence and Corresponding Source.** GPL-3.0-or-later ([ADR-0017](0017-license.md)) obliges us to convey the source. The manifest names the public repository and the release ref, which is the mechanism ADR-0017 §3 relies on.
2. **PyMuPDF's AGPL-3.0 text in full.** PyMuPDF is dual-licensed *AGPL-3.0 or Artifex commercial*; this project distributes under the AGPL option, and AGPL-3.0 §4 requires the licence text to accompany the binary. **Its own `dist-info` does not carry that text** — PyMuPDF ships a 64-character `COPYING` that merely names the dual licence — so `pip-licenses` cannot supply it. The verbatim text is therefore committed at `packaging/licenses/AGPL-3.0.txt` and embedded as an appendix. Committing it (rather than fetching it during the build) keeps the build offline and reproducible.
3. **A prominent PyMuPDF/MuPDF notice**, since it is the one bundled dependency whose licence imposes obligations on whoever redistributes this binary further.

Sections 1 and 2 above are the release prerequisites #8 tracked; the generator makes them a build output rather than a manual checklist item.

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
- ⚠️ A custom project location is remembered only via a pointer *inside* the default project; if both are deleted, the next launch falls back to the default project — accepted, since the no-traces guarantee takes priority. The same fallback applies when the remembered project exists but **cannot be opened** (corrupt `tta.sqlite`, failed migration, permission error): startup reports the reason and opens the default project rather than aborting, because a pointer that selects a broken target would otherwise make every subsequent launch fail with no user-visible way to reset it (see SDD §5.6.1).
- ✅ Step 1 of the professor's happy path stays "start the app".
- ✅ Schema migrations gated behind a defensive backup.
- ✅ Binary contents are a function of the declared dependency set, not of the build machine (QA-REPRO); the size gate makes a re-contaminated build a CI failure rather than a shipped 212 MB download.
- ✅ Licence compliance is a build output: the binary cannot be produced without its third-party notices, and the GPL Corresponding-Source pointer travels with it (ADR-0017).
- ⚠️ The manifest reflects the *build environment*, so it is only as honest as the clean-environment clause above; a contaminated build would also over-report licences.
- ⚠️ Startup ~1–3 s due to PyInstaller unpacking.
- ⚠️ Binary size ~73 MB (CLI) / ~74 MB (GUI) on Linux x86_64; CI ceiling 100 MB per executable.
- ⚠️ The `excludes` list is a standing maintenance item: a future module that genuinely needs `pandas`/`scipy` must be declared in `pyproject.toml` **and** removed from the spec's excludes in the same change, or it will fail only in the frozen binary.
- ⚠️ Unsigned binary → first-run warnings on Windows / macOS (workaround documented).
- ✅ Per-OS build matrix implemented (Linux / Windows / macOS arm64 + x86_64), tag-triggered draft release on top of it; the produced CLI binary is driven end to end on every target before its artefact is published. Artefacts are uploaded only for tags and manual runs (storage quota, revision 2026-10-12).
- ⚠️ The Windows and macOS size ceilings are provisional until the first matrix run measures them.
- ⚠️ The GUI binary is only *executed* by CI on Linux (Xvfb); on Windows and macOS it is built and checked but never launched.

## Revisit when

- Code signing becomes affordable / institutionally required (see SDD §12).
- Startup becomes a complaint (consider Nuitka).
- A declared dependency legitimately pushes a binary past its ceiling — raise the ceiling here, with the measurement, rather than in CI.
- The first green Windows/macOS matrix run lands — replace the provisional ceiling rows with the measurements, and re-tighten them to the Linux row's headroom.
