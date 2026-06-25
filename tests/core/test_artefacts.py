"""Artefact filesystem layout tests (SDD Sec. 5.4, Sec. 8.2)."""

from tta.core import artefact_kinds
from tta.core.artefacts import KIND_FILENAMES, ArtefactStore


def test_every_kind_has_a_filename():
    assert set(KIND_FILENAMES) == artefact_kinds.ALL_KINDS


def test_store_moves_into_layout_and_resolves(tmp_path):
    store = ArtefactStore(tmp_path / "project")
    src = tmp_path / "produced.txt"
    src.write_text("hello", encoding="utf-8")

    relative = store.store(thesis_id=7, run_id=42, kind=artefact_kinds.RAW_TEXT, src=src)

    assert relative == "artefacts/7/42/raw_text.txt"
    assert not src.exists()  # moved, not copied
    resolved = store.resolve(relative)
    assert resolved.read_text(encoding="utf-8") == "hello"
