"""Unit tests for mod_readability (SDD Sec. 7.1 #7) - Flesch en / Amstad de."""

import os
import shutil

import pytest

from tta.core.modules.base import NotApplicable
from tta.core.modules.readability import Readability

ENGLISH = "The cat sat on the mat. The dog ran to the park. We like short words."
GERMAN = "Die Katze sitzt auf der Matte. Der Hund l\u00e4uft in den Park. Wir m\u00f6gen kurze W\u00f6rter."


def test_english_flesch(build_ctx):
    metrics = Readability().run(
        build_ctx(prose_text=ENGLISH, language={"code": "en", "confidence": 1.0})
    ).metrics
    assert metrics["flesch_reading_ease"] > 80  # simple short-word prose


def test_german_uses_amstad(build_ctx):
    de = Readability().run(
        build_ctx(prose_text=GERMAN, language={"code": "de", "confidence": 1.0})
    ).metrics["flesch_reading_ease"]
    # Amstad differs from plain Flesch on the same text; the en formula on
    # this German text gives a different value than the de formula
    en_formula = Readability().run(
        build_ctx(prose_text=GERMAN, language={"code": "en", "confidence": 1.0})
    ).metrics["flesch_reading_ease"]
    assert de != pytest.approx(en_formula)


def test_unsupported_language_is_not_applicable(build_ctx):
    with pytest.raises(NotApplicable, match="no readability formula for language: it"):
        Readability().run(build_ctx(prose_text="Ciao.", language={"code": "it", "confidence": 1.0}))


REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]

# Runs in a FRESH interpreter: textstat memoises the corpus (@typed_cache on
# get_cmudict) and NLTK's LazyCorpusLoader caches the reader, so once any test
# in this process has loaded cmudict from the real data path, no monkeypatching
# of nltk.data.path can make it look absent again. A subprocess is also what a
# real run is - a spawned worker process (ADR-0013).
_PROBE = r"""
import json, os, socket, sys

attempts = []


def _spy(*args, **kwargs):
    attempts.append(repr(args[:1]))
    raise AssertionError("outbound connection attempted")


socket.create_connection = _spy
socket.socket.connect = _spy

import nltk
nltk.data.path = [os.environ["TTA_TEST_NLTK_DATA"]]

from tta.core.modules.readability import Readability

result = {}
ctx = json.loads(os.environ["TTA_TEST_CTX"])


def run(language, text):
    from pathlib import Path
    import tempfile

    workdir = Path(tempfile.mkdtemp())
    (workdir / "raw.txt").write_text(text, encoding="utf-8")
    (workdir / "lang.json").write_text(
        json.dumps({"code": language, "confidence": 1.0}), encoding="utf-8"
    )
    from tta.core import artefact_kinds
    from tta.core.modules.base import RunContext
    from tta.core.types import Thesis

    return Readability().run(
        RunContext(
            thesis=Thesis(id=1, pdf_sha256=None,
                          pdf_path=str(workdir / "x.pdf"), pdf_filename="x.pdf"),
            artefacts={
                artefact_kinds.PROSE_TEXT: workdir / "raw.txt",
                artefact_kinds.LANGUAGE: workdir / "lang.json",
            },
            workdir=workdir,
        )
    )


try:
    result["de"] = run("de", ctx["german"]).metrics["flesch_reading_ease"]
except Exception as exc:
    result["de"] = f"{type(exc).__name__}: {exc}"

try:
    run("en", ctx["english"])
    result["en"] = "UNEXPECTED SUCCESS"
except RuntimeError as exc:
    result["en"] = f"RuntimeError: {exc}"
except Exception as exc:
    result["en"] = f"{type(exc).__name__}: {exc}"

result["attempts"] = attempts
print("RESULT " + json.dumps(result))
"""


def _punkt_only_nltk_data(tmp_path):
    """An NLTK data dir with punkt_tab but no cmudict - a from-source machine
    (and the CI runner before #75)."""
    import nltk

    data_dir = tmp_path / "nltk_data"
    (data_dir / "tokenizers").mkdir(parents=True)
    source = str(nltk.data.find("tokenizers/punkt_tab"))
    target = data_dir / "tokenizers" / "punkt_tab"
    try:
        target.symlink_to(source, target_is_directory=True)
    except OSError:
        # Windows refuses symlinks without Developer Mode or admin rights
        # (WinError 1314); a copy (~11 MB) is the same data dir to NLTK.
        shutil.copytree(source, target)
    return data_dir


def _run_probe(tmp_path):
    import json
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["TTA_TEST_NLTK_DATA"] = str(_punkt_only_nltk_data(tmp_path))
    env["TTA_TEST_CTX"] = json.dumps({"english": ENGLISH, "german": GERMAN})
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, env=env,
        cwd=str(REPO_ROOT),
    )
    line = next(
        (ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")), None
    )
    assert line, f"probe produced no result\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    return json.loads(line[len("RESULT "):])


def test_no_outbound_connection_when_cmudict_is_missing(tmp_path):
    """#75, QA-PRIV: textstat calls nltk.download('cmudict', quiet=True) itself
    when the corpus is absent, and quiet=True swallows the failure. The module
    must make that impossible rather than unlikely."""
    result = _run_probe(tmp_path)

    assert result["attempts"] == [], "an outbound connection was attempted"
    # German does not need cmudict and must still compute
    assert isinstance(result["de"], (int, float)) and result["de"] > 0, result["de"]
    # English cannot be computed without it, and says so actionably
    assert result["en"].startswith("RuntimeError:"), result["en"]
    assert "cmudict" in result["en"]
    assert "nltk.downloader cmudict" in result["en"]
    assert "QA-PRIV" in result["en"]


# -- #86: no per-text state survives a run in a reused worker ----------------

LONG_GERMAN = (
    "Die Hyphenierungsbibliothek merkt sich jedes Wort, das sie jemals getrennt "
    "hat. Ein langlebiger Arbeitsprozess darf deshalb nicht mit dem Korpus "
    "wachsen. Donaudampfschifffahrtsgesellschaftskapitaensmuetze."
)


def _textstat_cache_sizes():
    """currsize of every lru cache textstat exposes, minus the kept loaders."""
    import sys

    from tta.core.modules.readability import _KEPT_TEXTSTAT_CACHES

    sizes = {}
    for name, module in list(sys.modules.items()):
        if module is None or not name.startswith("textstat"):
            continue
        for attr, obj in vars(module).items():
            info = getattr(obj, "cache_info", None)
            if attr not in _KEPT_TEXTSTAT_CACHES and callable(info):
                sizes[f"{name}.{attr}"] = info().currsize
    return sizes


def _pyphen_word_cache_sizes():
    import pyphen

    return {str(path): len(hd.cache) for path, hd in pyphen.hdcache.items()}


def test_run_leaves_no_per_text_cache_behind(build_ctx):
    """Workers are long-lived (#86): textstat's text-keyed lru caches and
    pyphen's unbounded per-word cache grew a worker by ~2.4 MB per thesis.
    After a run both must be empty, while the per-language loaders stay warm."""
    import textstat

    from tta.core.modules.readability import flesch_reading_ease

    # without the sweep, a raw textstat call does fill both caches
    textstat.set_lang("de")
    flesch_reading_ease(LONG_GERMAN)
    assert any(_textstat_cache_sizes().values())
    assert any(_pyphen_word_cache_sizes().values())

    for language, text in (("de", LONG_GERMAN), ("en", ENGLISH)):
        Readability().run(build_ctx(prose_text=text, language={"code": language, "confidence": 1.0}))
        assert not any(_textstat_cache_sizes().values()), _textstat_cache_sizes()
        assert not any(_pyphen_word_cache_sizes().values()), _pyphen_word_cache_sizes()

    from textstat.backend.utils import get_pyphen

    assert get_pyphen.cache_info().currsize >= 1  # the dictionary stays loaded


def test_clearing_the_caches_changes_no_result(build_ctx):
    """The caches are pure: a score computed after a sweep equals the score
    computed with warm caches, so no module version bump is needed (#86)."""
    import textstat

    from tta.core.modules.readability import drop_text_caches, flesch_reading_ease

    for language, text in (("de", LONG_GERMAN), ("en", ENGLISH)):
        textstat.set_lang(language)
        warm = [flesch_reading_ease(text) for _ in range(2)]
        drop_text_caches()
        cold = Readability().run(
            build_ctx(prose_text=text, language={"code": language, "confidence": 1.0})
        ).metrics["flesch_reading_ease"]
        again = Readability().run(
            build_ctx(prose_text=text, language={"code": language, "confidence": 1.0})
        ).metrics["flesch_reading_ease"]
        assert warm[0] == warm[1] == cold == again


def test_cache_sweep_survives_changed_library_internals(build_ctx, monkeypatch):
    """The sweep reaches into textstat/pyphen internals, so a future version
    that renames or retypes them must not fail the module (#86)."""
    import pyphen
    import textstat

    class Exploding:
        def cache_clear(self):
            raise RuntimeError("internals changed")

    monkeypatch.setattr(pyphen, "hdcache", object(), raising=False)  # no .values()
    monkeypatch.setattr(textstat, "_tta_test_exploding", Exploding(), raising=False)
    metrics = Readability().run(
        build_ctx(prose_text=ENGLISH, language={"code": "en", "confidence": 1.0})
    ).metrics
    assert metrics["flesch_reading_ease"] > 80

    class OddDict:
        cache = None  # not a dict any more

    monkeypatch.setattr(pyphen, "hdcache", {"x": OddDict()}, raising=False)
    metrics = Readability().run(
        build_ctx(prose_text=GERMAN, language={"code": "de", "confidence": 1.0})
    ).metrics
    assert "flesch_reading_ease" in metrics

    monkeypatch.delattr(pyphen, "hdcache")  # gone altogether
    metrics = Readability().run(
        build_ctx(prose_text=GERMAN, language={"code": "de", "confidence": 1.0})
    ).metrics
    assert "flesch_reading_ease" in metrics
