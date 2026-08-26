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
    # ADR-0013 "Timeouts": None -> the runner's own defaults (300 s / 600 s)
    module_timeout_s: float | None = None
    thesis_timeout_s: float | None = None
    cancel_grace_s: float | None = None  # None -> runner default 2 s (#57)
    ui_mode: str = "basic"  # basic | extended (SDD Sec. 9.3)
    outlier_scheme: str = "default"  # extended-mode highlighting scheme (Sec. 9.5)
    institution: str | None = None  # used in export filenames and sources row
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
    return Config(
        workers=raw.get("runner", {}).get("workers"),
        module_timeout_s=raw.get("runner", {}).get("module_timeout_s"),
        thesis_timeout_s=raw.get("runner", {}).get("thesis_timeout_s"),
        cancel_grace_s=raw.get("runner", {}).get("cancel_grace_s"),
        ui_mode=ui_mode,
        outlier_scheme=raw.get("ui", {}).get("outlier_scheme", "default"),
        institution=raw.get("project", {}).get("institution"),
        raw=raw,
    )


def save_config(project_dir: Path | str, config: Config) -> None:
    raw = dict(config.raw or {})
    runner = dict(raw.get("runner", {}))
    if config.workers is None:
        runner.pop("workers", None)
    else:
        runner["workers"] = config.workers
    for key, value in (
        ("module_timeout_s", config.module_timeout_s),
        ("thesis_timeout_s", config.thesis_timeout_s),
        ("cancel_grace_s", config.cancel_grace_s),
    ):
        if value is None:
            runner.pop(key, None)
        else:
            runner[key] = float(value)
    ui = dict(raw.get("ui", {}))
    ui["mode"] = config.ui_mode
    ui["outlier_scheme"] = config.outlier_scheme
    project = dict(raw.get("project", {}))
    if config.institution is None:
        project.pop("institution", None)
    else:
        project["institution"] = config.institution
    for key, value in (("runner", runner), ("ui", ui), ("project", project)):
        if value:
            raw[key] = value
        else:
            raw.pop(key, None)
    path = Path(project_dir) / CONFIG_FILENAME
    with open(path, "wb") as fh:
        tomli_w.dump(raw, fh)
