"""Read-only details panel for a grid cell (SDD Sec. 9.9 "Details panel").

Everything a cell has to say beyond its value is said here rather than in a
hover tooltip (#66): the na reason, the error reason plus - in extended mode -
the traceback, the not-yet-run hint, and the garbled-row explanation.

Deliberately the same shape as ``MainWindow._show_privacy``: a ``Toplevel``
holding a disabled ``Text`` and a ``Scrollbar``, so a long traceback scrolls and
can be selected and copied but not edited.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from tta.core.i18n import N_, _

TITLE = N_("Cell details")


def show_details(parent, heading: str, body: str, title: str | None = None) -> tk.Toplevel:
    """Open the details panel and return it (returned so callers and tests can
    inspect or close it). ``heading`` names the row/column and carries the
    column's one-line help; ``body`` is the state-specific text."""
    window = tk.Toplevel(parent)
    window.title(_(TITLE) if title is None else title)
    window.geometry("640x420")
    text = tk.Text(window, wrap="word")
    text.insert("1.0", f"{heading}\n\n{body}" if heading else body)
    text.configure(state="disabled")
    scrollbar = ttk.Scrollbar(window, command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    text.pack(fill="both", expand=True)
    return window
