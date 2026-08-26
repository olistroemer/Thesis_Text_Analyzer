"""GUI entry-point tests (ADR-0014, US-PROF-AUTO-OPEN, US-PROF-NO-TRACES).

Replaces the recent.json store tests: there is no store any more. The
pointer is a project file and its resolution belongs to core, covered by
tests/core/test_startup.py. What is left here is what the adapter itself
owns - keeping matplotlib's caches inside the project (SDD Sec. 5.6.2).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tta.ui.tk import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_redirect_caches_points_matplotlib_into_the_project(tmp_path, monkeypatch):
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    app.redirect_caches(tmp_path / "proj")
    assert Path(os.environ["MPLCONFIGDIR"]) == tmp_path / "proj" / ".cache" / "matplotlib"


def test_redirect_caches_leaves_an_explicit_mplconfigdir_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("MPLCONFIGDIR", "/somewhere/mine")
    app.redirect_caches(tmp_path / "proj")
    assert os.environ["MPLCONFIGDIR"] == "/somewhere/mine"


def test_the_external_recent_store_is_gone():
    """#31: the ~/.config/tta/recent.json module must not come back."""
    with pytest.raises(ImportError):
        __import__("tta.ui.tk.recent")


def test_matplotlib_import_writes_nothing_outside_the_project(tmp_path):
    """The audited leak (SDD Sec. 5.6.2), proven in a clean interpreter.

    matplotlib caches its config dir on first import, so this only means
    something out-of-process.
    """
    pytest.importorskip("matplotlib")
    home = tmp_path / "home"
    project = home / "TTA-Theses"
    project.mkdir(parents=True)

    script = "\n".join(
        [
            "from pathlib import Path",
            "from tta.ui.tk import app",
            f"project = Path({str(project)!r})",
            "app.redirect_caches(project)",
            "import matplotlib",
            "from matplotlib.figure import Figure",
            "Figure()",
            f"home = Path({str(home)!r})",
            "escaped = [str(p) for p in home.rglob('*')"
            " if project not in p.parents and p != project]",
            "print('ESCAPED:' + repr(escaped))",
            "print('CONFIGDIR:' + matplotlib.get_configdir())",
            "print('CACHEDIR:' + matplotlib.get_cachedir())",
        ]
    )

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)  # Path.home() on Windows
    env.pop("MPLCONFIGDIR", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    out = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=300
    )
    assert out.returncode == 0, out.stderr
    assert "ESCAPED:[]" in out.stdout, out.stdout
    expected = project / ".cache" / "matplotlib"
    for prefix in ("CONFIGDIR:", "CACHEDIR:"):
        line = [ln for ln in out.stdout.splitlines() if ln.startswith(prefix)][0]
        assert Path(line[len(prefix):]) == expected
