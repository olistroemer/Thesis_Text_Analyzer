"""Add-dialog tests (SDD Sec. 9.7, #62, #61).

No display needed: the Tk dialog functions are stubbed, so the flow logic
(recursive collect, count confirmation, batched add) is what gets exercised.
"""

from types import SimpleNamespace

import pytest

from tta.core.project import Project
from tta.ui.tk import dialogs


@pytest.fixture
def gui_project(tmp_path):
    with Project.open(tmp_path / "proj", create=True) as project:
        yield project


def _tree(root):
    """Two PDFs at the top, one nested, one uppercase, one non-PDF."""
    paths = []
    for rel in ("a.pdf", "b.pdf", "sub/c.pdf", "sub/D.PDF"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-" + rel.encode())
        paths.append(path)
    (root / "readme.txt").write_bytes(b"not a thesis")
    return paths


def _stub(monkeypatch, *, directory, confirm=True):
    calls = SimpleNamespace(info=[], asked=[])
    monkeypatch.setattr(
        dialogs.filedialog, "askdirectory", lambda **kw: str(directory) if directory else ""
    )
    monkeypatch.setattr(
        dialogs.messagebox, "showinfo", lambda *a, **kw: calls.info.append(a)
    )

    def _askyesno(title, message, **kw):
        calls.asked.append(message)
        return confirm

    monkeypatch.setattr(dialogs.messagebox, "askyesno", _askyesno)
    return calls


def test_add_folder_flow_adds_every_pdf_beneath(gui_project, tmp_path, monkeypatch):
    """Recursive, case-insensitive, non-PDFs skipped (#62)."""
    folder = tmp_path / "theses"
    _tree(folder)
    calls = _stub(monkeypatch, directory=folder)

    added = dialogs.add_folder_flow(None, gui_project)

    assert added == 4
    names = sorted(t.pdf_filename for t in gui_project.repo.list_theses())
    assert names == ["D.PDF", "a.pdf", "b.pdf", "c.pdf"]
    # the count is confirmed before anything is written
    assert len(calls.asked) == 1 and "Add 4 PDFs" in calls.asked[0]


def test_add_folder_flow_declined_writes_nothing(gui_project, tmp_path, monkeypatch):
    folder = tmp_path / "theses"
    _tree(folder)
    _stub(monkeypatch, directory=folder, confirm=False)
    assert dialogs.add_folder_flow(None, gui_project) == 0
    assert gui_project.repo.list_theses() == []


def test_add_folder_flow_cancelled_dialog_writes_nothing(gui_project, tmp_path, monkeypatch):
    calls = _stub(monkeypatch, directory=None)
    assert dialogs.add_folder_flow(None, gui_project) == 0
    assert gui_project.repo.list_theses() == []
    assert calls.asked == []  # no confirmation for a cancelled picker


def test_add_folder_flow_reports_an_empty_folder(gui_project, tmp_path, monkeypatch):
    """A folder with no PDFs says so rather than silently doing nothing."""
    empty = tmp_path / "empty"
    empty.mkdir()
    calls = _stub(monkeypatch, directory=empty)
    assert dialogs.add_folder_flow(None, gui_project) == 0
    assert len(calls.info) == 1
    assert calls.asked == []
    assert gui_project.repo.list_theses() == []


def test_add_files_flow_batches_the_whole_selection(gui_project, tmp_path, monkeypatch):
    """The multi-select flow adds in one transaction, not one commit per file
    (#61); a re-selected file still resolves to its existing row."""
    paths = _tree(tmp_path / "theses")
    monkeypatch.setattr(
        dialogs.filedialog, "askopenfilenames", lambda **kw: tuple(str(p) for p in paths)
    )
    assert dialogs.add_files_flow(None, gui_project) == 4
    assert dialogs.add_files_flow(None, gui_project) == 4  # re-add updates in place
    assert len(gui_project.repo.list_theses()) == 4


def test_add_files_flow_cancelled(gui_project, monkeypatch):
    monkeypatch.setattr(dialogs.filedialog, "askopenfilenames", lambda **kw: ())
    assert dialogs.add_files_flow(None, gui_project) == 0
    assert gui_project.repo.list_theses() == []

