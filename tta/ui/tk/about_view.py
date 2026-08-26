"""About window (Sec. 9.2, #71): version, attribution, licence, source URL.

The repository URL is a copyleft compliance item, not decoration: the binary
ships under GPL-3.0-or-later and bundles copyleft dependencies (ADR-0017),
so a recipient holding only the executable must still be able to find the
Corresponding Source. It therefore sits in a selectable read-only field with
a Copy button, which is why this is a Toplevel and not a messagebox.

It is deliberately not a hyperlink: QA-PRIV states the application runs
fully offline with no network access, and this module hands nothing to a
browser (no ``webbrowser`` import) so that claim needs no caveat.

REPO_URL and LICENCE_SPDX are constants rather than ``importlib.metadata``
lookups because the frozen single-file build (ADR-0014) has no dist-info to
read; a test pins them against ``pyproject.toml`` so the two cannot drift.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import tta

REPO_URL = "https://github.com/olistroemer/Thesis_Text_Analyzer"
LICENCE_SPDX = "GPL-3.0-or-later"
ATTRIBUTION = "Data Science Project Group SS26 - FH Wedel"
WINDOW_TITLE = "About"
SOURCE_LABEL = "Source code (GPL Sec. 6), copy the address to visit it:"


def about_lines() -> tuple[str, ...]:
    """The text facts of the About window, in display order."""
    return (
        f"Thesis Text Analyzer {tta.__version__}",
        ATTRIBUTION,
        f"Free software under the GNU General Public License, {LICENCE_SPDX} (SPDX).",
    )


class AboutWindow(tk.Toplevel):
    """Read-only window; the URL field is selectable and copyable."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(WINDOW_TITLE)
        self.resizable(False, False)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        heading, attribution, licence = about_lines()
        ttk.Label(frame, text=heading, font="TkHeadingFont").pack(anchor="w")
        ttk.Label(frame, text=attribution).pack(anchor="w", pady=(2, 10))
        ttk.Label(frame, text=licence, wraplength=420, justify="left").pack(anchor="w")
        ttk.Label(frame, text=SOURCE_LABEL, wraplength=420, justify="left").pack(
            anchor="w", pady=(10, 2)
        )

        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.url_var = tk.StringVar(value=REPO_URL)
        self.url_entry = ttk.Entry(row, textvariable=self.url_var, state="readonly", width=48)
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.copy_button = ttk.Button(row, text="Copy", command=self.copy_url)
        self.copy_button.pack(side="left", padx=(6, 0))

        self.status = ttk.Label(frame, text="")
        self.status.pack(anchor="w", pady=(6, 0))
        ttk.Button(frame, text="Close", command=self.destroy).pack(anchor="e", pady=(12, 0))
        self.url_entry.selection_range(0, "end")
        self.url_entry.focus_set()

    def copy_url(self) -> None:
        """Put the repository URL on the clipboard - no browser involved."""
        self.clipboard_clear()
        self.clipboard_append(REPO_URL)
        self.status.configure(text="Address copied to the clipboard.")


def show_about(parent) -> AboutWindow:
    return AboutWindow(parent)
