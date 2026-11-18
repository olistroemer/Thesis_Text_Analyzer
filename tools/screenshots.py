#!/usr/bin/env python
"""Regenerate the documentation screenshots of tta (SDD Sec. 5.6.5).

Usage (repository root, conda env ``pds``)::

    python tools/screenshots.py --out <dir>                 # all images
    python tools/screenshots.py --out <dir> --only app-cli  # a subset
    python tools/screenshots.py --out <dir> --readme        # the README set
    python tools/screenshots.py --list                      # image names

What it does: writes synthetic thesis PDFs (invented titles, placeholder
authors), builds a fresh German-locale project from them in a scratch
directory, drives the real Tk ``MainWindow`` through a run and its dialogs,
and captures each window to ``<out>/<name>.png``. The HTML report and a CLI
transcript are rasterised by a headless browser. Nothing outside the scratch
directory and ``--out`` is written; the user's default project and its
last-project pointer are never opened (the project is opened with
``Project.open``, not ``open_startup_project``).

Needs: the dev environment (PyMuPDF for the demo PDFs, rich for the CLI
transcript - both already there) and, for ``app-bericht`` and ``app-cli``, a
Chromium-family browser (Edge is found on Windows; else pass ``--browser``).
It runs on a profile in the scratch directory, never the user's own.
Windows only for the Tk captures (Win32 ``PrintWindow``); the windows appear
on screen for a few seconds while they are captured. Takes under a minute.

The ``--workdir`` (default: ``<temp>/tta-screenshots``) is deleted and
recreated on every run; the tool refuses to delete a directory it did not
create itself.
"""

from __future__ import annotations

import argparse
import io
import os
import queue
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Output names, fixed by projektdoku/README.md ("Screenshots und Abbildungen"),
#: in the order they are produced.
IMAGES = (
    "app-analyselauf",
    "app-hauptfenster-basis",
    "app-detailpanel",
    "app-hilfe",
    "app-datenschutz",
    "app-export",
    "app-hauptfenster-erweitert",
    "app-bericht",
    "app-cli",
)
GUI_IMAGES = IMAGES[:7]
#: The subset shown in the repository README (--readme): the grid after a
#: run, the report, the help viewer and the CLI - what the tool does, what it
#: produces, how it explains itself, and the researcher's way in.
README_IMAGES = ("app-hauptfenster-basis", "app-bericht", "app-hilfe", "app-cli")

PROJECT_NAME = "Beispielprojekt"
INSTITUTION = "FH-Musterstadt"
MARKER = ".tta-screenshots-workdir"  # proves a --workdir is ours to delete
MAIN_GEOMETRY = (1400, 580)
WORKERS = 2
# The details-panel image: an error cell (basic mode, so no traceback).
# An ok cell opens no panel at all (SDD Sec. 9.9).
DETAIL_THESIS, DETAIL_METRIC = "ma14-defekt.pdf", "n_pages"
PAUSE_AFTER_THESES = 6  # the in-progress image: this many theses finished
# Fixed "generated at" of the report: Claude Shannon's birthday, at 2^10
# minutes past midnight (10:24). One constant - change it here.
REPORT_TIMESTAMP = datetime(1916, 4, 30, 10, 24)
REPORT_WINDOW = (1280, 2300)  # the top of the report: note, cards, filters, two panels
#: The report draws its charts with plotly.js after load (SDD Sec. 9.8): give
#: the headless browser virtual time to finish before the capture.
REPORT_SCRIPT_BUDGET_MS = 10000
CLI_WIDTH = 104
CLI_RUN_HEAD, CLI_RUN_TAIL = 7, 3  # `tta run` lines kept around the elision


# ---------------------------------------------------------------------------
# Demo data: invented theses, deterministic text (seeded per thesis)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoThesis:
    filename: str
    lang: str  # de | en | fr | garbled | corrupt
    kind: str  # title-page wording, "" = none
    year: int
    title: str
    author: str  # placeholder names only - never a real person
    words: int
    clause_max: int = 2  # max subordinate clauses per sentence (sentence length)
    vocab: int = 60  # nouns drawn from (vocabulary richness, Yule's K)
    jargon: bool = False  # long compounds and very uneven sentences
    producer: str = "LaTeX with hyperref"
    excluded: bool = False


DEMO_THESES = (
    DemoThesis("ba12-lager.pdf", "de", "Bachelorarbeit", 2012,
               "Optimierung der Lagerplanung in einem mittelstaendischen Betrieb",
               "Max Mustermann", 2400, producer="Microsoft Word"),
    DemoThesis("dipl08-netz.pdf", "de", "Diplomarbeit", 2008,
               "Planung eines Campusnetzes mit redundanten Verbindungen",
               "Erika Musterfrau", 5200, clause_max=3),
    DemoThesis("ba15-web.pdf", "de", "Bachelorarbeit", 2015,
               "Barrierefreiheit von Webanwendungen in der Verwaltung",
               "Lena Beispiel", 2900, vocab=40, producer="Microsoft Word"),
    DemoThesis("ma16-sensor.pdf", "en", "Master Thesis", 2016,
               "Sensor Data Fusion for Indoor Positioning",
               "John Doe", 4300, clause_max=3),
    DemoThesis("fr17-projet.pdf", "fr", "", 2017,
               "La gestion de projet dans les petites entreprises",
               "Jeanne Exemple", 2600, clause_max=3),
    DemoThesis("ba18-energy.pdf", "en", "Bachelor Thesis", 2018,
               "Energy Monitoring for Small Office Buildings",
               "Jane Roe", 2700, producer="Microsoft Word"),
    DemoThesis("ma19-prozess.pdf", "de", "Masterarbeit", 2019,
               "Prozessmodellierung im Gesundheitswesen",
               "Tom Platzhalter", 4800, clause_max=3),
    DemoThesis("ba19-scan.pdf", "garbled", "Bachelorarbeit", 2019,
               "Digitalisierung eines Archivbestands",
               "Paula Probe", 2600),
    DemoThesis("ba20-app.pdf", "en", "Bachelor Thesis", 2020,
               "Usability Testing of a Mobile Library App",
               "Alex Sample", 3100, vocab=45),
    DemoThesis("ma21-graphen.pdf", "de", "Masterarbeit", 2021,
               "Wissensgraphen fuer die Anforderungsverwaltung",
               "Mia Muster", 5600, jargon=True, vocab=25),
    DemoThesis("ba22-cloud.pdf", "de", "Bachelorarbeit", 2022,
               "Kostenanalyse von Cloud-Diensten fuer Hochschulen",
               "Ben Beispielmann", 3300, producer="Microsoft Word"),
    DemoThesis("ma23-forecast.pdf", "en", "Master Thesis", 2023,
               "Explainable Forecasting of Energy Demand",
               "Sam Placeholder", 5100, clause_max=3, vocab=80),
    DemoThesis("ba23-entwurf.pdf", "de", "Bachelorarbeit", 2023,
               "Zurueckgezogene Arbeit (ausgeschlossen)",
               "Nora Nobody", 2500, excluded=True),
    DemoThesis("ba24-chatbot.pdf", "de", "Bachelorarbeit", 2024,
               "Bewertung eines Chatbots fuer die Studienberatung",
               "Kim Exempel", 3500, vocab=70),
    DemoThesis("ma25-retrieval.pdf", "en", "Master Thesis", 2025,
               "Retrieval Pipelines for Technical Documentation",
               "Robin Roe", 5400, clause_max=3, vocab=90),
    DemoThesis("ma14-defekt.pdf", "corrupt", "", 2014, "", "", 0),
)

#: A short CLI demo: the first theses of the list, in a project of their own.
CLI_THESES = 3

# Sentence material. German without umlauts where it reads naturally, the
# rest escaped (ADR-0018: ASCII source).
WORDS = {
    "de": {
        "det": ("Die", "Diese", "Eine"),
        "nouns": (
            "Analyse", "Methode", "Untersuchung", "Auswertung", "Studie", "Messung",
            "Anforderung", "Planung", "Struktur", "Umgebung", "Schnittstelle",
            "Datenbasis", "Bewertung", "Umsetzung", "Erweiterung", "Simulation",
            "Befragung", "Kennzahl", "Architektur", "Strategie", "Nutzung",
            "Steuerung", "Verwaltung", "Dokumentation", "Optimierung", "Erhebung",
            "Beobachtung", "Entwicklung", "Software", "Infrastruktur", "Abfrage",
            "Visualisierung", "Prognose", "Verteilung", "Sicherheit", "Leistung",
            "Kommunikation", "Organisation", "Lieferkette", "Produktion",
            "Kalkulation", "Schulung", "Wartung", "Validierung", "Integration",
            "Migration", "Konfiguration", "Automatisierung", "Priorisierung",
            "Modellierung", "Klassifikation", "Annahme", "Hypothese", "Grenze",
            "Abweichung", "Stichprobe", "Tabelle", "Abbildung", "Literatur",
            "Fragestellung", "Zielsetzung", "Gliederung", "Einleitung",
            "Zusammenfassung", "Diskussion", "Fallstudie", "Pilotphase",
            "Referenz", "Plattform", "Oberfl\u00e4che", "Pr\u00fcfung", "Qualit\u00e4t",
            "Effizienz", "Genauigkeit", "Stabilit\u00e4t", "Kosten", "Zeitplanung",
            "Abteilung", "Einrichtung", "Hochschule", "Verwaltungseinheit",
        ),
        "verbs": (
            "zeigt", "beschreibt", "untersucht", "verbessert", "erweitert",
            "bewertet", "erkl\u00e4rt", "begr\u00fcndet", "unterst\u00fctzt",
            "beeinflusst", "ber\u00fccksichtigt", "vereinfacht",
        ),
        "adjuncts": (
            "in der Praxis", "im Rahmen dieser Arbeit", "mit einem einfachen Verfahren",
            "f\u00fcr die weitere Arbeit", "auf der Grundlage der Literatur",
            "in diesem Kapitel", "an einem konkreten Beispiel", "\u00fcber mehrere Wochen",
            "mit den vorhandenen Mitteln", "nach einer ersten Pilotphase",
        ),
        "clauses": (
            "weil die {n} der {n2} nicht ausreicht", "da die {n} sich ver\u00e4ndert hat",
            "wobei die {n} eine wichtige Rolle spielt", "sodass die {n} besser wird",
            "obwohl die {n} noch offen ist", "und die {n} wird dabei genauer",
        ),
        "obj": "die {n} der {n2}",
        "prefixes": (
            "Anforderungs", "Wissens", "Graph", "Daten", "Modell", "Prozess",
            "Ontologie", "Verwaltungs", "Abh\u00e4ngigkeits", "Versions",
        ),
    },
    "en": {
        "det": ("The", "This", "Each"),
        "nouns": (
            "analysis", "method", "study", "measurement", "result", "sensor",
            "system", "network", "model", "dataset", "interface", "evaluation",
            "design", "prototype", "survey", "requirement", "architecture",
            "framework", "algorithm", "experiment", "baseline", "metric",
            "forecast", "estimate", "user", "participant", "session", "task",
            "process", "pipeline", "component", "service", "database", "query",
            "document", "index", "budget", "building", "device", "signal",
            "accuracy", "error", "deviation", "sample", "table", "figure",
            "chapter", "literature", "question", "objective", "outline",
            "discussion", "limitation", "approach", "strategy", "tool",
            "library", "platform", "workflow", "schedule", "cost", "load",
            "demand", "pattern", "feature", "label", "score", "threshold",
            "parameter", "configuration", "deployment", "maintenance",
            "validation", "integration", "migration", "visualisation",
            "documentation", "benchmark", "scenario", "case", "context",
        ),
        "verbs": (
            "shows", "describes", "examines", "improves", "extends", "evaluates",
            "explains", "supports", "affects", "considers", "simplifies",
            "reduces",
        ),
        "adjuncts": (
            "in practice", "in this thesis", "with a simple procedure",
            "for the remaining work", "on the basis of the literature",
            "in this chapter", "with a concrete example", "over several weeks",
            "with the available resources", "after a first pilot phase",
        ),
        "clauses": (
            "because the {n} of the {n2} is not sufficient",
            "since the {n} has changed", "while the {n} plays an important role",
            "so that the {n} becomes more reliable", "although the {n} is still open",
            "and the {n} is measured with care",
        ),
        "obj": "the {n} of the {n2}",
        "prefixes": (),
    },
    "fr": {
        "det": ("La", "Cette", "Une"),
        "nouns": (
            "analyse", "m\u00e9thode", "\u00e9tude", "mesure", "gestion",
            "planification", "entreprise", "organisation", "\u00e9quipe",
            "communication", "strat\u00e9gie", "\u00e9valuation", "d\u00e9marche",
            "structure", "ressource", "contrainte", "solution", "pratique",
            "enqu\u00eate", "question", "hypoth\u00e8se", "partie", "conclusion",
            "litt\u00e9rature", "approche", "situation", "activit\u00e9",
            "direction", "formation", "relation", "production", "qualit\u00e9",
            "performance", "d\u00e9cision", "information", "transformation",
            "coordination", "\u00e9tape", "phase", "base",
        ),
        "verbs": (
            "montre", "d\u00e9crit", "examine", "am\u00e9liore", "\u00e9tend",
            "\u00e9value", "explique", "soutient", "influence", "simplifie",
        ),
        "adjuncts": (
            "dans la pratique", "dans ce travail", "avec une m\u00e9thode simple",
            "pour la suite du travail", "sur la base de la litt\u00e9rature",
            "dans ce chapitre", "avec un exemple concret", "pendant plusieurs semaines",
        ),
        # mod_check_extraction_quality counts EN/DE function words only, so
        # French without "on", "a" and "des" would be flagged as garbled; the
        # demo keeps that limitation out of the [!] row it means to show.
        "clauses": (
            "car on a observ\u00e9 la {n} des {n2}s", "et on a \u00e9tudi\u00e9 la {n}",
            "alors que la {n} des {n2}s a chang\u00e9", "puisque on a compar\u00e9 la {n}",
        ),
        "obj": "la {n} des {n2}s",
        "prefixes": (),
    },
}

TITLE_PAGE = {
    "de": ("vorgelegt von", "Fachhochschule Musterstadt", "Fachbereich Informatik",
           "Musterstadt, im M\u00e4rz {year}"),
    "en": ("submitted by", "University of Applied Sciences Musterstadt",
           "Department of Computer Science", "Musterstadt, March {year}"),
    "fr": ("pr\u00e9sent\u00e9 par", "Haute \u00e9cole de Musterstadt",
           "D\u00e9partement de gestion", "Musterstadt, mars {year}"),
}


def demo_text(spec: DemoThesis) -> list[str]:
    """Paragraphs of deterministic prose for one thesis (seeded by its name)."""
    lang = "de" if spec.lang == "garbled" else spec.lang
    w = WORDS[lang]
    rng = random.Random(spec.filename)
    nouns = list(w["nouns"])
    rng.shuffle(nouns)
    nouns = nouns[: max(8, min(spec.vocab, len(nouns)))]

    def noun() -> str:
        if spec.jargon and w["prefixes"] and rng.random() < 0.7:
            parts = rng.sample(w["prefixes"], 2)
            return parts[0] + parts[1].lower() + nouns[rng.randrange(len(nouns))].lower()
        return nouns[rng.randrange(len(nouns))]

    def sentence() -> str:
        words = [rng.choice(w["det"]), noun(), rng.choice(w["verbs"]),
                 w["obj"].format(n=noun(), n2=noun())]
        if spec.jargon and rng.random() < 0.5:
            return f"{words[0]} {words[1]} {words[2]}."  # very short ...
        clauses = rng.randint(0, spec.clause_max)
        if spec.jargon and rng.random() < 0.6:
            clauses = 9  # ... or very long: an uneven style
        parts = [" ".join(words)]
        if rng.random() < 0.6:
            parts[0] += " " + rng.choice(w["adjuncts"])
        for _ in range(clauses):
            parts.append(rng.choice(w["clauses"]).format(n=noun(), n2=noun()))
        return ", ".join(parts) + "."

    paragraphs, count = [], 0
    while count < spec.words:
        paragraph = " ".join(sentence() for _ in range(rng.randint(4, 7)))
        count += len(paragraph.split())
        paragraphs.append(paragraph)
    if spec.lang == "garbled":
        paragraphs = [garble(p) for p in paragraphs]
    return paragraphs


def garble(text: str) -> str:
    """Deterministic gibberish of the kind a broken /ToUnicode CMap extracts as:
    a fixed letter substitution, so the stop-word ratio collapses."""
    plain = "abcdefghijklmnopqrstuvwxyz"
    table = str.maketrans(plain + plain.upper(), "qxjzvkwpybfgmhdlcnrtsaueoi" * 2)
    return text.translate(table)


def write_demo_pdf(spec: DemoThesis, path: Path) -> None:
    """One synthetic thesis: a title page, then the body text."""
    import fitz  # PyMuPDF - dev extra; the demo data needs a real PDF writer

    if spec.lang == "corrupt":
        # Truncated garbage behind a PDF header: the extractor errors out.
        path.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + bytes(range(256)) * 8)
        return
    doc = fitz.open()
    page = doc.new_page()
    lang = "de" if spec.lang == "garbled" else spec.lang
    by, school, department, place = TITLE_PAGE[lang]
    lines = [school, department, "", "", spec.kind, "", spec.title, "", "",
             by, spec.author, "", "", place.format(year=spec.year)]
    page.insert_textbox(page.rect + (72, 140, -72, -72), "\n".join(lines),
                        fontsize=14, align=1)
    text = "\n\n".join(demo_text(spec))
    scratch = fitz.open()  # probe pages, so the real document stays clean
    while text:
        page = doc.new_page()
        rect = page.rect + (72, 72, -72, -72)
        # insert_textbox returns < 0 when the text overflows; find how many
        # words fit on the page (binary search over the word count).
        words = text.split(" ")
        lo, hi = 1, len(words)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            probe = scratch.new_page()
            fits = probe.insert_textbox(rect, " ".join(words[:mid]), fontsize=11) >= 0
            scratch.delete_page(0)
            if fits:
                lo = mid
            else:
                hi = mid - 1
        page.insert_textbox(rect, " ".join(words[:lo]), fontsize=11)
        text = " ".join(words[lo:])
    stamp = f"D:{spec.year}0315120000"
    doc.set_metadata({"title": spec.title, "producer": spec.producer,
                      "creator": spec.producer, "creationDate": stamp, "modDate": stamp})
    doc.save(path, deflate=True)
    doc.close()
    scratch.close()


def prepare_workdir(workdir: Path) -> None:
    if workdir.exists():
        if not (workdir / MARKER).is_file():
            sys.exit(f"refusing to delete {workdir}: not created by this tool "
                     f"(no {MARKER}); choose another --workdir")
        if not clean_workdir(workdir):
            sys.exit(f"could not empty {workdir} (a file is still in use?)")
    workdir.mkdir(parents=True)
    (workdir / MARKER).write_text("scratch directory of tools/screenshots.py\n",
                                  encoding="utf-8")


def clean_workdir(workdir: Path) -> bool:
    """Delete the scratch directory, the marker last: if a file is still
    locked (an aborted run's database, say), the leftover keeps its marker and
    the next run may still delete it. Returns whether it is gone."""
    for child in workdir.iterdir():
        if child.name == MARKER:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink(missing_ok=True)
            except OSError:
                pass  # still in use; reported by the check below
    if any(child.name != MARKER for child in workdir.iterdir()):
        return False
    shutil.rmtree(workdir, ignore_errors=True)
    return not workdir.exists()


def write_demo_pdfs(folder: Path, theses=DEMO_THESES) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for spec in theses:
        path = folder / spec.filename
        write_demo_pdf(spec, path)
        paths.append(path)
    return paths


def write_project_config(project_dir: Path) -> None:
    """German UI, fixed worker count, no post-run prompt (SDD Sec. 5.6.5)."""
    from tta.core.config import load_config, save_config

    project_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(project_dir)
    config.ui_locale = "de"
    config.ui_mode = "basic"
    config.workers = WORKERS
    config.institution = INSTITUTION
    config.open_report_after_run = "never"
    save_config(project_dir, config)


def build_demo_project(workdir: Path, project_dir: Path):
    """PDFs under ``<workdir>/beispiele``, a fresh project at ``project_dir``
    holding them (not yet analysed), the ``excluded`` ones excluded."""
    from tta.core.project import Project

    pdfs = write_demo_pdfs(workdir / "beispiele")
    write_project_config(project_dir)
    project = Project.open(project_dir, create=True)
    # Relative to the working directory where possible (main() runs inside
    # the scratch directory): error texts quote the PDF path, and it should
    # read "beispiele/x.pdf", not a scratch path with the account name.
    here = Path.cwd()
    project.repo.add_theses(
        [pdf.relative_to(here) if pdf.is_relative_to(here) else pdf for pdf in pdfs]
    )
    excluded = {spec.filename for spec in DEMO_THESES if spec.excluded}
    for thesis in project.repo.list_theses(local_only=True, include_excluded=True):
        if thesis.pdf_filename in excluded:
            project.repo.set_excluded(thesis.id, True)
    return project


# ---------------------------------------------------------------------------
# PNG writing (stdlib only - Pillow stays out of the environment, ADR-0014)
# ---------------------------------------------------------------------------


def write_png(path: Path, width: int, height: int, bgra: bytes) -> None:
    """Write top-down 32-bit BGRA pixels as an 8-bit RGB PNG."""
    rgb = bytearray(width * height * 3)
    rgb[0::3] = bgra[2::4]
    rgb[1::3] = bgra[1::4]
    rgb[2::3] = bgra[0::4]
    stride = width * 3
    raw = b"".join(b"\x00" + bytes(rgb[y * stride:(y + 1) * stride]) for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    write_file(path, b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
               + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def write_file(path: Path, data: bytes, attempts: int = 10) -> None:
    """Replace ``path`` atomically. An image viewer or a sync client holding
    the previous file open makes the replace fail for a moment on Windows,
    so it is retried briefly rather than aborting the whole run."""
    path = Path(path)
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(data)
    for attempt in range(attempts):
        try:
            os.replace(temporary, path)
            return
        except OSError:
            if attempt == attempts - 1:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.5)


def png_size(path: Path) -> tuple[int, int]:
    data = Path(path).read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    return struct.unpack(">II", data[16:24])


# ---------------------------------------------------------------------------
# Win32 window capture (ctypes)
# ---------------------------------------------------------------------------


class Win32:
    """The handful of user32/gdi32/dwmapi calls the capture needs, typed for
    64-bit handles."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wt = ctypes, wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self.dwmapi = ctypes.WinDLL("dwmapi")
        H, B, I, U = wintypes.HANDLE, wintypes.BOOL, ctypes.c_int, wintypes.UINT
        HW = wintypes.HWND
        sig = {
            (self.user32, "GetWindowRect"): ([HW, ctypes.POINTER(wintypes.RECT)], B),
            (self.user32, "GetWindowDC"): ([HW], H),
            (self.user32, "ReleaseDC"): ([HW, H], I),
            (self.user32, "PrintWindow"): ([HW, H, U], B),
            (self.user32, "IsWindowVisible"): ([HW], B),
            (self.user32, "GetClassNameW"): ([HW, wintypes.LPWSTR, I], I),
            (self.user32, "GetWindowTextW"): ([HW, wintypes.LPWSTR, I], I),
            (self.user32, "GetWindowThreadProcessId"):
                ([HW, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            (self.user32, "PostMessageW"):
                ([HW, U, wintypes.WPARAM, wintypes.LPARAM], B),
            (self.gdi32, "CreateCompatibleDC"): ([H], H),
            (self.gdi32, "CreateCompatibleBitmap"): ([H, I, I], H),
            (self.gdi32, "SelectObject"): ([H, H], H),
            (self.gdi32, "GetDIBits"):
                ([H, H, U, U, ctypes.c_void_p, ctypes.c_void_p, U], I),
            (self.gdi32, "DeleteObject"): ([H], B),
            (self.gdi32, "DeleteDC"): ([H], B),
            (self.dwmapi, "DwmGetWindowAttribute"):
                ([HW, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD], ctypes.c_long),
            (self.dwmapi, "DwmSetWindowAttribute"):
                ([HW, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD], ctypes.c_long),
        }
        for (dll, name), (args, res) in sig.items():
            fn = getattr(dll, name)
            fn.argtypes, fn.restype = args, res

    def square_corners(self, hwnd: int) -> None:
        """Windows 11 rounds top-level corners; the capture would show the
        desktop-less black behind them. DWMWA_WINDOW_CORNER_PREFERENCE (33) =
        DWMWCP_DONOTROUND (1). Harmless no-op on Windows 10."""
        value = self.ctypes.c_int(1)
        self.dwmapi.DwmSetWindowAttribute(hwnd, 33, self.ctypes.byref(value), 4)

    def capture(self, hwnd: int, path: Path) -> tuple[int, int]:
        """Render ``hwnd`` (frame included) with PrintWindow and save a PNG,
        cropped to the visible frame (the DWM extended frame bounds - the
        window rect also holds the invisible resize borders)."""
        ctypes, wt = self.ctypes, self.wt
        rect = wt.RECT()
        self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        frame = wt.RECT()
        if self.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(frame),
                                             ctypes.sizeof(frame)) != 0:
            frame = rect  # DWMWA_EXTENDED_FRAME_BOUNDS unavailable
        window_dc = self.user32.GetWindowDC(hwnd)
        memory_dc = self.gdi32.CreateCompatibleDC(window_dc)
        bitmap = self.gdi32.CreateCompatibleBitmap(window_dc, width, height)
        old = self.gdi32.SelectObject(memory_dc, bitmap)
        try:
            # PW_RENDERFULLCONTENT (2): ask DWM for the composed window, which
            # works whether or not the window is covered.
            if not self.user32.PrintWindow(hwnd, memory_dc, 2):
                raise OSError(f"PrintWindow failed for window {hwnd:#x}")
            header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
            info = ctypes.create_string_buffer(header + b"\x00" * 16)
            pixels = ctypes.create_string_buffer(width * height * 4)
            if not self.gdi32.GetDIBits(memory_dc, bitmap, 0, height, pixels, info, 0):
                raise OSError("GetDIBits failed")
        finally:
            self.gdi32.SelectObject(memory_dc, old)
            self.gdi32.DeleteObject(bitmap)
            self.gdi32.DeleteDC(memory_dc)
            self.user32.ReleaseDC(hwnd, window_dc)
        left = max(frame.left - rect.left, 0)
        top = max(frame.top - rect.top, 0)
        crop_w = min(frame.right - frame.left, width - left)
        crop_h = min(frame.bottom - frame.top, height - top)
        raw = pixels.raw
        rows = [raw[(top + y) * width * 4 + left * 4:(top + y) * width * 4 + (left + crop_w) * 4]
                for y in range(crop_h)]
        write_png(path, crop_w, crop_h, b"".join(rows))
        return crop_w, crop_h

    def find_dialogs(self, title: str) -> list[int]:
        """Visible standard dialogs (class #32770) of this process titled
        ``title`` - how a native message box is found from outside Tk."""
        ctypes, wt = self.ctypes, self.wt
        found: list[int] = []
        pid = os.getpid()
        proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def visit(hwnd, _lparam):
            owner = wt.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and self.user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                self.user32.GetClassNameW(hwnd, buf, 256)
                if buf.value == "#32770":
                    self.user32.GetWindowTextW(hwnd, buf, 256)
                    if buf.value == title:
                        found.append(hwnd)
            return True

        enum = self.user32.EnumWindows
        enum.argtypes, enum.restype = [proc, wt.LPARAM], wt.BOOL
        enum(proc(visit), 0)
        return found

    def press(self, hwnd: int, button_id: int) -> None:
        """Click a dialog button by id (WM_COMMAND), e.g. IDNO = 7."""
        self.user32.PostMessageW(hwnd, 0x0111, button_id, 0)


def capture_tk(win32: Win32, window, path: Path) -> tuple[int, int]:
    """Capture a Tk root or Toplevel; ``wm frame`` is its top-level HWND."""
    window.update_idletasks()
    hwnd = int(window.wm_frame(), 16)
    win32.square_corners(hwnd)
    pump(window, 0.4)  # let DWM recompose with square corners
    return win32.capture(hwnd, path)


def pump(widget, seconds: float) -> None:
    """Run the Tk event loop for ``seconds`` without entering mainloop()."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        widget.update()
        time.sleep(0.02)


def pump_until(widget, condition, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        widget.update()
        if condition():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------------------
# GUI session
# ---------------------------------------------------------------------------


class GatedQueue(queue.Queue):
    """The run's event queue, holding the run thread after ``pause_after``
    finished theses until :meth:`release` - so the in-progress screenshot
    catches the run mid-way regardless of machine speed. ``put`` is called on
    the run thread (the runner publishes there), never on the Tk thread."""

    def __init__(self, pause_after: int):
        super().__init__()
        self.pause_after = pause_after
        self.finished = 0
        self.paused = threading.Event()
        self._release = threading.Event()

    def put(self, item, block=True, timeout=None):
        from tta.core import events

        super().put(item, block, timeout)
        if isinstance(item, events.ThesisCompleted):
            self.finished += 1
            if self.finished == self.pause_after:
                self.paused.set()
                self._release.wait(timeout=300)

    def release(self) -> None:
        self._release.set()


def toplevels(widget) -> list:
    """Every Toplevel below ``widget`` - dialogs are parented to the root or
    to the widget that opened them (the details panel hangs off the grid)."""
    found = []
    for child in widget.winfo_children():
        if child.winfo_class() == "Toplevel":
            found.append(child)
        found += toplevels(child)
    return found


def toplevel_names(root) -> set:
    return {str(w) for w in toplevels(root)}


def new_toplevels(root, before: set) -> list:
    return [w for w in toplevels(root) if str(w) not in before]


def run_gui(project, out: Path, wanted: set, log) -> None:
    """Drive MainWindow through a run and its dialogs; capture what's wanted."""
    from tta.core.i18n import _
    from tta.ui.tk import dialogs
    from tta.ui.tk.main_window import BTN_CANCEL, MainWindow

    win32 = Win32()
    window = MainWindow(project)
    root = window.root
    root.geometry("%dx%d+40+40" % MAIN_GEOMETRY)
    pump(root, 0.5)

    def shot(name, tk_window):
        if name in wanted:
            size = capture_tk(win32, tk_window, out / f"{name}.png")
            log(f"{name}.png  {size[0]}x{size[1]}")

    # -- run, paused mid-way -------------------------------------------------
    gate = GatedQueue(PAUSE_AFTER_THESES)
    window._event_queue = gate  # the run subscribes this queue's put at start
    try:
        window._run(rerun=False)
        if not pump_until(root, gate.paused.is_set, timeout=300):
            raise RuntimeError("the run never reached the pause point")
        # let the queue drain and the ETA leave "estimating..." (damped, #54)
        label = lambda: window._progress_label.cget("text") if window._progress_label else ""
        pump_until(root, lambda: "~" in label(), timeout=8)
        pump(root, 1.0)
        if BTN_CANCEL not in window._toolbar_buttons:
            raise RuntimeError("expected the run toolbar (Cancel + progress)")
        shot("app-analyselauf", root)
        gate.release()
        done = lambda: not (window._run_thread and window._run_thread.is_alive())
        if not pump_until(root, done, timeout=600):
            raise RuntimeError("the run did not finish")
        pump(root, 1.0)  # RunCompleted drained, toolbar restored
        shot("app-hauptfenster-basis", root)

        # -- details panel of an error cell: the corrupt PDF's page count -------
        if "app-detailpanel" in wanted:
            grid = window.grid_view
            r = next(i for i, row in enumerate(grid.rows)
                     if row.thesis.pdf_filename == DETAIL_THESIS)
            names = grid._column_names()
            c = names.index(DETAIL_METRIC)
            grid.sheet.select_cell(r, c, redraw=True)
            before = toplevel_names(root)
            grid._on_double_click(None)  # the grid's own "open this" gesture
            panel = new_toplevels(root, before)
            if not panel:
                raise RuntimeError("the details panel did not open")
            panel[0].geometry("+80+80")
            pump(root, 0.3)
            shot("app-detailpanel", panel[0])
            panel[0].destroy()
            grid.sheet.deselect("all")

        # -- help viewer on its cover page (the Help button, #92) ------------------
        if "app-hilfe" in wanted:
            window._show_help()
            help_window = window._help_window
            help_window.geometry("1000x680+80+60")
            pump(root, 0.3)
            shot("app-hilfe", help_window)
            help_window.destroy()

        # -- privacy statement: the help viewer's privacy page (#92) ------------
        if "app-datenschutz" in wanted:
            window._show_privacy()
            privacy = window._help_window
            privacy.geometry("1000x680+80+60")
            pump(root, 0.3)
            shot("app-datenschutz", privacy)
            privacy.destroy()

        # -- export: the native "Export complete" message box --------------------
        if "app-export" in wanted:
            capture_export_dialog(win32, window, dialogs, _, out / "app-export.png", log)

        # -- extended mode -------------------------------------------------------
        if "app-hauptfenster-erweitert" in wanted:
            window._extended.set(True)
            window._mode_changed()
            pump(root, 0.5)
            shot("app-hauptfenster-erweitert", root)
    finally:
        # On a failure too: never leave the run thread parked on the gate
        # (it holds the project database open) or a window on screen.
        gate.release()
        if window._runner is not None:
            window._runner.cancel()
        if window._run_thread is not None:
            window._run_thread.join(timeout=60)
        root.destroy()


def capture_export_dialog(win32: Win32, window, dialogs, _, path: Path, log) -> None:
    """Run the real export flow. The save-as dialog is answered with its own
    proposed path (it would show the user's folders); the confirmation that
    follows is a native message box, blocking the Tk thread - so a helper
    thread finds it, captures it and answers "No" (do not open the folder)."""
    title = _("Export complete")
    result: dict = {}

    def watcher():
        end = time.monotonic() + 30
        while time.monotonic() < end:
            found = win32.find_dialogs(title)
            if found:
                time.sleep(0.5)  # let it paint
                try:
                    win32.square_corners(found[0])
                    time.sleep(0.3)
                    result["size"] = win32.capture(found[0], path)
                finally:
                    win32.press(found[0], 7)  # IDNO
                return
            time.sleep(0.1)

    def proposed(**options):
        return str(Path(options["initialdir"]) / options["initialfile"])

    original = dialogs.filedialog.asksaveasfilename
    dialogs.filedialog.asksaveasfilename = proposed
    thread = threading.Thread(target=watcher, daemon=True)
    thread.start()
    try:
        dialogs.export_flow(window.root, window.project)
    finally:
        dialogs.filedialog.asksaveasfilename = original
    thread.join(timeout=35)
    if "size" not in result:
        raise RuntimeError("the export confirmation was not captured")
    log(f"{path.name}  {result['size'][0]}x{result['size'][1]}")


# ---------------------------------------------------------------------------
# Browser rendering (report, CLI transcript)
# ---------------------------------------------------------------------------

BROWSER_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "microsoft-edge", "chromium", "chromium-browser", "google-chrome",
)


def find_browser(explicit: str | None) -> str | None:
    for candidate in ((explicit,) if explicit else BROWSER_CANDIDATES):
        if Path(candidate).is_file():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def browser_screenshot(browser: str, source: Path, png: Path, size: tuple[int, int],
                       profile: Path, script_budget_ms: int = 0) -> None:
    """Rasterise a local file with a headless Chromium-family browser on a
    throwaway profile (never the user's); network features are switched off -
    everything rendered here is local. The browser writes into the scratch
    directory; the result replaces ``png`` like every other image."""
    shot = profile.parent / f"browser-{png.name}"
    shot.unlink(missing_ok=True)
    command = [
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions",
        "--disable-sync", "--disable-background-networking",
        "--disable-component-update", "--no-pings", "--mute-audio",
        f"--user-data-dir={profile}", "--force-device-scale-factor=1",
        f"--window-size={size[0]},{size[1]}", f"--screenshot={shot}",
        *([f"--virtual-time-budget={script_budget_ms}"] if script_budget_ms else []),
        source.resolve().as_uri(),
    ]
    subprocess.run(command, check=False, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not shot.is_file():
        raise RuntimeError(f"the browser wrote no screenshot: {' '.join(command)}")
    write_file(png, shot.read_bytes())


def render_report(project_dir: Path, workdir: Path, browser: str, out: Path, log) -> None:
    """The HTML report exactly as the GUI's Report button writes it, but with a
    fixed timestamp and without opening the user's default browser. It compares
    the demo theses with the reference aggregates the app ships (ADR-0025)."""
    from tta.core import report
    from tta.core.project import Project

    with Project.open(project_dir) as project:
        html = report.render_html(report.collect(project.repo), generated_at=REPORT_TIMESTAMP)
    path = report.default_report_path(project_dir, today=REPORT_TIMESTAMP.date())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    browser_screenshot(browser, path, out / "app-bericht.png", REPORT_WINDOW,
                       workdir / "browser-profile", REPORT_SCRIPT_BUDGET_MS)
    log("app-bericht.png  %dx%d" % png_size(out / "app-bericht.png"))


def cli(args: list[str], cwd: Path) -> str:
    """Run ``tta`` in a subprocess with colour forced on; stdout and stderr
    share one pipe, so the transcript keeps their real order."""
    env = dict(os.environ, FORCE_COLOR="1", COLUMNS=str(CLI_WIDTH), TTY_COMPATIBLE="1",
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]))
    env.pop("NO_COLOR", None)
    env.pop("TTA_LOCALE", None)  # the project's tta.toml decides: German
    done = subprocess.run(
        [sys.executable, "-c", "from tta.cli.main import main; main()", *args],
        cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600,
    )
    # CRLF from a Windows stdout: rich takes the "\r" as a line reset and
    # blanks the line
    return done.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")


def elide_run_output(output: str) -> str:
    """Keep the head and tail of the per-module progress lines of `tta run`;
    the full log is dozens of lines per thesis."""
    lines = output.splitlines()
    module_lines = [i for i, line in enumerate(lines) if line.lstrip().startswith("[thesis")]
    if len(module_lines) <= CLI_RUN_HEAD + CLI_RUN_TAIL + 1:
        return output
    cut_from = module_lines[CLI_RUN_HEAD]
    cut_to = len(lines) - CLI_RUN_TAIL - 1  # keep the summary line too
    skipped = cut_to - cut_from
    marker = f"\x1b[2m  [... {skipped} weitere Zeilen gek\u00fcrzt ...]\x1b[0m"
    return "\n".join(lines[:cut_from] + [marker] + lines[cut_to:])


def render_cli(workdir: Path, browser: str, out: Path, log) -> None:
    """`tta run`, `tta list`, `tta export` on a small project of its own,
    recorded by rich as an SVG terminal and rasterised by the browser."""
    from rich.console import Console
    from rich.text import Text

    project_dir = workdir / "cli-projekt"
    write_project_config(project_dir)
    write_demo_pdfs(project_dir / "beispiele", DEMO_THESES[:CLI_THESES])
    console = Console(record=True, width=CLI_WIDTH, file=io.StringIO(),
                      force_terminal=True, color_system="truecolor")
    for command in (["run", "beispiele"], ["list"], ["export"]):
        console.print(Text.assemble(("PS C:\\Beispiel> ", "bold green"),
                                    ("tta " + " ".join(command), "bold")))
        output = cli(command, cwd=project_dir)
        if command[0] == "run":
            output = elide_run_output(output)
        console.print(Text.from_ansi(output.rstrip("\n")))
    svg = console.export_svg(title="tta - Kommandozeile")
    # rich points the font at a CDN; the render stays offline and falls back
    # to the browser's monospace font. Its macOS-style window buttons go too.
    svg = re.sub(r',?\s*url\("[^"]*"\)\s*format\("[^"]*"\)', "", svg)
    svg = re.sub(r"<circle[^>]*/>", "", svg)
    svg_path = workdir / "cli.svg"
    svg_path.write_text(svg, encoding="utf-8")
    match = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    size = (int(float(match.group(1))) + 1, int(float(match.group(2))) + 1)
    browser_screenshot(browser, svg_path, out / "app-cli.png", size,
                       workdir / "browser-profile")
    log("app-cli.png  %dx%d" % png_size(out / "app-cli.png"))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="output directory for the PNGs")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--only", nargs="+", metavar="NAME", choices=IMAGES,
                           help="build only these images (default: all)")
    selection.add_argument("--readme", action="store_true",
                           help="build the README subset: " + ", ".join(README_IMAGES))
    parser.add_argument("--workdir", type=Path,
                        default=Path(tempfile.gettempdir()) / "tta-screenshots",
                        help="scratch directory, recreated on every run")
    parser.add_argument("--browser", help="Chromium-family browser executable "
                        "(default: Edge/Chrome/Chromium, whichever is found)")
    parser.add_argument("--keep", action="store_true",
                        help="keep the scratch directory afterwards")
    parser.add_argument("--list", action="store_true", help="print the image names")
    args = parser.parse_args(argv)
    if not args.list and args.out is None:
        parser.error("--out is required")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list:
        print("\n".join(IMAGES))
        return 0
    wanted = set(README_IMAGES if args.readme else args.only or IMAGES)
    gui_wanted = wanted & set(GUI_IMAGES)
    if gui_wanted and sys.platform != "win32":
        sys.exit("the Tk captures need Windows (Win32 PrintWindow); "
                 "on this platform use --only app-bericht app-cli")
    browser = None
    if wanted & {"app-bericht", "app-cli"}:
        browser = find_browser(args.browser)
        if browser is None:
            sys.exit("no Chromium-family browser found; pass --browser")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    workdir = args.workdir.resolve()
    prepare_workdir(workdir)
    log = lambda line: print("  " + line, flush=True)

    if sys.platform == "win32":
        import ctypes

        # Per-monitor DPI aware: crisp captures and window rects in real
        # pixels; at 100 % scaling this changes nothing.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except OSError:
            pass

    # Relative project path: the window title, the export path and the CLI
    # output then show "Beispielprojekt", not a scratch path holding the
    # user's account name. Workers inherit the working directory.
    previous_cwd = Path.cwd()
    os.chdir(workdir)
    try:
        from tta.core import i18n

        print(f"demo project in {workdir / PROJECT_NAME}")
        project = build_demo_project(workdir, Path(PROJECT_NAME))
        i18n.install(config_locale=project.config.ui_locale)
        with project:
            if gui_wanted:
                run_gui(project, out, gui_wanted, log)  # analyses during the run
            elif "app-bericht" in wanted:
                runner = project.make_runner()
                runner.execute(runner.plan())  # headless: the report needs data
        if "app-bericht" in wanted:
            render_report(Path(PROJECT_NAME), workdir, browser, out, log)
        if "app-cli" in wanted:
            render_cli(workdir, browser, out, log)
    finally:
        os.chdir(previous_cwd)
        if not args.keep and not clean_workdir(workdir):
            print(f"note: {workdir} could not be removed completely; "
                  "the next run deletes it")
    print(f"done: {len(wanted)} image(s) in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
