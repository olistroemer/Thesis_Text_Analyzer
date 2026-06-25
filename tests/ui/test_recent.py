"""recent.json store tests (ADR-0014, US-PROF-AUTO-OPEN)."""

from tta.ui.tk import recent


def test_first_launch_yields_default_dir(tmp_path):
    path = tmp_path / "recent.json"
    project_dir, first = recent.resolve_startup_project(path)
    assert first is True
    assert project_dir == recent.DEFAULT_PROJECT_DIR


def test_remember_and_resolve_most_recent(tmp_path):
    store = tmp_path / "cfg" / "recent.json"
    a = tmp_path / "proj_a"
    b = tmp_path / "proj_b"
    for proj in (a, b):
        proj.mkdir()
        (proj / "tta.sqlite").write_bytes(b"")
        recent.remember_project(proj, store)
    project_dir, first = recent.resolve_startup_project(store)
    assert first is False
    assert project_dir == b.resolve()


def test_stale_entries_are_skipped(tmp_path):
    store = tmp_path / "recent.json"
    gone = tmp_path / "deleted_project"
    gone.mkdir()
    (gone / "tta.sqlite").write_bytes(b"")
    recent.remember_project(gone, store)
    (gone / "tta.sqlite").unlink()
    project_dir, first = recent.resolve_startup_project(store)
    assert first is True  # falls back to default


def test_corrupt_file_is_tolerated(tmp_path):
    store = tmp_path / "recent.json"
    store.write_text("{not json", encoding="utf-8")
    assert recent.recent_projects(store) == []
