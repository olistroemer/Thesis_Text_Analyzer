"""Shared PDF collection for both adapters (SDD Sec. 9.7, ADR-0002).

"Add this folder" has to mean the same thing in the GUI and in `tta run`,
so the recursive walk lives here rather than in either adapter (#62). The
CLI had it privately in `cli/main.py`, which is why the GUI could only
multi-select individual files.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

PDF_SUFFIX = ".pdf"


def is_pdf(path: Path) -> bool:
    """Suffix test, case-**in**sensitively.

    ``rglob("*.pdf")`` is case-sensitive on POSIX, so a ``Thesis.PDF``
    (routine on files that came from a Windows machine) used to be skipped
    silently - no error, just a missing thesis (#62).
    """
    return path.suffix.lower() == PDF_SUFFIX


def collect_pdfs(paths: Iterable[Path | str]) -> list[Path]:
    """Every PDF designated by ``paths``.

    A directory is walked **recursively**; a file is taken as-is if it is a
    PDF and skipped otherwise (so an accidental ``notes.txt`` never becomes a
    thesis that fails extraction). Directories that merely end in ``.pdf`` are
    not files and are skipped too.

    The result is de-duplicated, keeping first appearance, and each directory
    contributes its finds in sorted order - so the same selection always adds
    theses in the same order, which keeps thesis ids reproducible across
    machines for the same folder. Paths are returned exactly as given (not
    resolved): ``theses.pdf_path`` is the add-time dedup key, and silently
    absolutising it would split one thesis into two rows.
    """
    collected: dict[Path, None] = {}
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for found in sorted(p for p in path.rglob("*") if is_pdf(p) and p.is_file()):
                collected[found] = None
        elif is_pdf(path):
            collected[path] = None
    return list(collected)
