"""The Help menu's entries and what they open (Sec. 9.2).

Headless where possible: the menu wiring is read from the real window only
in the display-gated tests, which follow the tests/ui/test_smoke.py pattern
and run for real under Xvfb in CI and natively on Windows.
"""

import tkinter

import pytest

from tta.core.project import Project
from tests.ui.conftest import display_available

display_only = pytest.mark.skipif(not display_available(), reason="no display")


def _help_menu(window) -> tkinter.Menu:
    menubar = window.root.nametowidget(window.root.cget("menu"))
    for index in range(menubar.index("end") + 1):
        # the menubar keeps Tk's default tearoff entry at index 0
        if menubar.type(index) == "cascade" and menubar.entrycget(index, "label") == "Help":
            return window.root.nametowidget(menubar.entrycget(index, "menu"))
    raise AssertionError("no Help menu")


def _labels(menu) -> list[str]:
    return [
        menu.entrycget(i, "label")
        for i in range(menu.index("end") + 1)
        if menu.type(i) == "command"
    ]


@display_only
def test_the_privacy_entry_opens_the_help_viewer_on_the_rendered_statement(tmp_path):
    """#92: the menu entry opens the help viewer on its privacy page, with
    all seven sections (#6) - rendered, so no markdown source shows."""
    from tta.core.help_corpus import PRIVACY_URI
    from tta.ui.tk.help_view import HelpWindow
    from tta.ui.tk.main_window import MainWindow

    with Project.open(tmp_path / "proj", create=True) as project:
        window = MainWindow(project)
        try:
            menu = _help_menu(window)
            menu.invoke(_labels(menu).index("Privacy statement"))
            window.root.update_idletasks()
            viewer = window._help_window
            assert isinstance(viewer, HelpWindow)
            assert viewer.current.uri == PRIVACY_URI
            assert viewer.tree.selection() == (PRIVACY_URI,)
            statement = viewer.text.get("1.0", "end")
            assert "In brief" in statement
            assert "6. Responsibility and your rights under GDPR" in statement
            assert "7. Publisher and contact" in statement
            assert "Fachhochschule Wedel gGmbH" in statement
            assert "## " not in statement and "**" not in statement
            assert "|" not in statement
        finally:
            window.root.destroy()


@display_only
def test_the_help_entries_share_one_viewer(tmp_path, monkeypatch):
    """Sec. 9.4.1 (#92, owner decision 2026-11-17): a fresh viewer starts on
    the cover page; with one open, Help topics and the ? Help button only
    raise and focus it and keep its page, while Privacy statement always
    navigates to the privacy page. Never a second window."""
    from tta.core.help_corpus import COVER_URI, PRIVACY_URI
    from tta.ui.tk.main_window import MainWindow

    with Project.open(tmp_path / "proj", create=True) as project:
        window = MainWindow(project)
        try:
            menu = _help_menu(window)
            labels = _labels(menu)
            menu.invoke(labels.index("Help topics"))
            window.root.update_idletasks()
            viewer = window._help_window
            assert viewer.current.uri == COVER_URI
            focused = []
            monkeypatch.setattr(viewer, "focus_force", lambda: focused.append(1))
            # the reader moves on; Help must not pull them back to the cover
            viewer.show_topic("metric:yules_k")
            window._toolbar_buttons["? Help"].invoke()
            window.root.update_idletasks()
            assert window._help_window is viewer
            assert viewer.current.uri == "metric:yules_k"
            menu.invoke(labels.index("Help topics"))
            window.root.update_idletasks()
            assert viewer.current.uri == "metric:yules_k"
            assert len(focused) == 2
            menu.invoke(labels.index("Privacy statement"))
            window.root.update_idletasks()
            assert window._help_window is viewer
            assert viewer.current.uri == PRIVACY_URI
            assert len(focused) == 3
            helps = [
                top
                for top in window.root.winfo_children()
                if isinstance(top, tkinter.Toplevel)
            ]
            assert helps == [viewer]
        finally:
            window.root.destroy()


# -- Help -> Third-party licences (#36) ----------------------------------------


def test_the_licence_window_explains_when_there_is_no_manifest(monkeypatch):
    """Headless: the from-source case yields the explanation, not an error."""
    import sys

    from tta.ui.tk import licenses_view

    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    text, found = licenses_view.licenses_text()
    assert found is False
    assert "packaging/gen_third_party_licenses.py" in text


def test_the_licence_window_shows_the_bundled_manifest(tmp_path, monkeypatch):
    import sys

    from tta.core.third_party_licenses import FILENAME
    from tta.ui.tk import licenses_view

    (tmp_path / FILENAME).write_text("THIRD-PARTY NOTICES", encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert licenses_view.licenses_text() == ("THIRD-PARTY NOTICES", True)


def test_the_absent_message_is_translated():
    """The explanation is user-facing, so it must be in the catalogue."""
    from tta.core import i18n
    from tta.ui.tk import licenses_view

    i18n.install("de")
    try:
        german = i18n._(licenses_view.ABSENT_MESSAGE)
        title = i18n._(licenses_view.WINDOW_TITLE)
    finally:
        i18n.install("en")
    assert german != licenses_view.ABSENT_MESSAGE
    assert "packaging/gen_third_party_licenses.py" in german
    assert title == "Lizenzen Dritter"


@display_only
def test_the_help_menu_has_a_third_party_licences_entry(tmp_path, monkeypatch):
    import sys

    from tta.ui.tk.licenses_view import LicensesWindow
    from tta.ui.tk.main_window import MainWindow

    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    with Project.open(tmp_path / "proj", create=True) as project:
        window = MainWindow(project)
        try:
            menu = _help_menu(window)
            labels = _labels(menu)
            assert labels == ["Help topics", "Privacy statement", "Third-party licences", "About"]
            menu.invoke(labels.index("Third-party licences"))
            window.root.update_idletasks()
            opened = window._licenses_window
            assert isinstance(opened, LicensesWindow)
            assert opened.title() == "Third-party licences"
            assert opened.found is False  # from source: the explanation
            assert "gen_third_party_licenses" in opened.text.get("1.0", "end")
            assert opened.text.cget("state") == "disabled"
        finally:
            window.root.destroy()


@display_only
def test_the_help_page_link_opens_the_licence_window(tmp_path, monkeypatch):
    import sys

    from tta.core.third_party_licenses import FILENAME, LICENSES_URI
    from tta.ui.tk import help_view
    from tta.ui.tk.licenses_view import LicensesWindow

    (tmp_path / FILENAME).write_text("NOTICES", encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    root = tkinter.Tk()
    try:
        viewer = help_view.HelpWindow(root)
        viewer.show_topic("concept:bundled_components")
        assert LICENSES_URI in viewer._link_targets.values()
        viewer._follow(LICENSES_URI)
        assert isinstance(viewer._licenses_window, LicensesWindow)
        assert viewer._licenses_window.text.get("1.0", "end").strip() == "NOTICES"
    finally:
        root.destroy()
