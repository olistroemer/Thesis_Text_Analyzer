# ADR-0014: Distribution as single-file standalone binary

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** US-ALL-OFFLINE, US-RES-LOW-FRICTION (step 1 = "start the app", not "start the app and then pick a folder"), US-PROF-AUTO-OPEN, QA-PORT.

## Decision

Build per-OS single-file executables with **PyInstaller `--onefile`**. Cross-OS build matrix on CI. Binary is stateless; all persistent data lives in a project directory the user picks on first run (with sensible defaults). **No auto-update**; new versions distributed out-of-band.

## Project-directory model

```
<project>/
├── pds.toml          # configuration
├── pds.sqlite        # the database
└── artefacts/        # cached files
```

The binary itself is stateless. On first launch the app creates `~/PDS-Theses/` (or platform equivalent) as the default project and shows a dismissible banner naming the path. On subsequent launches the app auto-opens the most recently used project. The only per-user state outside the project folder is `~/.config/pds/recent.json` listing recent projects (US-PROF-AUTO-OPEN).

This keeps the professor's happy-path step 1 as "start the app" — never "start the app, then pick a folder".

## Build pipeline

CI matrix builds release binaries on Windows, macOS (arm64 + amd64), and Linux. Tag-triggered. The AGPL release gate (CI grep for `import fitz`/`import pymupdf` under `pds/core/`) blocks the build if PyMuPDF leaks. NLTK data bundled via PyInstaller `--add-data`. UPX disabled (antivirus false positives).

Approximate release-build size: ~100 MB per OS.

## Code signing

MVP ships **unsigned**. Workarounds (SmartScreen "More info → Run anyway", Gatekeeper right-click → Open) documented in release notes. Signing is revisited when deployment to multiple institutions warrants the cost.

## Migrations on launch

DB schema migrations run on app startup against the project's `pds.sqlite`. Before migration, a defensive backup is written to `pds.sqlite.bak.<version>`. Migrations are forward-only. If migration fails, the backup remains and the binary refuses to open the project.

## Alternatives considered

- **Briefcase / native installers**: contradicts "no installer" requirement.
- **Nuitka compiled**: smaller, faster start, but more fragile with tkinter / tksheet / NLTK hooks. Revisit if size or startup become complaints.
- **Onedir distribution** (folder, not single file): smaller and faster but contradicts "single file" requirement.

## Consequences

- ✅ One file to distribute; no installation step.
- ✅ Project folder is the entire state — easy to back up, copy, move.
- ✅ Step 1 of the professor's happy path stays "start the app".
- ✅ Schema migrations gated behind a defensive backup.
- ⚠️ Startup ~1–3 s due to PyInstaller unpacking.
- ⚠️ Binary size ~100 MB.
- ⚠️ Unsigned binary → first-run warnings on Windows / macOS (workaround documented).
- ⚠️ Per-OS CI build matrix required.

## Revisit when

- Code signing becomes affordable / institutionally required (see SDD §12).
- Startup becomes a complaint (consider Nuitka).
