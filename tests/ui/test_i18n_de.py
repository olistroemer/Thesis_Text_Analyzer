r"""The GUI under the German catalog (#28, SDD Sec. 9.6).

ADR-0018 case 2: this file asserts on German *string content*, so the handful
of umlauts it needs are written as ``\uXXXX`` escapes. The file bytes stay
pure ASCII; the runtime values are byte-for-byte the German the catalog
holds, and the assertions passing is the proof the escapes are right. Where an
assertion can key on an ASCII-only slice of the German instead, it does.

Needs a display; skipped headless, and run for real under Xvfb in CI (the same
display-gated pattern as tests/ui/test_smoke.py).

The point is deliberately NOT "the catalog contains the right strings" -
tests/core/test_i18n_catalogs.py does that, and it would pass even if the
window never resolved a single one. What is checked here is that the *real*
window, built through the real code paths, comes out in German: the menu, the
toolbar, the grid headers, the details panel, the report. Plus the layout
question Sec. 9.6 raises - German runs about 30 % longer than English, so
every widget has to have grown rather than clipped.
"""

import tkinter

import pytest

from tta.core import i18n
from tta.core.project import Project
from tta.ui.tk.columns import LEAD_COLUMNS, column_label
from tests.ui.conftest import display_available

FILE_COL = LEAD_COLUMNS.index("file")


pytestmark = pytest.mark.skipif(not display_available(), reason="no display")


@pytest.fixture
def german():
    """Install `de` for one test. The autouse fixture in tests/conftest.py puts
    English back afterwards, but this makes the switch explicit and local."""
    i18n.install("de")
    yield
    i18n.install("en")


@pytest.fixture
def seeded_project(tmp_path, english_pdf):
    with Project.open(tmp_path / "proj", create=True) as project:
        thesis = project.repo.add_thesis(english_pdf)
        with project.repo.transaction():
            project.repo.record_run(
                thesis.id, "mod_surface_counts", "0.1.0", "ok",
                metrics={"word_count": 9000, "avg_word_len": 4.75},
            )
            project.repo.record_run(
                thesis.id, "mod_readability", "0.1.0", "na", reason="not a PDF"
            )
            project.repo.record_run(
                thesis.id, "mod_classify_language", "0.1.0", "ok",
                metrics={"language_code": "en"},
            )
        yield project


@pytest.mark.slow
def test_the_main_window_builds_and_renders_in_german(german, seeded_project):
    from tta.ui.tk.main_window import MainWindow

    window = MainWindow(seeded_project, first_launch=True)
    try:
        window.root.update_idletasks()
        window.root.update()

        # toolbar: keyed by English identity, labelled in German
        assert set(window._toolbar_buttons) >= {"Add files", "Run all", "Report"}
        assert str(window._toolbar_buttons["Run all"]["text"]) == "Alle analysieren"
        assert (
            str(window._toolbar_buttons["Add files"]["text"])
            == "Dateien hinzuf\u00fcgen"
        )

        # window title and status line
        assert window.root.title().startswith("Thesis Text Analyzer - ")
        assert "Bereit" in str(window.status["text"])
        assert "Arbeiten" in str(window.status["text"])

        # grid headers are the German labels, not raw metric names (#16 + #28)
        headers = [str(h) for h in window.grid_view.sheet.headers()]
        assert "W\u00f6rter" in headers
        assert "Lesbarkeit (Flesch)" in headers
        assert "word_count" not in headers
        assert "flesch_reading_ease" not in headers

        # the first-launch banner is German prose with the path interpolated
        banner = _all_label_text(window.root)
        assert "Ihr Projekt liegt unter" in banner
        assert str(seeded_project.dir) in banner
    finally:
        window.root.destroy()


@pytest.mark.slow
def test_the_details_panel_is_german_and_still_names_the_raw_metric(
    german, seeded_project
):
    """#16's "raw name stays discoverable" has to hold in German too - the
    German label is what the professor reads, the raw name is what `tta list`
    and the help pages key on."""
    from tta.ui.tk.grid import GridView
    from tta.ui.tk.columns import MetricColumn

    root = tkinter.Tk()
    try:
        grid = GridView(root, seeded_project.repo, seeded_project.store)
        grid.reload(
            [MetricColumn("flesch_reading_ease", "mod_readability")],
            show_artefacts=False,
        )
        root.update_idletasks()
        column = grid._column_names().index("flesch_reading_ease")
        grid.sheet.select_cell(0, column)
        grid._on_double_click(None)
        panels = [w for w in grid.winfo_children() if isinstance(w, tkinter.Toplevel)]
        assert len(panels) == 1
        text = panels[0].winfo_children()[0].get("1.0", "end")

        assert "Lesbarkeit (Flesch)" in text          # the German label
        assert "Spaltenname: flesch_reading_ease" in text  # the raw name
        assert "Lesbarkeitsindex" in text             # the German column help
        # the module's `na` reason: English in the DB, German on screen
        assert "keine PDF-Datei" in text
        assert panels[0].title() == "Zelldetails"
        panels[0].destroy()
    finally:
        root.destroy()


@pytest.mark.slow
def test_german_labels_do_not_clip_the_layout(german, seeded_project):
    """SDD Sec. 9.6's flexible-layout requirement, actually exercised.

    German runs ~30 % longer, and the failure mode is a button whose text is
    cut off. Asserted as "every widget is at least as wide as its own
    requested width", which is what pack()/grid() guarantee and a hard-coded
    `width=` would break.
    """
    from tta.ui.tk.main_window import MainWindow

    window = MainWindow(seeded_project, first_launch=True)
    try:
        window.root.update_idletasks()
        window.root.update()
        clipped = []
        for key, button in window._toolbar_buttons.items():
            requested = button.winfo_reqwidth()
            actual = button.winfo_width()
            # winfo_width is 1 until the widget is mapped; only compare mapped
            if actual > 1 and actual < requested:
                clipped.append((key, requested, actual))
        assert clipped == [], clipped

        # the German toolbar must genuinely be wider than the English one -
        # otherwise this test would pass on an untranslated UI
        german_width = sum(b.winfo_reqwidth() for b in window._toolbar_buttons.values())
        i18n.install("en")
        window._render_toolbar()
        window.root.update_idletasks()
        english_width = sum(b.winfo_reqwidth() for b in window._toolbar_buttons.values())
        assert german_width > english_width, (german_width, english_width)
    finally:
        i18n.install("de")
        window.root.destroy()


@pytest.mark.slow
def test_the_report_renders_in_german_and_declares_the_locale(german, seeded_project):
    """The HTML report is rendered in core, so this is also the check that
    core's own user-facing output follows the locale (ADR-0020 5)."""
    from tta.ui.tk.main_window import MainWindow

    window = MainWindow(seeded_project, first_launch=False)
    try:
        path = window._write_report()
        assert path is not None
        document = path.read_text(encoding="utf-8")
        assert '<html lang="de">' in document
        assert "Bericht zu den Abschlussarbeiten" in document
        assert "Analysierte Arbeiten" in document
        assert "Dieser Bericht kann personenbezogene Daten enthalten." in document
        assert "Thesis report" not in document
    finally:
        window.root.destroy()


def _all_label_text(widget) -> str:
    """Every ``text`` option in the widget tree, joined - enough to assert that
    a piece of copy reached the screen without knowing its exact widget."""
    found = []
    for child in widget.winfo_children():
        try:
            if "text" in child.keys():
                found.append(str(child["text"]))
        except tkinter.TclError:  # pragma: no cover - defensive
            pass
        found.append(_all_label_text(child))
    return " | ".join(found)
