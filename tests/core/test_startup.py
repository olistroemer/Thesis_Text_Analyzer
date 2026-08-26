"""Startup project resolution and the no-traces guarantee.

Covers SDD Sec. 5.6.1 / 5.6.2, ADR-0014, US-PROF-AUTO-OPEN and
US-PROF-NO-TRACES, plus the #41 regressions: a startup that used to
discard the user's File -> Open choice, or die on it permanently.
"""

import pytest

from tta.core.config import Config, load_config, save_config
from tta.core.project import (
    DB_FILENAME,
    Project,
    default_project_dir,
    last_opened_pointer,
    open_startup_project,
    remember_project,
    resolve_startup_project,
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """An empty HOME, so a sweep can prove nothing escaped the project."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Path.home() on Windows
    return home


def _make_project(path):
    path.mkdir(parents=True, exist_ok=True)
    Project.open(path, create=True).close()
    return path


# -- resolution --------------------------------------------------------------


def test_default_project_dir_follows_home(fake_home):
    assert default_project_dir() == fake_home / "TTA-Theses"


def test_first_launch_resolves_to_the_default_project(tmp_path):
    base = tmp_path / "TTA-Theses"
    target = resolve_startup_project(base)
    assert target.project_dir == base
    assert target.first_launch is True


def test_second_launch_is_not_a_first_launch(tmp_path):
    base = _make_project(tmp_path / "TTA-Theses")
    target = resolve_startup_project(base)
    assert target.project_dir == base
    assert target.first_launch is False


def test_reading_the_pointer_creates_nothing(tmp_path):
    base = tmp_path / "TTA-Theses"
    assert last_opened_pointer(base) is None
    assert not base.exists()


def test_remembered_project_wins_over_the_default(tmp_path):
    base = _make_project(tmp_path / "TTA-Theses")
    other = _make_project(tmp_path / "elsewhere" / "Theses")
    remember_project(other, base)
    target = resolve_startup_project(base)
    assert target.project_dir == other.resolve()
    assert target.first_launch is False


def test_pointer_lives_in_the_default_projects_toml(tmp_path):
    base = _make_project(tmp_path / "TTA-Theses")
    other = _make_project(tmp_path / "other")
    remember_project(other, base)
    raw = (base / "tta.toml").read_text(encoding="utf-8")
    assert str(other.resolve()) in raw
    assert load_config(base).last_opened == str(other.resolve())


def test_remembering_the_default_project_clears_the_pointer(tmp_path):
    base = _make_project(tmp_path / "TTA-Theses")
    other = _make_project(tmp_path / "other")
    remember_project(other, base)
    remember_project(base, base)  # user goes back home
    assert last_opened_pointer(base) is None
    assert resolve_startup_project(base).project_dir == base


def test_remembering_creates_the_default_project_folder(tmp_path):
    """The pointer's anchor must exist even if the user never opened it."""
    base = tmp_path / "TTA-Theses"
    other = _make_project(tmp_path / "other")
    remember_project(other, base)
    assert (base / "tta.toml").exists()


def test_deleted_remembered_project_falls_back_to_default(tmp_path):
    """Deleting a project folder must leave nothing behind (ADR-0014)."""
    import shutil

    base = _make_project(tmp_path / "TTA-Theses")
    other = _make_project(tmp_path / "gone")
    remember_project(other, base)
    shutil.rmtree(other)
    target = resolve_startup_project(base)
    assert target.project_dir == base
    assert target.first_launch is False


# -- #41: the File -> Open choice used to be discarded -----------------------


def test_remembered_empty_folder_becomes_the_project(tmp_path):
    """#41: File -> Open on a folder that is not yet a project.

    The first-launch banner tells the user to pick a different location
    with File -> Open, so an empty folder is a legitimate choice. Startup
    used to skip it (no tta.sqlite) and silently reopen the old project.
    """
    base = _make_project(tmp_path / "TTA-Theses")
    chosen = tmp_path / "Documents" / "MyTheses"
    chosen.mkdir(parents=True)
    remember_project(chosen, base)

    target = resolve_startup_project(base)
    assert target.project_dir == chosen.resolve()
    assert target.first_launch is True  # banner names the new location

    project, first_launch, notice = open_startup_project(base)
    try:
        assert project.dir == chosen.resolve()
        assert first_launch is True
        assert notice is None
        assert (chosen / DB_FILENAME).exists()
    finally:
        project.close()


# -- #41: a bad pointer used to make the app unstartable, permanently -------


@pytest.mark.parametrize(
    "name, break_it",
    [
        # a foreign or truncated file where the DB should be: sqlite3 raises
        # DatabaseError("file is not a database")
        ("corrupt_db", lambda d: (d / DB_FILENAME).write_bytes(b"%PDF-1.7 not a database\n" * 40)),
        # a directory in the DB's place: OperationalError("unable to open ...")
        ("db_is_a_directory", lambda d: (d / DB_FILENAME).mkdir()),
    ],
)
def test_unopenable_remembered_project_falls_back_with_a_notice(tmp_path, name, break_it):
    """#41: startup must not die on the remembered project.

    The pointer selects the same broken target on every launch, so an
    unhandled failure here means the GUI never starts again.
    """
    base = _make_project(tmp_path / "TTA-Theses")
    broken = tmp_path / name
    broken.mkdir()
    break_it(broken)
    remember_project(broken, base)

    project, first_launch, notice = open_startup_project(base)
    try:
        assert project.dir == base
        assert first_launch is False
        assert notice is not None
        assert str(broken.resolve()) in notice
        assert "File -> Open" in notice
    finally:
        project.close()


def test_fallback_keeps_the_pointer_so_the_user_can_repair_it(tmp_path):
    base = _make_project(tmp_path / "TTA-Theses")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / DB_FILENAME).write_bytes(b"not a database" * 40)
    remember_project(broken, base)
    open_startup_project(base)[0].close()
    assert last_opened_pointer(base) == broken.resolve()


def test_broken_default_project_still_raises(tmp_path):
    """Nothing to fall back to: the error must not be swallowed."""
    base = tmp_path / "TTA-Theses"
    base.mkdir()
    (base / DB_FILENAME).write_bytes(b"not a database" * 40)
    with pytest.raises(Exception):
        open_startup_project(base)


@pytest.mark.parametrize("value", ["123", '["/tmp/a"]', '""', '"   "'])
def test_malformed_pointer_is_ignored(tmp_path, value):
    """A hand-edited or older-version pointer must not reach Path()."""
    base = _make_project(tmp_path / "TTA-Theses")
    (base / "tta.toml").write_text(f"[project]\nlast_opened = {value}\n", encoding="utf-8")
    assert last_opened_pointer(base) is None
    assert resolve_startup_project(base).project_dir == base


# -- pointer round-trips through the UI's own config saves ------------------


def test_pointer_survives_a_ui_config_save(tmp_path):
    """The View menu writes tta.toml too; it must not drop the pointer."""
    base = _make_project(tmp_path / "TTA-Theses")
    other = _make_project(tmp_path / "other")
    remember_project(other, base)

    config = load_config(base)          # what MainWindow holds
    config.ui_mode = "extended"         # what _mode_changed does
    save_config(base, config)

    assert load_config(base).last_opened == str(other.resolve())
    assert load_config(base).ui_mode == "extended"


# -- #31 acceptance: no writes outside the project folder -------------------


def test_startup_and_use_write_nothing_outside_the_project(fake_home, english_pdf):
    """US-PROF-NO-TRACES: sweep HOME after a realistic session."""
    project, first_launch, notice = open_startup_project()
    assert first_launch is True and notice is None
    project_dir = project.dir
    try:
        thesis = project.repo.add_thesis(english_pdf)
        with project.repo.transaction():
            project.repo.record_run(
                thesis.id, "mod_surface_counts", "0.1.0", "ok", metrics={"word_count": 9000}
            )
        config = project.config
        config.ui_mode = "extended"
        save_config(project_dir, config)
    finally:
        project.close()

    remember_project(project_dir)  # File -> Open back onto the default

    escaped = [
        p for p in fake_home.rglob("*")
        if project_dir not in p.parents and p != project_dir
    ]
    assert escaped == [], f"wrote outside the project: {escaped}"
    assert not (fake_home / ".config").exists()
    assert not (fake_home / ".cache").exists()


def test_a_custom_project_only_adds_the_default_projects_pointer(fake_home):
    """Working elsewhere still writes only inside project folders."""
    custom = fake_home / "Documents" / "Theses"
    custom.mkdir(parents=True)
    remember_project(custom)
    project, _, notice = open_startup_project()
    try:
        assert project.dir == custom.resolve()
        assert notice is None
    finally:
        project.close()

    projects = {default_project_dir(), custom}
    # the test made home/Documents itself; only its *contents* are the app's
    allowed = projects | {p for proj in projects for p in proj.parents}
    escaped = [
        p for p in fake_home.rglob("*")
        if not any(a == p or a in p.parents for a in projects) and p not in allowed
    ]
    assert escaped == [], f"wrote outside every project: {escaped}"
    assert not (fake_home / ".config").exists()
