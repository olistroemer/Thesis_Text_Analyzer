"""Locating the bundled licence manifest (ADR-0014, SDD Sec. 9.2, #36).

The frozen layout is simulated by pointing ``sys._MEIPASS`` at a temporary
directory - exactly the attribute PyInstaller's bootloader sets, and the one
``packaging/rthook_nltk.py`` reads for the NLTK data. The real frozen check
is the release smoke in CI; this pins the lookup rule itself.
"""

import ast
import pathlib
import sys

import pytest

from tta.core import third_party_licenses as tpl

SPEC = pathlib.Path(__file__).resolve().parents[2] / "packaging" / "tta.spec"


def test_from_source_there_is_no_bundle_and_no_manifest(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert tpl.bundle_root() is None
    assert tpl.manifest_path() is None
    assert tpl.read_manifest() is None


def test_the_manifest_is_found_at_the_frozen_bundle_root(tmp_path, monkeypatch):
    (tmp_path / tpl.FILENAME).write_text("pymupdf\nAGPL text\n", encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert tpl.bundle_root() == tmp_path
    assert tpl.manifest_path() == tmp_path / tpl.FILENAME
    assert tpl.read_manifest() == "pymupdf\nAGPL text\n"


def test_a_bundle_without_the_manifest_is_reported_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert tpl.manifest_path() is None
    assert tpl.read_manifest() is None


def test_the_lookup_matches_where_the_spec_bundles_the_file():
    """The spec's `datas` entry for the manifest must land at the bundle
    root under the same name the runtime looks for."""
    if not SPEC.is_file():
        pytest.skip("running against an installed package, no packaging/tta.spec")
    tree = ast.parse(SPEC.read_text(encoding="utf-8"))
    assigned = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert ast.literal_eval(assigned["LICENSES_DEST"]) == tpl.FILENAME
    datas = assigned["datas"]
    assert any(
        isinstance(entry, ast.Tuple)
        and isinstance(entry.elts[0], ast.Name)
        and entry.elts[0].id == "_licenses"
        and ast.literal_eval(entry.elts[1]) == "."
        for entry in datas.elts
    ), "the manifest is no longer bundled at the archive root"
