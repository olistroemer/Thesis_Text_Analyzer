"""`tta.toml` reader/writer (SDD Sec. 5.4).

Unknown keys are preserved on save so future versions and hand edits
survive a round-trip.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

CONFIG_FILENAME = "tta.toml"

UI_MODES = ("basic", "extended")


@dataclass
class Config:
    workers: int | None = None  # None -> runner default max(1, cpus - 1)
    ui_mode: str = "basic"  # basic | extended (SDD Sec. 9.3)
    outlier_scheme: str = "default"  # extended-mode highlighting scheme (Sec. 9.5)
    institution: str | None = None  # used in export filenames and sources row
    # Last-project pointer (SDD Sec. 5.6.1). Only the *default* project's
    # tta.toml is ever consulted for it; it is the whole of the app's
    # cross-launch memory, and it is a project file, so deleting the project
    # folder deletes it too (US-PROF-NO-TRACES).
    last_opened: str | None = None
    raw: dict | None = None  # full parsed file, for round-tripping


def load_config(project_dir: Path | str) -> Config:
    path = Path(project_dir) / CONFIG_FILENAME
    if not path.exists():
        return Config(raw={})
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    ui_mode = raw.get("ui", {}).get("mode", "basic")
    if ui_mode not in UI_MODES:
        ui_mode = "basic"
    # Hand edits and older versions can put anything here; a non-string
    # pointer must be ignored, not carried into a Path() at startup.
    last_opened = raw.get("project", {}).get("last_opened")
    if not isinstance(last_opened, str) or not last_opened.strip():
        last_opened = None
    return Config(
        workers=raw.get("runner", {}).get("workers"),
        ui_mode=ui_mode,
        outlier_scheme=raw.get("ui", {}).get("outlier_scheme", "default"),
        institution=raw.get("project", {}).get("institution"),
        last_opened=last_opened,
        raw=raw,
    )


def save_config(project_dir: Path | str, config: Config) -> None:
    raw = dict(config.raw or {})
    runner = dict(raw.get("runner", {}))
    if config.workers is None:
        runner.pop("workers", None)
    else:
        runner["workers"] = config.workers
    ui = dict(raw.get("ui", {}))
    ui["mode"] = config.ui_mode
    ui["outlier_scheme"] = config.outlier_scheme
    project = dict(raw.get("project", {}))
    if config.institution is None:
        project.pop("institution", None)
    else:
        project["institution"] = config.institution
    if config.last_opened is None:
        project.pop("last_opened", None)
    else:
        project["last_opened"] = config.last_opened
    for key, value in (("runner", runner), ("ui", ui), ("project", project)):
        if value:
            raw[key] = value
        else:
            raw.pop(key, None)
    path = Path(project_dir) / CONFIG_FILENAME
    with open(path, "wb") as fh:
        tomli_w.dump(raw, fh)
