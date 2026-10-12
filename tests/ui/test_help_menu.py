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
