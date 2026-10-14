"""`tta.toml` reader/writer (SDD Sec. 5.4).

Unknown keys are preserved on save so future versions and hand edits
survive a round-trip.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

from tta.core.i18n import SUPPORTED_LOCALES, normalise_locale

CONFIG_FILENAME = "tta.toml"

UI_MODES = ("basic", "extended")

#: UI locales selectable from `tta.toml` (SDD Sec. 9.6, ADR-0020). Re-exported
#: so callers configure the locale without importing core.i18n themselves.
UI_LOCALES = SUPPORTED_LOCALES


@dataclass
class Config:
    workers: int | None = None  # None -> runner default max(1, cpus - 1)
    # ADR-0013 "Timeouts": None -> the runner's own defaults (300 s / 600 s)
    module_timeout_s: float | None = None
    thesis_timeout_s: float | None = None
    cancel_grace_s: float | None = None  # None -> runner default 2 s (#57)
    # ADR-0013 "Recycling" (#86): None -> runner defaults (250 theses /
    # 1024 MiB); 0 disables either safeguard
    recycle_after_theses: int | None = None
    recycle_above_rss_mb: float | None = None
    ui_mode: str = "basic"  # basic | extended (SDD Sec. 9.3)
    # UI locale (SDD Sec. 9.6, ADR-0020). None -> resolve from TTA_LOCALE, else
    # the German default. Deliberately NOT derived from the OS locale.
    ui_locale: str | None = None
    outlier_scheme: str = "default"  # extended-mode highlighting scheme (Sec. 9.5)
    # post-run report offer: ask | always | never (Sec. 9.8.3, #70). Validated
    # where it is consumed (`core.report.should_offer_report`), not here.
    open_report_after_run: str = "ask"
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
    # An unsupported or non-string locale is ignored rather than fatal: a hand
    # edit must not make the application unstartable (ADR-0020).
    ui_locale = normalise_locale(raw.get("ui", {}).get("locale"))
    last_opened = raw.get("project", {}).get("last_opened")
    if not isinstance(last_opened, str) or not last_opened.strip():
        last_opened = None
    return Config(
        workers=raw.get("runner", {}).get("workers"),
        module_timeout_s=raw.get("runner", {}).get("module_timeout_s"),
        thesis_timeout_s=raw.get("runner", {}).get("thesis_timeout_s"),
        cancel_grace_s=raw.get("runner", {}).get("cancel_grace_s"),
        recycle_after_theses=raw.get("runner", {}).get("recycle_after_theses"),
        recycle_above_rss_mb=raw.get("runner", {}).get("recycle_above_rss_mb"),
        ui_mode=ui_mode,
        ui_locale=ui_locale,
        outlier_scheme=raw.get("ui", {}).get("outlier_scheme", "default"),
        open_report_after_run=raw.get("ui", {}).get("open_report_after_run", "ask"),
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
    for key, value in (
        ("module_timeout_s", config.module_timeout_s),
        ("thesis_timeout_s", config.thesis_timeout_s),
        ("cancel_grace_s", config.cancel_grace_s),
        ("recycle_above_rss_mb", config.recycle_above_rss_mb),
    ):
        if value is None:
            runner.pop(key, None)
        else:
            runner[key] = float(value)
    if config.recycle_after_theses is None:
        runner.pop("recycle_after_theses", None)
    else:
        runner["recycle_after_theses"] = int(config.recycle_after_theses)
    ui = dict(raw.get("ui", {}))
    ui["mode"] = config.ui_mode
    if config.ui_locale is None:
        ui.pop("locale", None)  # absent means "resolve it" (ADR-0020)
    else:
        ui["locale"] = config.ui_locale
    ui["outlier_scheme"] = config.outlier_scheme
    ui["open_report_after_run"] = config.open_report_after_run
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
