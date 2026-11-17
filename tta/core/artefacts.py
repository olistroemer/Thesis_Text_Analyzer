"""Filesystem layer for cached artefact files (SDD Sec. 5.4, Sec. 8.2).

Layout: ``<project>/artefacts/<thesis_id>/<run_id>/<kind>.<ext>`` -
integers only, filesystem-safe on all OSes. The DB references artefacts
by path relative to the project directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tta.core import artefact_kinds

#: Canonical on-disk filename per kind (SDD Sec. 8.2).
KIND_FILENAMES = {
    artefact_kinds.RAW_TEXT: "raw_text.txt",
    artefact_kinds.PROSE_TEXT: "prose_text.txt",
    artefact_kinds.LANGUAGE: "language.json",
    artefact_kinds.TOKENS: "tokens.json",
    artefact_kinds.PDF_METADATA: "pdf_metadata.json",
}


class ArtefactStore:
    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)

    def store(self, thesis_id: int, run_id: int, kind: str, src: Path) -> str:
        """Move a module-produced file into the layout; returns the
        project-relative path recorded in ``artefact_files``."""
        relative = Path("artefacts") / str(thesis_id) / str(run_id) / KIND_FILENAMES[kind]
        dest = self.project_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), dest)  # shutil.move: workdirs may sit on another filesystem
        return relative.as_posix()

    def resolve(self, relative_path: str) -> Path:
        return self.project_dir / relative_path

    def purge(self, thesis_id: int) -> None:
        """Delete a thesis's entire on-disk artefact subtree
        ``artefacts/<thesis_id>/`` (the PII-bearing files: raw_text, prose_text,
        tokens, pdf_metadata). Used by the excluded-thesis scrub (US-PROF-EXCLUDE,
        ADR-0006 rev. 5, #11).

        A no-op if the subtree does not exist (a thesis excluded before it was
        ever analysed cached nothing). A failure to remove existing files (e.g.
        a locked or permission-denied file on Windows) is deliberately NOT
        swallowed - it raises so the caller can surface that the local scrub was
        incomplete, rather than report a false success (#11 review). The files
        never leave this machine (ADR-0007), so an incomplete scrub is a
        local-only defence-in-depth warning, not a disclosure."""
        target = self.project_dir / "artefacts" / str(thesis_id)
        if target.exists():
            shutil.rmtree(target)
