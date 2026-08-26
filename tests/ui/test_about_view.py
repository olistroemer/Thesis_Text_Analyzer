"""About window: version, attribution, SPDX licence, copyable source URL
(Sec. 9.2, ADR-0017, #71).

The URL is a GPL source-availability item, so two things are pinned here:
that it really is selectable/copyable in the window, and that it matches
the packaging metadata in pyproject.toml.
"""

import ast
import inspect
import os
import pathlib
import tkinter
import tomllib

import pytest

import tta
from tta.core.project import Project
from tta.ui.tk import about_view
from tta.ui.tk.about_view import LICENCE_SPDX, REPO_URL, about_lines

PYPROJECT = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"


def _display_available() -> bool:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        tkinter.Tk().destroy()
        return True
    except tkinter.TclError:
        return False


display_only = pytest.mark.skipif(not _display_available(), reason="no display")


@pytest.fixture
def root():
    window = tkinter.Tk()
    yield window
    window.destroy()


# -- content ------------------------------------------------------------------


def test_about_lines_carry_version_attribution_and_licence():
    heading, attribution, licence = about_lines()
    assert tta.__version__ in heading
    assert "FH Wedel" in attribution
    assert LICENCE_SPDX in licence


def test_repo_url_matches_the_packaging_metadata():
    """The About URL and [project.urls] must not drift apart."""
    if not PYPROJECT.is_file():
        pytest.skip("running against an installed package, no pyproject.toml")
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    urls = project["urls"]
    assert urls["Homepage"] == REPO_URL
    assert urls["Source"] == REPO_URL
    assert project["license"] == LICENCE_SPDX


def _imported_modules(module) -> set:
    """Top-level module names imported anywhere in a module's source."""
    names = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_about_never_hands_the_url_to_a_browser():
    """QA-PRIV: no network call, and no browser hand-off to caveat it."""
    assert "webbrowser" not in _imported_modules(about_view)


# -- window (needs a display) -------------------------------------------------


@display_only
def test_window_shows_the_facts_and_a_readonly_copyable_url(root):
    window = about_view.show_about(root)
    try:
        root.update_idletasks()
        assert window.title() == "About"
        labels = [
            child["text"]
            for child in window.winfo_children()[0].winfo_children()
            if "text" in child.keys()
        ]
        rendered = " | ".join(str(text) for text in labels)
        for line in about_lines():
            assert line in rendered
        # the URL lives in a selectable read-only field, not in a label
        assert window.url_entry.get() == REPO_URL
        assert str(window.url_entry["state"]) == "readonly"
    finally:
        window.destroy()


@display_only
def test_copy_button_puts_the_url_on_the_clipboard(root):
    window = about_view.show_about(root)
    try:
        root.clipboard_clear()
        window.copy_button.invoke()
        root.update_idletasks()
        assert root.clipboard_get() == REPO_URL
    except tkinter.TclError as error:  # pragma: no cover - clipboard-less X
        pytest.skip(f"clipboard unavailable: {error}")
    finally:
        window.destroy()


@display_only
def test_help_about_opens_the_window_from_the_main_window(tmp_path):
    from tta.ui.tk.main_window import MainWindow

    with Project.open(tmp_path / "proj", create=True) as project:
        window = MainWindow(project)
        try:
            window._show_about()
            window.root.update_idletasks()
            opened = window._about_window
            assert isinstance(opened, about_view.AboutWindow)
            assert opened.url_entry.get() == REPO_URL
            opened.destroy()
        finally:
            window.root.destroy()
