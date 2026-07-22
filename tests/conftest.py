import hashlib
import json
from types import SimpleNamespace

import pytest

from tta.core import artefact_kinds, db
from tta.core.modules.base import RunContext
from tta.core.artefacts import ArtefactStore
from tta.core.db import migrator
from tta.core.db.repository import Repository
from tta.core.types import Thesis

SAMPLE_PAGES = ("Hello thesis world.", "Second page text.")

# ~45 words with plenty of EN function words; repeated onto two pages it
# clears mod_classify_language's 200-char and the quality check's
# 200-token applicability thresholds.
ENGLISH_PARAGRAPH = (
    "The analysis of student theses is an interesting task for the research team. "
    "Many of the documents are written with care, and they contain long sentences "
    "about the methods and the results of the work. The reader can follow the "
    "argument from the first page to the conclusion."
)


@pytest.fixture
def sample_pages():
    return SAMPLE_PAGES


@pytest.fixture
def sample_pdf(tmp_path):
    """A tiny two-page PDF, generated on the fly (no binary fixture in the repo)."""
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "sample_thesis.pdf"
    doc = fitz.open()
    for content in SAMPLE_PAGES:
        page = doc.new_page()
        page.insert_text((72, 72), content)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def english_pdf(tmp_path):
    """Two pages of plain English prose - enough text for the full pipeline."""
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "english_thesis.pdf"
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        rect = page.rect + (72, 72, -72, -72)
        page.insert_textbox(rect, " ".join([ENGLISH_PARAGRAPH] * 4), fontsize=10)
    doc.set_metadata(
        {
            "producer": "pdfTeX-1.40.25",
            "creator": "LaTeX with hyperref",
            "creationDate": "D:20230412120000Z",
            "modDate": "D:20240115093000Z",
        }
    )
    doc.save(path)
    doc.close()
    return path


def make_thesis(pdf_path, thesis_id=1, **overrides) -> Thesis:
    fields = dict(
        id=thesis_id,
        pdf_sha256=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        pdf_path=str(pdf_path),
        pdf_filename=pdf_path.name,
    )
    fields.update(overrides)
    return Thesis(**fields)


@pytest.fixture
def sample_thesis(sample_pdf):
    return make_thesis(sample_pdf)


@pytest.fixture
def english_thesis(english_pdf):
    return make_thesis(english_pdf)


@pytest.fixture
def build_ctx(tmp_path):
    """Factory for module RunContexts with inline artefact content."""

    def _build(thesis=None, raw_text=None, language=None, tokens=None, pdf_metadata=None):
        workdir = tmp_path / "module_workdir"
        workdir.mkdir(exist_ok=True)
        artefacts = {}
        if raw_text is not None:
            path = tmp_path / "raw_text.txt"
            path.write_text(raw_text, encoding="utf-8")
            artefacts[artefact_kinds.RAW_TEXT] = path
        if language is not None:
            path = tmp_path / "language.json"
            path.write_text(json.dumps(language), encoding="utf-8")
            artefacts[artefact_kinds.LANGUAGE] = path
        if tokens is not None:
            path = tmp_path / "tokens.json"
            path.write_text(json.dumps(tokens), encoding="utf-8")
            artefacts[artefact_kinds.TOKENS] = path
        if pdf_metadata is not None:
            path = tmp_path / "pdf_metadata.json"
            path.write_text(json.dumps(pdf_metadata), encoding="utf-8")
            artefacts[artefact_kinds.PDF_METADATA] = path
        if thesis is None:
            thesis = Thesis(
                id=1,
                pdf_sha256="0" * 64,
                pdf_path="/tmp/x.pdf",
                pdf_filename="x.pdf",
            )
        return RunContext(thesis=thesis, artefacts=artefacts, workdir=workdir)

    return _build


@pytest.fixture
def project(tmp_path):
    """A migrated project directory with repository and artefact store."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    db_path = project_dir / "tta.sqlite"
    migrator.migrate(db_path)
    conn = db.connect(db_path)
    repo = Repository(conn)
    repo.ensure_local_source()
    yield SimpleNamespace(
        dir=project_dir,
        db_path=db_path,
        conn=conn,
        repo=repo,
        store=ArtefactStore(project_dir),
    )
    conn.close()
