"""Third-party licences window (Sec. 9.2, ADR-0014, #36).

Shows the ``THIRD_PARTY_LICENSES.txt`` the release binary carries, in the
same read-only text-window pattern as the privacy statement: a ``Toplevel``
with a disabled ``tk.Text`` and a scrollbar. The file is plain text, not
markdown, so it is shown verbatim in fixed pitch rather than through the
help viewer's renderer, which would read its ``*`` and ``#`` lines as markup.

Where the file comes from is ``core/third_party_licenses.py``'s business
(the frozen bundle root, nothing else). When there is none - a run from
source - the window explains that instead of failing.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from tta.core.i18n import N_, _
from tta.core.third_party_licenses import read_manifest

WINDOW_TITLE = N_("Third-party licences")
ABSENT_MESSAGE = N_(
    "This copy of the program contains no third-party licence file. The file "
    "is generated when a release binary is built and is packed into it, so a "
    "run from the source code does not have one.\n\n"
    "To generate it, run this in the build environment, from the repository "
    "root:\n\n"
    "    python packaging/gen_third_party_licenses.py\n\n"
    "The repository's docs/dependencies.md lists every component with its "
    "purpose and licence."
)


def licenses_text() -> tuple[str, bool]:
    """(text to show, whether it is the bundled manifest)."""
    manifest = read_manifest()
    if manifest is None:
        return _(ABSENT_MESSAGE), False
    return manifest, True


class LicensesWindow(tk.Toplevel):
    """Read-only, scrollable view of the bundled licence manifest."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(_(WINDOW_TITLE))
        self.geometry("800x600")
        content, self.found = licenses_text()
        # The manifest's licence texts are laid out for a fixed-pitch
        # terminal; the explanation is prose and reads better proportional.
        font = "TkFixedFont" if self.found else "TkTextFont"
        self.text = tk.Text(self, wrap="word", font=font, padx=8, pady=6)
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")
        scrollbar = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)


def show_third_party_licenses(parent) -> LicensesWindow:
    return LicensesWindow(parent)
