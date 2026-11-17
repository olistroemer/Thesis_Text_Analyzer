"""Smoke test for the documentation-screenshot tool (tools/screenshots.py,
SDD Sec. 5.6.5): its demo data still produces what the images need, and the
Win32 window capture still writes a PNG. The full tool run (a real analysis
plus a browser) is not repeated here."""

import importlib.util
import sys
import threading
import tkinter
import zlib
from pathlib import Path

import pytest

from tta.core import events
from tta.core.modules.check_extraction_quality import STOP_WORDS, WORD_RE
from tests.ui.conftest import display_available

TOOL = Path(__file__).resolve().parents[2] / "tools" / "screenshots.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("tta_screenshots_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _stop_word_ratio(text: str) -> float:
    tokens = WORD_RE.findall(text.lower())[:5000]
    return sum(token in STOP_WORDS for token in tokens) / len(tokens)


def test_demo_texts_drive_the_states_the_images_show(tool):
    """The [!] row needs exactly one thesis judged garbled; the French one (the
    na readability cell) must not be, or it would be a second [!] row."""
    by_lang = {}
    for spec in tool.DEMO_THESES:
        if spec.lang != "corrupt":
            by_lang.setdefault(spec.lang, []).append(" ".join(tool.demo_text(spec)))
    assert set(by_lang) == {"de", "en", "fr", "garbled"}
    assert len(by_lang["garbled"]) == 1
    assert _stop_word_ratio(by_lang["garbled"][0]) < 0.10
    for lang in ("de", "en", "fr"):
        for text in by_lang[lang]:
            assert _stop_word_ratio(text) >= 0.149, lang
    # deterministic: the same thesis always gets the same text
    first = tool.DEMO_THESES[0]
    assert tool.demo_text(first) == tool.demo_text(first)


def test_demo_project_setup(tool, tmp_path):
    project = tool.build_demo_project(tmp_path, tmp_path / tool.PROJECT_NAME)
    try:
        theses = project.repo.list_theses(local_only=True, include_excluded=True)
        assert sorted(t.pdf_filename for t in theses) == sorted(
            s.filename for s in tool.DEMO_THESES
        )
        assert [t.pdf_filename for t in theses if t.excluded] == [
            s.filename for s in tool.DEMO_THESES if s.excluded
        ]
        assert project.config.ui_locale == "de"
        assert project.config.open_report_after_run == "never"
        assert project.config.workers == tool.WORKERS
    finally:
        project.close()
    # everything it wrote is inside the given directory
    assert (tmp_path / "beispiele").is_dir()
    assert (tmp_path / tool.PROJECT_NAME / "tta.toml").is_file()


def test_prepare_workdir_refuses_a_foreign_directory(tool, tmp_path):
    foreign = tmp_path / "not-ours"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        tool.prepare_workdir(foreign)
    assert (foreign / "keep.txt").is_file()
    ours = tmp_path / "ours"
    tool.prepare_workdir(ours)
    (ours / "leftover").write_text("x", encoding="utf-8")
    tool.prepare_workdir(ours)  # its own marker: recreated, leftovers gone
    assert not (ours / "leftover").exists()


def test_png_writer(tool, tmp_path):
    # 2x1 BGRA: pure red, pure blue
    path = tmp_path / "x.png"
    tool.write_png(path, 2, 1, bytes([0, 0, 255, 255, 255, 0, 0, 255]))
    assert tool.png_size(path) == (2, 1)
    data = path.read_bytes()
    start = data.index(b"IDAT") + 4
    length = int.from_bytes(data[start - 8:start - 4], "big")
    raw = zlib.decompress(data[start:start + length])
    assert raw == bytes([0, 255, 0, 0, 0, 0, 255])  # filter byte, then RGB RGB


def test_gated_queue_holds_the_run_thread(tool):
    gate = tool.GatedQueue(pause_after=2)
    finished = threading.Event()

    def run():
        for thesis_id in (1, 2, 3):
            gate.put(events.ThesisCompleted(thesis_id, {}))
        finished.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert gate.paused.wait(5)
    assert not finished.wait(0.2)  # held after the 2nd thesis
    gate.release()
    assert finished.wait(5)
    assert gate.qsize() == 3


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 PrintWindow capture")
@pytest.mark.skipif(not display_available(), reason="no display")
def test_capture_tk_window(tool, tmp_path):
    root = tkinter.Tk()
    try:
        root.geometry("320x200+40+40")
        tkinter.Label(root, text="tta").pack()
        tool.pump(root, 0.3)
        path = tmp_path / "window.png"
        width, height = tool.capture_tk(tool.Win32(), root, path)
        assert tool.png_size(path) == (width, height)
        # the client area plus a frame of a few pixels and a title bar
        assert 320 <= width < 360 and 200 < height < 280
    finally:
        root.destroy()
