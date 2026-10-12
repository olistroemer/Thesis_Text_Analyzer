"""The Help menu's entries and what they open (Sec. 9.2).

Headless where possible: the menu wiring is read from the real window only
in the display-gated tests, which follow the tests/ui/test_smoke.py pattern
and run for real under Xvfb in CI.
"""

import os
import tkinter

import pytest

from tta.core.project import Project


def _display_available() -> bool:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        tkinter.Tk().destroy()
        return True
    except tkinter.TclError:
        return False


display_only = pytest.mark.skipif(not _display_available(), reason="no display")


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
def test_the_privacy_window_shows_the_legal_sections_too(tmp_path):
    """#6: the GUI rendered sections 1-5 only; it must show 6 and 7."""
    from tta.ui.tk.main_window import MainWindow

    with Project.open(tmp_path / "proj", create=True) as project:
        window = MainWindow(project)
        try:
            menu = _help_menu(window)
            menu.invoke(_labels(menu).index("Privacy statement"))
            window.root.update_idletasks()
            texts = [
                child
                for top in window.root.winfo_children()
                if isinstance(top, tkinter.Toplevel)
                for child in top.winfo_children()
                if isinstance(child, tkinter.Text)
            ]
            assert texts, "the privacy window did not open"
            statement = texts[-1].get("1.0", "end")
            assert "## 6. Your rights under GDPR" in statement
            assert "## 7. Controller contact" in statement
            assert "Fachhochschule Wedel gGmbH" in statement
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
