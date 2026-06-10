"""Filesystem layer for cached artefact files (SDD §5.4, §8.2).

Layout: ``<project>/artefacts/<thesis_id>/<run_id>/<kind>.<ext>`` —
integers only, filesystem-safe on all OSes. The DB references artefacts
by path relative to the project directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pds.core import artefact_kinds

#: Canonical on-disk filename per kind (SDD §8.2).
KIND_FILENAMES = {
    artefact_kinds.RAW_TEXT: "raw_text.txt",
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
