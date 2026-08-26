"""Project facade: one open project directory (SDD Sec. 5.4, ADR-0014).

Both adapters bootstrap through this: migrate the DB (with defensive
backup), open the connection, ensure the single local source. The
binary stays stateless; the project directory is the entire state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tta.core import db
from tta.core.artefacts import ArtefactStore
from tta.core.config import Config, load_config, save_config
from tta.core.db import migrator
from tta.core.db.repository import Repository
from tta.core.events import EventBus
from tta.core.modules.registry import ModuleRegistry, default_registry
from tta.core.runner import Runner

DB_FILENAME = "tta.sqlite"
DEFAULT_PROJECT_DIRNAME = "TTA-Theses"


# -- startup project resolution (SDD Sec. 5.6.1, ADR-0014) -------------------
#
# The app's entire cross-launch memory is one key, `[project].last_opened`,
# in the *default* project's `tta.toml`. Nothing is written under
# ~/.config - deleting the project folders deletes every trace
# (US-PROF-NO-TRACES). Resolution lives in core so both adapters share it.


def default_project_dir() -> Path:
    """The default project location.

    A function rather than a module constant so that pointing HOME
    elsewhere takes effect without re-importing the module.
    """
    return Path.home() / DEFAULT_PROJECT_DIRNAME


def _base_dir(default_dir: Path | str | None) -> Path:
    return Path(default_dir) if default_dir is not None else default_project_dir()


def _same_dir(a: Path | str, b: Path | str) -> bool:
    a, b = Path(a), Path(b)
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return a.absolute() == b.absolute()


def _one_line(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".splitlines()
    return text[0] if text else type(exc).__name__


@dataclass
class StartupTarget:
    """Where startup should open, and whether it is creating that project."""

    project_dir: Path
    first_launch: bool


def last_opened_pointer(default_dir: Path | str | None = None) -> Path | None:
    """The remembered custom project, or ``None``.

    Reads the pointer out of the default project's ``tta.toml``. Creates
    nothing: a missing folder, a missing file, or a non-string value all
    yield ``None``.
    """
    pointer = load_config(_base_dir(default_dir)).last_opened
    return Path(pointer) if pointer else None


def remember_project(project_dir: Path | str, default_dir: Path | str | None = None) -> None:
    """Record ``project_dir`` as the project to open on next start.

    Pointing at the default project clears the pointer instead of storing a
    self-reference. Writing it creates the default project folder if
    needed - that folder is the anchor the pointer lives in.
    """
    base = _base_dir(default_dir)
    target = Path(project_dir).expanduser()
    try:
        target = target.resolve()
    except OSError:
        target = target.absolute()
    base.mkdir(parents=True, exist_ok=True)
    config = load_config(base)
    config.last_opened = None if _same_dir(target, base) else str(target)
    save_config(base, config)


def resolve_startup_project(default_dir: Path | str | None = None) -> StartupTarget:
    """Resolve which project the next launch opens (SDD Sec. 5.6.1)."""
    base = _base_dir(default_dir)
    pointer = last_opened_pointer(base)
    # A remembered directory that still exists wins even without a
    # tta.sqlite: File -> Open may name an empty folder, and the project is
    # created there. A directory that is *gone* is a project the user
    # deleted, and no-traces says that must leave nothing behind, so the
    # stale pointer is ignored and the default project is used.
    if pointer is not None and pointer.is_dir():
        return StartupTarget(pointer, not (pointer / DB_FILENAME).exists())
    return StartupTarget(base, not (base / DB_FILENAME).exists())


def open_startup_project(
    default_dir: Path | str | None = None,
) -> tuple["Project", bool, str | None]:
    """Open the resolved startup project; fall back to the default one.

    Returns ``(project, first_launch, notice)``, where ``notice`` is
    ``None`` on the normal path and a human-readable reason when the
    remembered project could not be opened. Startup must not die on a bad
    pointer: it selects the same broken target on every launch, so an
    unhandled failure here means the app never starts again. The pointer is
    deliberately left in place - the user may want to repair that project -
    and the notice tells them File -> Open resets it.

    A broken *default* project has nothing to fall back to, so it raises.
    """
    base = _base_dir(default_dir)
    target = resolve_startup_project(base)
    try:
        return Project.open(target.project_dir, create=True), target.first_launch, None
    except Exception as exc:
        if _same_dir(target.project_dir, base):
            raise
        notice = (
            f"Could not open the remembered project at {target.project_dir} "
            f"({_one_line(exc)}). Opened the default project at {base} instead - "
            "use File -> Open Project... to choose another."
        )
        first_launch = not (base / DB_FILENAME).exists()
        return Project.open(base, create=True), first_launch, notice


class Project:
    def __init__(self, project_dir: Path, repo: Repository, store: ArtefactStore, config: Config):
        self.dir = project_dir
        self.repo = repo
        self.store = store
        self.config = config

    @classmethod
    def open(cls, project_dir: Path | str, create: bool = False) -> "Project":
        """Open (and migrate) the project at ``project_dir``.

        With ``create=False`` a directory without a ``tta.sqlite`` is
        rejected - guards against silently creating projects in the
        wrong place (CLI: only `tta db init` and `tta run` create).
        """
        project_dir = Path(project_dir)
        db_path = project_dir / DB_FILENAME
        if not db_path.exists() and not create:
            raise FileNotFoundError(
                f"no project at {project_dir} ({DB_FILENAME} missing) - run `tta db init` first"
            )
        project_dir.mkdir(parents=True, exist_ok=True)
        migrator.migrate(db_path)
        config = load_config(project_dir)
        repo = Repository(db.connect(db_path))
        repo.ensure_local_source(
            name=config.institution or "Local", institution=config.institution
        )
        return cls(project_dir, repo, ArtefactStore(project_dir), config)

    def connect(self) -> Repository:
        """A fresh Repository on a new connection to this project's DB, for
        use on a worker thread (sqlite3 connections are thread-affine)."""
        return Repository(db.connect(self.dir / DB_FILENAME))

    def close(self) -> None:
        self.repo.conn.close()

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def make_runner(
        self,
        registry: ModuleRegistry | None = None,
        bus: EventBus | None = None,
        workers: int | None = None,
        repo: Repository | None = None,
    ) -> Runner:
        return Runner(
            repo or self.repo,
            self.store,
            registry or default_registry(),
            bus=bus,
            workers=workers or self.config.workers,
            module_timeout_s=self.config.module_timeout_s,
            thesis_timeout_s=self.config.thesis_timeout_s,
            cancel_grace_s=self.config.cancel_grace_s,
        )
