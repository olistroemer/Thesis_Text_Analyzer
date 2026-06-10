"""Project facade: one open project directory (SDD §5.4, ADR-0014).

Both adapters bootstrap through this: migrate the DB (with defensive
backup), open the connection, ensure the single local source. The
binary stays stateless; the project directory is the entire state.
"""

from __future__ import annotations

from pathlib import Path

from pds.core import db
from pds.core.artefacts import ArtefactStore
from pds.core.config import Config, load_config
from pds.core.db import migrator
from pds.core.db.repository import Repository
from pds.core.events import EventBus
from pds.core.modules.registry import ModuleRegistry, default_registry
from pds.core.runner import Runner

DB_FILENAME = "pds.sqlite"


class Project:
    def __init__(self, project_dir: Path, repo: Repository, store: ArtefactStore, config: Config):
        self.dir = project_dir
        self.repo = repo
        self.store = store
        self.config = config

    @classmethod
    def open(cls, project_dir: Path | str, create: bool = False) -> "Project":
        """Open (and migrate) the project at ``project_dir``.

        With ``create=False`` a directory without a ``pds.sqlite`` is
        rejected — guards against silently creating projects in the
        wrong place (CLI: only `pds db init` and `pds run` create).
        """
        project_dir = Path(project_dir)
        db_path = project_dir / DB_FILENAME
        if not db_path.exists() and not create:
            raise FileNotFoundError(
                f"no project at {project_dir} ({DB_FILENAME} missing) — run `pds db init` first"
            )
        project_dir.mkdir(parents=True, exist_ok=True)
        migrator.migrate(db_path)
        config = load_config(project_dir)
        repo = Repository(db.connect(db_path))
        repo.ensure_local_source(
            name=config.institution or "Local", institution=config.institution
        )
        return cls(project_dir, repo, ArtefactStore(project_dir), config)

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
    ) -> Runner:
        return Runner(
            self.repo,
            self.store,
            registry or default_registry(),
            bus=bus,
            workers=workers or self.config.workers,
        )
