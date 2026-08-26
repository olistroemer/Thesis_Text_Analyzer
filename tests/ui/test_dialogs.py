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



# -- remove_thesis_flow (#63) ------------------------------------------------


def _analysed(project, pdf_name="mistake.pdf", tmp_path=None):
    pdf = project.dir / pdf_name
    pdf.write_bytes(b"%PDF-content")
    thesis = project.repo.add_thesis(pdf)
    with project.repo.transaction():
        run_id = project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics={"m": 1})
        src = project.dir / "raw.txt"
        src.write_text("secret extracted text", encoding="utf-8")
        rel = project.store.store(thesis.id, run_id, "raw_text", src)
        project.repo.record_artefact(thesis.id, "raw_text", rel, run_id)
    return thesis


def _capture(monkeypatch, *, confirm):
    seen = SimpleNamespace(asked=[], warned=[], errored=[])
    monkeypatch.setattr(
        dialogs.messagebox, "askyesno",
        lambda title, message, **kw: (seen.asked.append(message), confirm)[1],
    )
    monkeypatch.setattr(
        dialogs.messagebox, "showwarning",
        lambda title, message, **kw: seen.warned.append(message),
    )
    monkeypatch.setattr(
        dialogs.messagebox, "showerror",
        lambda title, message, **kw: seen.errored.append(message),
    )
    return seen


def test_remove_thesis_flow_confirms_then_forgets(gui_project, monkeypatch):
    thesis = _analysed(gui_project)
    tree = gui_project.dir / "artefacts" / str(thesis.id)
    seen = _capture(monkeypatch, confirm=True)

    assert dialogs.remove_thesis_flow(None, gui_project, thesis.id) is True

    assert gui_project.repo.list_theses() == []
    assert not tree.exists()
    # the wording must carry both consequences, not just "deleted"
    message = seen.asked[0]
    assert "mistake.pdf" in message
    assert "forgotten" in message and "re-include" in message
    assert "cannot be undone" in message


def test_remove_thesis_flow_declined_changes_nothing(gui_project, monkeypatch):
    thesis = _analysed(gui_project)
    _capture(monkeypatch, confirm=False)
    assert dialogs.remove_thesis_flow(None, gui_project, thesis.id) is False
    assert len(gui_project.repo.list_theses()) == 1
    assert (gui_project.dir / "artefacts" / str(thesis.id)).exists()


def test_remove_thesis_flow_reports_a_vanished_thesis(gui_project, monkeypatch):
    """A stale grid selection must not raise out of the flow."""
    seen = _capture(monkeypatch, confirm=True)
    assert dialogs.remove_thesis_flow(None, gui_project, 999) is False
    assert len(seen.errored) == 1
    assert seen.asked == []  # nothing to confirm


def test_remove_thesis_flow_warns_on_an_incomplete_artefact_removal(gui_project, monkeypatch):
    """The rows are gone either way; a failed file removal is surfaced, not
    swallowed, and the flow still reports success for the DB half (#11 review
    contract, reused for #63)."""
    thesis = _analysed(gui_project)
    seen = _capture(monkeypatch, confirm=True)
    monkeypatch.setattr(
        "tta.core.artefacts.ArtefactStore.purge",
        lambda self, tid: (_ for _ in ()).throw(PermissionError("file is locked")),
    )

    assert dialogs.remove_thesis_flow(None, gui_project, thesis.id) is True

    assert gui_project.repo.list_theses() == []
    assert len(seen.warned) == 1
    assert "could not be deleted" in seen.warned[0]
