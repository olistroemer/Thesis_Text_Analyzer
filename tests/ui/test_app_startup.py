"""GUI entry-point tests (ADR-0014, US-PROF-AUTO-OPEN, US-PROF-NO-TRACES).

Replaces the recent.json store tests: there is no store any more. The
pointer is a project file and its resolution belongs to core, covered by
tests/core/test_startup.py. What is left here is what the adapter itself
owns. The matplotlib cache redirect that used to live here went with
the dependency itself (#53): with no matplotlib there is no
~/.config/matplotlib to steer, so SDD Sec. 5.6.2 lists no such path.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tta.ui.tk import app

REPO_ROOT = Path(__file__).resolve().parents[2]




def test_the_external_recent_store_is_gone():
    """#31: the ~/.config/tta/recent.json module must not come back."""
    with pytest.raises(ImportError):
        __import__("tta.ui.tk.recent")



