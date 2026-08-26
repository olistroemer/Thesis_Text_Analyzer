"""Shared PDF collector tests (SDD Sec. 9.7, ADR-0002, #62).

The GUI and the CLI must agree on what "add this folder" means; this is the
one place that behaviour is pinned down.
"""

from pathlib import Path

from tta.core.discovery import collect_pdfs, is_pdf


def touch(path: Path, content: bytes = b"%PDF-x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_directory_is_walked_recursively(tmp_path):
    top = touch(tmp_path / "a.pdf")
    nested = touch(tmp_path / "sub" / "deep" / "b.pdf")
    touch(tmp_path / "sub" / "notes.txt", b"not a thesis")
    assert collect_pdfs([tmp_path]) == [top, nested]


def test_uppercase_suffix_is_found(tmp_path):
    """`rglob("*.pdf")` is case-sensitive on POSIX, so a `.PDF` from a Windows
    machine used to be skipped silently (#62)."""
    upper = touch(tmp_path / "SCAN.PDF")
    mixed = touch(tmp_path / "Thesis.Pdf")
    assert set(collect_pdfs([tmp_path])) == {upper, mixed}
    assert is_pdf(Path("x.PDF")) and is_pdf(Path("x.pdf")) and not is_pdf(Path("x.txt"))


def test_explicit_file_must_be_a_pdf(tmp_path):
    """A named file is taken as-is when it is a PDF and skipped otherwise, so a
    stray notes.txt never becomes a thesis that fails extraction."""
    pdf = touch(tmp_path / "a.pdf")
    txt = touch(tmp_path / "a.txt", b"text")
    assert collect_pdfs([pdf, txt]) == [pdf]


def test_directory_named_like_a_pdf_is_not_collected(tmp_path):
    (tmp_path / "bundle.pdf").mkdir()
    inner = touch(tmp_path / "bundle.pdf" / "real.pdf")
    assert collect_pdfs([tmp_path]) == [inner]


def test_duplicates_collapse_and_order_is_stable(tmp_path):
    """First appearance wins; each directory contributes its finds sorted, so
    the same selection always adds theses in the same order."""
    a = touch(tmp_path / "one" / "a.pdf")
    b = touch(tmp_path / "one" / "b.pdf")
    c = touch(tmp_path / "two" / "c.pdf")
    assert collect_pdfs([tmp_path / "one", tmp_path / "two", tmp_path / "one", a]) == [a, b, c]


def test_paths_are_returned_as_given_not_resolved(tmp_path, monkeypatch):
    """`theses.pdf_path` is the add-time dedup key; absolutising it silently
    would split one thesis across two rows."""
    touch(tmp_path / "a.pdf")
    monkeypatch.chdir(tmp_path)
    assert collect_pdfs([Path("a.pdf")]) == [Path("a.pdf")]
    assert collect_pdfs([Path(".")]) == [Path("a.pdf")]


def test_empty_and_missing_inputs(tmp_path):
    assert collect_pdfs([]) == []
    assert collect_pdfs([tmp_path]) == []  # empty directory
    assert collect_pdfs([tmp_path / "nope.pdf"]) == [tmp_path / "nope.pdf"]  # existence not checked


def test_both_adapters_delegate_to_this_collector(tmp_path):
    """ADR-0002 / #62: one collector in core, so the GUI and the CLI cannot
    drift on what "add this folder" means."""
    from tta.cli.main import _collect_pdfs
    from tta.ui.tk import dialogs

    touch(tmp_path / "a.pdf")
    touch(tmp_path / "sub" / "B.PDF")
    assert dialogs.collect_pdfs is collect_pdfs  # imported, not re-implemented
    assert _collect_pdfs((tmp_path,)) == collect_pdfs([tmp_path])
    assert len(_collect_pdfs((tmp_path,))) == 2
