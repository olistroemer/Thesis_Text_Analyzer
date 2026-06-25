"""Recent-projects store — the only per-user state outside the project
folder (ADR-0014): ``~/.config/tta/recent.json``."""

from __future__ import annotations

import json
from pathlib import Path

RECENT_PATH = Path.home() / ".config" / "tta" / "recent.json"
DEFAULT_PROJECT_DIR = Path.home() / "TTA-Theses"


def recent_projects(path: Path = RECENT_PATH) -> list[Path]:
    try:
        return [Path(p) for p in json.loads(path.read_text(encoding="utf-8"))["projects"]]
    except (OSError, ValueError, KeyError):
        return []


def remember_project(project_dir: Path, path: Path = RECENT_PATH) -> None:
    projects = [str(Path(project_dir).resolve())]
    projects += [str(p) for p in recent_projects(path) if str(p) != projects[0]]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"projects": projects[:10]}), encoding="utf-8")


def resolve_startup_project(path: Path = RECENT_PATH) -> tuple[Path, bool]:
    """Most recent project, or the default location on first launch
    (US-PROF-AUTO-OPEN). Returns ``(project_dir, is_first_launch)``."""
    for candidate in recent_projects(path):
        if (candidate / "tta.sqlite").exists():
            return candidate, False
    return DEFAULT_PROJECT_DIR, True
