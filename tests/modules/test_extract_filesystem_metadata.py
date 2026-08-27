"""Unit tests for mod_extract_filesystem_metadata (SDD Sec. 7.4, #18)."""

import os
import time
from datetime import datetime, timezone

import pytest

from tta.core.modules.extract_filesystem_metadata import ExtractFilesystemMetadata
from tta.core.types import Thesis
from tests.conftest import make_thesis


def run(build_ctx, pdf_path):
    return ExtractFilesystemMetadata().run(build_ctx(thesis=make_thesis(pdf_path)))


def test_reports_size_and_modified_year(build_ctx, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.7\n" + b"x" * 500)
    # a fixed mtime so the assertion does not depend on "now"
    stamp = datetime(2019, 6, 15, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(pdf, (stamp, stamp))

    result = run(build_ctx, pdf)
    assert result.metrics["file_size_bytes"] == 509
    assert result.metrics["fs_modified_year"] == 2019


def test_size_is_observed_at_run_time_not_add_time(build_ctx, tmp_path):
    """#18: the metric is a second, independent observation of the add-time
    theses.pdf_size_bytes column, so a swapped file becomes visible."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    thesis = make_thesis(pdf)
    pdf.write_bytes(b"%PDF-1.7\n" + b"y" * 1000)  # swapped after add

    result = ExtractFilesystemMetadata().run(build_ctx(thesis=thesis))
    assert result.metrics["file_size_bytes"] == 1009


def test_year_is_utc_not_local(build_ctx, tmp_path, monkeypatch):
    """QA-REPRO: the same project opened in another timezone must not read a
    different year off the same file."""
    if not hasattr(time, "tzset"):  # tzset is POSIX-only
        pytest.skip("time.tzset unavailable on this platform")
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    stamp = datetime(2020, 1, 1, 0, 30, tzinfo=timezone.utc).timestamp()
    os.utime(pdf, (stamp, stamp))

    monkeypatch.setenv("TZ", "Pacific/Niue")  # UTC-11
    time.tzset()
    try:
        # sanity: a naive/local reading of this very timestamp WOULD say 2019,
        # so the assertion below genuinely pins the UTC interpretation
        assert datetime.fromtimestamp(stamp).year == 2019
        assert run(build_ctx, pdf).metrics["fs_modified_year"] == 2020
    finally:
        monkeypatch.undo()
        time.tzset()


def test_atime_and_ctime_stay_in_local_diagnostics_only(build_ctx, tmp_path):
    """#18: atime is clobbered by the analysis run itself and ctime means
    different things on Windows and POSIX, so neither becomes a metric -
    but both stay inspectable in the local-only diagnostics."""
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    result = run(build_ctx, pdf)

    assert set(result.metrics) == {"file_size_bytes", "fs_modified_year"}
    assert "st_atime" in result.diagnostics and "st_ctime" in result.diagnostics
    assert result.diagnostics["st_mtime"] == os.stat(pdf).st_mtime
    assert "caveat" in result.diagnostics


def test_missing_file_is_not_applicable(tmp_path):
    gone = tmp_path / "gone.pdf"
    thesis = Thesis(
        id=1, pdf_sha256=None, pdf_path=str(gone), pdf_filename=gone.name
    )
    applicability = ExtractFilesystemMetadata().applicable(thesis)
    assert applicability.ok is False
    assert applicability.reason == "file not found"


def test_non_pdf_files_are_still_applicable(tmp_path):
    """Unlike the PDF-reading root modules this needs no format at all."""
    other = tmp_path / "thesis.txt"
    other.write_text("x", encoding="utf-8")
    assert ExtractFilesystemMetadata().applicable(make_thesis(other)).ok is True


def test_registered_in_the_default_catalogue():
    from tta.core.modules.registry import default_registry

    assert "mod_extract_filesystem_metadata" in default_registry().names()
