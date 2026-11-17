"""The researcher-side generator tools/reference_aggregates.py (ADR-0025):
a synthetic reference project plus a synthetic harvest DB in, a valid
aggregate file out - read-only on both inputs."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from tta.core import reference

TOOL = Path(__file__).resolve().parents[2] / "tools" / "reference_aggregates.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("tta_reference_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_ddc_parsing(tool):
    eth = "<dc:subject>info:eu-repo/classification/ddc/621.3</dc:subject>"
    edoc = "<dc:subject>ddc:330</dc:subject><dc:subject>004 Informatik</dc:subject>"
    assert tool.ddc_codes(eth) == ["621.3"]
    assert tool.ddc_codes(edoc) == ["330", "004"]
    assert tool.ddc_main_class("621.3") == "600"
    assert tool.ddc_main_class("004") == "000"
    assert tool.ddc_main_class("x") is None and tool.ddc_main_class(None) is None


def _harvest(root: Path, host: str, records: dict[str, str]) -> None:
    folder = root / host
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "theses.sqlite")
    conn.execute("CREATE TABLE downloads (handle TEXT, pdf_path TEXT)")
    conn.execute("CREATE TABLE records (handle TEXT, deleted INTEGER, raw_record_xml TEXT)")
    for stem, ddc in records.items():
        handle = stem.replace("_", "/")
        conn.execute("INSERT INTO downloads VALUES (?, ?)", (handle, f"pdfs/{stem}.pdf"))
        xml = f"<dc:subject>ddc:{ddc}</dc:subject>" if ddc else ""
        conn.execute("INSERT INTO records VALUES (?, 0, ?)", (handle, xml))
    conn.commit()
    conn.close()


def test_generator_end_to_end(tool, project, tmp_path):
    harvest = tmp_path / "harvester" / "data"
    pdfs = harvest / "example.org" / "pdfs"
    records = {}
    for index in range(24):
        stem = f"1_{index}"
        records[stem] = "330" if index < 12 else (None if index < 20 else "510")
        pdfs.mkdir(parents=True, exist_ok=True)
        pdf = pdfs / f"{stem}.pdf"
        pdf.write_bytes(b"%PDF-" + stem.encode())
        thesis = project.repo.add_thesis(pdf)
        metrics = {"thesis_type": "bachelor", "language_code": "de",
                   "publication_year": 2015, "word_count": 10000 + index,
                   "n_pages": 50, "file_size_bytes": 1_000_000}
        if index == 23:
            metrics["extraction_quality"] = "garbled"
        with project.repo.transaction():
            project.repo.record_run(thesis.id, "mod_x", "1.0.0", "ok", metrics=metrics)
    _harvest(harvest, "example.org", records)
    out = tmp_path / "aggregates.json"
    messages = []
    assert tool.main(["--project", str(project.dir), "--harvest-root", str(harvest),
                      "--source", "synthetic", "--status", "interim", "--out", str(out)],
                     log=messages.append) == 0

    document = json.loads(out.read_text(encoding="utf-8"))
    ref = reference.Reference(document)
    assert document["status"] == "interim" and document["source"] == "synthetic"
    assert document["analysed_with"] == ["mod_x 1.0.0"]
    keys = set(ref.rows)
    # 12 in field 300 -> own bucket; 3 usable in 500 (one garbled) -> dropped;
    # 8 without a field -> only in "all"
    assert ("bachelor", "de", "300", 2015) in keys
    assert ("bachelor", "de", "500", 2015) not in keys
    assert ("bachelor", "de", "all", 2015) in keys and ("all", "all", "all", 2015) in keys
    pooled = ref.stats("bachelor", "de", "all", 2015, "word_count")
    assert pooled["median"] == reference.summarise([10000 + i for i in range(23)])[1]
    assert ref.stats("bachelor", "de", "all", 2015, "words_per_page") is not None
    assert "23 in the reference population" in messages[0]


def test_generator_accepts_the_database_file_and_never_writes_it(tool, project, tmp_path):
    db = project.dir / "tta.sqlite"
    before = db.read_bytes()
    out = tmp_path / "a.json"
    tool.main(["--project", str(db), "--source", "x", "--out", str(out)], log=lambda _m: None)
    assert json.loads(out.read_text(encoding="utf-8"))["rows"] == []
    assert db.read_bytes() == before
