"""Unit tests for mod_readability (SDD Sec. 7.1 #7) - Flesch en / Amstad de."""

import os

import pytest

from tta.core.modules.base import NotApplicable
from tta.core.modules.readability import Readability

ENGLISH = "The cat sat on the mat. The dog ran to the park. We like short words."
GERMAN = "Die Katze sitzt auf der Matte. Der Hund l\u00e4uft in den Park. Wir m\u00f6gen kurze W\u00f6rter."


def test_english_flesch(build_ctx):
    metrics = Readability().run(
        build_ctx(raw_text=ENGLISH, language={"code": "en", "confidence": 1.0})
    ).metrics
    assert metrics["flesch_reading_ease"] > 80  # simple short-word prose


def test_german_uses_amstad(build_ctx):
    de = Readability().run(
        build_ctx(raw_text=GERMAN, language={"code": "de", "confidence": 1.0})
    ).metrics["flesch_reading_ease"]
    # Amstad differs from plain Flesch on the same text; the en formula on
    # this German text gives a different value than the de formula
    en_formula = Readability().run(
        build_ctx(raw_text=GERMAN, language={"code": "en", "confidence": 1.0})
    ).metrics["flesch_reading_ease"]
    assert de != pytest.approx(en_formula)


def test_unsupported_language_is_not_applicable(build_ctx):
    with pytest.raises(NotApplicable, match="no readability formula for language: it"):
        Readability().run(build_ctx(raw_text="Ciao.", language={"code": "it", "confidence": 1.0}))


REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]

# Runs in a FRESH interpreter: textstat memoises the corpus (@typed_cache on
# get_cmudict) and NLTK's LazyCorpusLoader caches the reader, so once any test
# in this process has loaded cmudict from the real data path, no monkeypatching
# of nltk.data.path can make it look absent again. A subprocess is also what a
# real run is - one process per thesis, spawned.
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
                artefact_kinds.RAW_TEXT: workdir / "raw.txt",
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
    (data_dir / "tokenizers" / "punkt_tab").symlink_to(
        str(nltk.data.find("tokenizers/punkt_tab"))
    )
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
