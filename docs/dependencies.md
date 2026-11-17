---
title: "Thesis Text Analyzer — Third-Party Dependency Inventory"
subtitle: "Purpose, version, licence, and the GPL-3.0-or-later compatibility audit"
status: "Current as of 2026-08-26 (issue #37)"
---

# Third-Party Dependency Inventory

**Scope.** Every third-party component the Thesis Text Analyzer depends on, for each: what it is
*for*, which version was audited, its licence, and whether it ends up inside the distributed binary.
This page doubles as the **one-time licence-compatibility audit** that
[ADR-0017](adr/0017-license.md) asks for ("A one-time license audit should confirm this before
release").

**This is the human-readable inventory.** The machine-generated `THIRD_PARTY_LICENSES.txt` — the
verbatim licence *texts* that must accompany the binary — is produced by the packaging work
(issue #4). The two are complementary: that file discharges the attribution obligation, this page
records *why each item is allowed to be there*. Where they disagree, this page is the reasoning of
record and the generated file is the artefact to fix (see [§8](#8-audit-findings), finding **F1**).

**Derivation.** Everything below was read out of the real environment (conda env `pds`,
CPython 3.12.13, Linux x86-64) with `importlib.metadata` and by opening the licence files the
wheels actually ship — not from memory and not from upstream websites. The regeneration recipe is
in [§9](#9-how-to-regenerate-this-page).

---

## 1. The rule this audit applies

The project's outbound licence is **GPL-3.0-or-later** ([ADR-0017](adr/0017-license.md), issue #8;
`pyproject.toml` `license = "GPL-3.0-or-later"`). Consequently every inbound component must be
distributable *under* GPL-3.0-or-later. Concretely, an inbound licence passes if it is:

| Class | Examples in this project | Why it passes |
|---|---|---|
| Permissive | MIT, MIT-CMU, BSD-2/3-Clause, ISC, 0BSD, Zlib, CC0-1.0, PSF-2.0, OFL-1.1 | No condition conflicts with the GPL; the combined work simply conveys under GPL-3.0-or-later. |
| Apache-2.0 | nltk, langdetect, regex (additions) | One-way compatible with GPLv3 (its patent/termination clauses are GPLv3-compatible but *not* GPLv2-compatible). Safe because we are v3-or-later, **not** v2. |
| MPL-2.0 | tqdm (part) | MPL-2.0 §3.3 explicitly permits conveying under a "Secondary License" (GPL/LGPL/AGPL). |
| Weak copyleft | LGPL-2.1-or-later (pyphen dictionaries) | LGPL-2.1 §3 permits relicensing to GPL-2.0-or-later, hence to GPL-3.0. |
| Same-or-stronger copyleft | GPL-2.0-or-later, GPL-3.0-or-later, AGPL-3.0 | "or later" reaches v3; GPLv3 §13 permits combining with an AGPLv3 part (ADR-0017 §Open question). |

A licence **fails** if it is copyleft-incompatible in the outbound direction (MPL-1.1 alone,
CDDL, EPL, bare CNRI-Python), field-of-use restricted (non-commercial, research-only), or
proprietary. **No component in the shipped dependency set fails.** Four require a recorded
rationale rather than a one-word verdict; they are [§8](#8-audit-findings) findings F1–F4.

---

## 2. Runtime dependencies — direct

These are the nine entries in `pyproject.toml` `[project].dependencies`. All nine are frozen into
the distributed binaries.

| Package | Version | Licence (SPDX) | Purpose in this project | Verdict |
|---|---|---|---|---|
| `langdetect` | 1.0.9 | **Apache-2.0** (see F1) | `mod_classify_language` — the `language` artefact plus `language_code` / `language_confidence`. Python port of Nakatani's n-gram profile detector. | ✅ compatible |
| `nltk` | 3.9.4 | Apache-2.0 | `mod_tokenize` — punkt sentence segmentation and Treebank word tokenisation; the `tokens` artefact every word-level metric consumes. Also the loader textstat reaches CMUdict through. | ✅ compatible |
| `textstat` | 0.7.13 | MIT | `mod_readability` — `flesch_reading_ease` (Flesch for `en`, Amstad for `de`). | ✅ compatible |
| `pypdf` | 6.13.2 | BSD-3-Clause | `mod_count_images` (`n_images`) and `mod_extract_pdf_metadata` (the `pdf_metadata` artefact and its six curated metrics). | ✅ compatible |
| `click` | 8.3.3 | BSD-3-Clause | The CLI adapter (`tta.cli`) — commands, options, `--help` ([ADR-0003](adr/0003-cli-first-class.md)). | ✅ compatible |
| `rich` | 15.0.0 | MIT | CLI tables and markdown help rendering ([ADR-0012](adr/0012-help-content.md)). | ✅ compatible |
| `tomli-w` | 1.2.0 | MIT | Writing `tta.toml`. (Reading uses stdlib `tomllib` — no dependency.) | ✅ compatible |
| `tksheet` | 7.6.0 | MIT | The data grid with per-cell styling ([ADR-0001](adr/0001-ui-toolkit.md)). | ✅ compatible |

### 2.1 The PDF extractor (optional extra, but shipped)

| Package | Version | Licence | Purpose | Verdict |
|---|---|---|---|---|
| `pymupdf` | 1.27.2.3 | **AGPL-3.0-or-later** OR Artifex commercial | `mod_extract_pymupdf` — the `raw_text` producer, i.e. the head of the whole pipeline. Declared in the `pymupdf` optional extra, but installed by the release job and named in `packaging/tta.spec` `hiddenimports`. | ✅ compatible under GPLv3 §13 (see F2) |

`pymupdf` sits in an extra for historical reasons (the retired AGPL gate). It is **not** optional in
the shipped product: `.github/workflows/ci.yml` installs `.[build,pymupdf]` for the release build.
See [§8](#8-audit-findings) F2 for the AGPL reasoning and F5 for the packaging inconsistency.

---

## 3. Runtime dependencies — transitive

Pulled in automatically and therefore frozen into the binary too. `Via` names the direct dependency
that requires them.

| Package | Version | Licence (SPDX) | Via | What it does here | Verdict |
|---|---|---|---|---|---|
| `pyphen` | 0.17.2 | **GPL-2.0-or-later OR LGPL-2.1-or-later OR MPL-1.1** (tri-licence) | textstat | Hyphenation-pattern syllable counting — the German syllable source for Amstad, and the English fallback for words missing from CMUdict. Bundles ~84 LibreOffice hyphenation dictionaries (6.1 MB). | ✅ compatible (see F3) |
| `regex` | 2026.4.4 | **Apache-2.0 AND CNRI-Python** (for the CPython-derived part) | nltk | Alternative regex engine NLTK declares as a hard requirement. Nothing under `tta/` imports it (every module uses stdlib `re`), and NLTK reaches for it only in `nltk/chunk/regexp.py` and `nltk/tokenize/casual.py` — neither on the punkt/Treebank path we use. | ✅ compatible (see F4) |
| `joblib` | 1.5.3 | BSD-3-Clause | nltk | NLTK-internal parallelism helper; unused by our modules. | ✅ compatible |
| `tqdm` | 4.67.3 | **MPL-2.0 AND MIT** | nltk | NLTK-internal progress bars; never surfaced in our UI. | ✅ compatible |
| `six` | 1.17.0 | MIT | langdetect | Py2/Py3 compatibility shim langdetect still imports. | ✅ compatible |
| `packaging` | 26.0 | Apache-2.0 OR BSD-2-Clause | pytest, pyinstaller | Version parsing. | ✅ compatible |
| `markdown-it-py` | 4.2.0 | MIT | rich | Markdown parsing for the rendered help pages. | ✅ compatible |
| `mdurl` | 0.1.2 | MIT | rich (via markdown-it-py) | URL handling inside the markdown parser. | ✅ compatible |
| `pygments` | 2.20.0 | BSD-2-Clause | rich | Syntax highlighting in rich output. | ✅ compatible |
| `setuptools` | 82.0.1 | MIT | textstat; also the PEP 517 build backend | Runtime presence is textstat's doing: it imports `pkg_resources` inside `_get_lang_easy_words` (Dale-Chall word lists), a code path `mod_readability` never enters. | ✅ compatible |

**Nothing in the runtime closure is proprietary, non-commercial, or copyleft-incompatible.**

---

## 4. Bundled data, models, and dictionaries

Data is as much a licensing surface as code, and in a `--onefile` binary it is *inside the
artefact*. This is the part a naive `pip`-metadata scraper misses entirely.

| Component | Origin | Licence | Bundled? | Notes |
|---|---|---|---|---|
| NLTK **`punkt_tab`** models (19 languages, ~4.3 MB) | `nltk_data`, pretrained by Jan Strunk / Tibor Kiss | **No licence statement in the package** (see F6) | Yes — `packaging/tta.spec` `datas`, resolved at build time by `nltk.data.find`, exposed by `packaging/rthook_nltk.py` | Only `english` and `german` are ever loaded (`mod_tokenize.NLTK_LANGUAGES`); the other 17 ride along. Provenance and bias: [`model-limitations.md`](model-limitations.md) §2. |
| **CMUdict** 0.7a (127,069 entries) | Carnegie Mellon University, via the NLTK `cmudict` corpus | BSD-2-Clause (CMU 1993–2008) | **Yes** — `nltk_data/corpora/cmudict` (since #75) | textstat's primary English syllable source. Was absent from `packaging/tta.spec`, which let `textstat` call `nltk.download('cmudict')` itself — both a licensing gap and an offline-promise bug (F7). Now bundled, and `mod_readability` blocks the download path outright. |
| **Pyphen** hyphenation dictionaries (~84 files, 6.1 MB) | LibreOffice / OpenOffice.org dictionaries, from TeX pattern files | GPL / LGPL-2-or-later / MPL, per dictionary. `hyph_de_AT/CH/DE.dic`: LGPL-2-or-later over LPPL `dehyphn.tex`. `hyph_en_GB/US.dic`: BSD-style over `ukhyphen.tex`/`hyph_en_US`. | Yes — inside the `pyphen` wheel | Only `de_AT` and `en_GB` are actually consulted, by accident of pyphen's short-code resolution ([`model-limitations.md`](model-limitations.md) §4.2). |
| SQL migrations, help markdown | This project | GPL-3.0-or-later | Yes | First-party, listed for completeness. |

---

## 5. Native libraries vendored inside wheels

`--onefile` extracts these shared objects at run time, so they are redistributed with the binary
even though no `pyproject.toml` line mentions them.

| Vendored in | Libraries (as shipped on Linux x86-64) | Licences | Verdict |
|---|---|---|---|
| `numpy` (`numpy.libs/`) | `libscipy_openblas64_`, `libgfortran.so.5`, `libquadmath.so.0` | OpenBLAS: BSD-3-Clause. libgfortran/libquadmath: **GPL-3.0-or-later WITH GCC-exception-3.1** | ✅ compatible — and doubly so: GPL-3.0-or-later is our own licence, so the runtime exception is not even load-bearing here. |
| CPython itself (bundled by PyInstaller) | libpython3.12, `_sqlite3` → SQLite, `_tkinter` → Tcl/Tk 8.6, zlib, bz2, lzma, libffi | Python: **PSF-2.0** (GPL-compatible). SQLite 3.51.2: **public domain**. Tcl/Tk: TCL licence (BSD-style). zlib/bzip2/xz/libffi: permissive. | ✅ compatible |

**Pillow is no longer shipped (2026-10-14, #52, #85).** Earlier builds carried `pillow`
(`pillow.libs/`: freetype, harfbuzz, libjpeg-turbo, libpng16, libtiff, libwebp, libavif, openjp2,
lcms2, brotli, zstd, liblzma, libxcb, libXau; all permissive or GPL-compatible dual, freetype taken
under FTL). It was never a declared dependency, only pulled in from the build environment; since
`mod_count_images` stopped decoding images ([ADR-0021](adr/0021-image-counting.md)) nothing needs
it, so the spec excludes `PIL` and the build check rejects it
([ADR-0014](adr/0014-distribution.md)).

`sqlite3` and `tkinter` are stdlib modules but real redistributed third-party code — SQLite backs
the entire persistence layer (`tta/core/db`) and Tk backs the whole GUI. They belong in
`THIRD_PARTY_LICENSES.txt`.

---

## 6. Build- and development-only dependencies

**Not distributed.** These never enter the binary, so they impose no obligation on the outbound
licence — a build tool is not a derivative-work relationship. Listed because ADR-0017 asked for
"both runtime and build deps".

| Package | Version | Licence | Purpose |
|---|---|---|---|
| `pyinstaller` | 6.21.0 | **GPL-2.0-or-later WITH a bundling exception** | Freezes the two `--onefile` binaries ([ADR-0014](adr/0014-distribution.md)). The exception explicitly permits building and distributing non-GPL applications; ours is GPL-3.0-or-later anyway, so neither the exception nor the GPLv2→v3 step matters. |
| `pyinstaller-hooks-contrib` | 2026.6 | Apache-2.0 OR GPL-2.0 | Third-party import hooks PyInstaller consults at analysis time. |
| `altgraph` | 0.17.5 | MIT | Dependency-graph library PyInstaller uses. |
| `setuptools` | 82.0.1 | MIT | PEP 517 build backend (`setuptools>=77` for PEP 639 SPDX expressions). |
| `wheel` | 0.46.3 | MIT | Present in the environment; not declared in `[build-system].requires` (modern setuptools vendors what it needs). Listed because it is installed alongside the build tooling. |
| `pytest` | 9.0.3 | MIT | Test runner (QA-TEST). |
| `iniconfig` | 2.3.0 | MIT | pytest internals. |
| `pluggy` | 1.6.0 | MIT | pytest plugin system. |

The one PyInstaller nuance worth stating: the **bootloader** it links into the produced executable
*is* redistributed. That is precisely what the bundling exception covers, and the exception's
conditions (do not restrict reverse-engineering, make the bootloader source available) are
satisfied trivially by a GPL-3.0-or-later project that ships its Corresponding Source.

---

## 7. Present in the dev environment but NOT dependencies

The conda env `pds` also hosts the *exploration* side-quest (Kaggle corpus analysis, ETH
harvesting). Those packages are **not** tta dependencies and must not appear in
`THIRD_PARTY_LICENSES.txt`. Recorded here so a future audit does not mistake `pip list` for the
dependency set:

`pandas`, `seaborn`, `scipy`, `numba`, `llvmlite`, `kagglehub`, `kagglesdk`, `requests`, `urllib3`,
`certifi`, `charset-normalizer`, `idna`, `protobuf`, `PyYAML`, `bleach`, `webencodings`,
`python-slugify`, `text-unidecode`, `crccheck`, `fastcrc`, `pip`.

One of these is a good illustration of why the distinction matters: **`text-unidecode` is
Artistic-1.0/GPL-dual**, and Artistic-1.0 is *not* GPL-compatible on its own. It arrives via
`python-slugify` ← `kagglehub` — exploration only. If a harvester ever moves into the shipped
product, re-run this audit.

---

## 8. Audit findings

Seven items where a one-word verdict would be dishonest. F1–F4 are licence reasoning; F5–F7 are
defects this audit surfaced and which belong to other issues.

**F1 — `langdetect`'s declared licence is wrong upstream.** Its wheel metadata says
`License: MIT`, but its classifier says Apache Software License and the files it ships are
`LICENSE` (Apache-2.0, Michal Danilak 2014–2015) and `NOTICE` (Apache-2.0, Cybozu Labs 2010–2014,
for the `language-detection` upstream). **The correct licence is Apache-2.0.** Both are compatible,
so nothing is blocked — but a `THIRD_PARTY_LICENSES.txt` generator that reads the `License`
metadata field will print "MIT" and attach no Apache-2.0 `NOTICE`, which *would* be a compliance
defect (Apache-2.0 §4(d) requires the NOTICE to travel). **Action for #4:** prefer shipping the
`.dist-info/licenses/*` files verbatim over trusting metadata strings.

**F2 — `pymupdf` is AGPL-3.0, and that is fine.** GPLv3 §13 expressly permits combining a GPLv3
work with an AGPLv3-licensed part; the combined work conveys under GPL-3.0-or-later, with AGPLv3
§13's remote-interaction duty attaching to the PyMuPDF portion. The app is offline by design
(SDD §2.3, US-ALL-OFFLINE), so §13 never triggers. Already decided in ADR-0017; recorded here so
the audit is self-contained. The Artifex commercial alternative is not needed and not purchased.

**F3 — `pyphen`'s tri-licence requires an explicit election.** GPL-2.0+/LGPL-2.1+/MPL-1.1 — and
**MPL-1.1 alone is GPL-incompatible**. The project therefore **elects GPL-2.0-or-later** for pyphen
and its bundled dictionaries, which reaches GPL-3.0-or-later via "or later". `THIRD_PARTY_LICENSES.txt`
should reproduce pyphen's `COPYING.GPL` (and may include the others, since they were offered), and
this election should be stated in it. The `hyph_de_*.dic` files are separately LGPL-2-or-later over
LPPL-licensed TeX patterns — also compatible.

**F4 — `regex` carries a CNRI-Python-licensed remnant.** Its `LICENSE.txt` opens: "This work was
derived from the 're' module of CPython 2.6 and CPython 3.1 … licensed under CNRI's Python 1.6
license. All additions and alterations are licensed under the Apache 2.0 License." The FSF
considers the *bare* CNRI licence (Python 1.6b1) GPL-incompatible because of its Virginia
choice-of-law clause, which is why SPDX distinguishes `CNRI-Python` from
`CNRI-Python-GPL-Compatible`. The derived code here descends from CPython 2.6/3.1, i.e. from after
the CNRI rider and the PSF relicensing that made the CPython chain GPL-compatible; CPython has been
redistributed inside GPL programs on that basis for two decades. **Verdict: compatible** — but this
is the single item whose verdict rests on that rider rather than on plain licence text. Mitigation
if it is ever challenged: `regex` is a *transitive* NLTK dependency, nothing under `tta/` imports
it (every module uses stdlib `re`), and the NLTK code paths this project exercises — punkt sentence
segmentation and Treebank word tokenisation — do not import it either.

**F5 — the `pymupdf` extra misdescribes reality (packaging, #4).** `pyproject.toml` still comments
that PyMuPDF is a "development-phase extractor only" and that "the release gate … fails any
distributed build that imports it under `tta/core/`". ADR-0017 retired that gate, and the release
job installs `.[build,pymupdf]` and lists `fitz` in `hiddenimports`. The comment is stale and the
default extractor's library is not in the default dependency set. Not this lane's file to fix.

**F6 — the bundled punkt models carry no licence statement.** `nltk_data/tokenizers/punkt_tab/`
ships a README with provenance and a citation, and no licence; there is no licence file anywhere in
the `nltk_data` tree. The `nltk` *package* is Apache-2.0, and the NLTK project has distributed these
models since 2006. The models are derived statistics (abbreviation lists, collocation counts), not
corpus text, so redistributing them does not redistribute the proprietary corpora they were trained
on (Penn Treebank/LDC, the NZZ CD-ROM, etc.). **Verdict: redistributable**, on NLTK's own long-standing
practice rather than on an explicit grant. Cheap hardening available if desired: bundle only
`english` and `german` (the only two `mod_tokenize` can load) instead of all 19 — smaller binary,
narrower claim.

**F7 — CMUdict was a real, unbundled, network-reaching dependency. RESOLVED by #75.**
`textstat.backend.utils._get_cmudict` does, for any English text:

```python
try:
    nltk.data.find("corpora/cmudict")
except LookupError:
    nltk.download('cmudict', quiet=True)
return nltk.corpus.cmudict.dict()
```

`packaging/tta.spec` bundles only `punkt_tab`; CI runs only `python -m nltk.downloader punkt_tab`;
`cmudict` appears nowhere in `packaging/`, `.github/`, `tta/`, or `tests/`. Two consequences, both
verified by running the frozen code path against an `NLTK_DATA` directory containing only
`punkt_tab`:

- **With network:** the binary silently downloads CMUdict from the internet on the first English
  thesis. That contradicts US-ALL-OFFLINE and QA-PRIV, the app's central promise.
- **Without network:** `mod_readability` raises `LookupError: Resource 'cmudict' not found` and
  errors for every English thesis. German is unaffected (it takes the pyphen path).

CI did not catch it at first because the runner had network access, so the download succeeded and
the smoke test passed. It surfaced when `tta doctor`'s offline self-check ran on CI and refused to
let the probe open a socket. **Fixed in #75** exactly as this finding prescribed - `cmudict` added to
`packaging/tta.spec` `datas` and to the
`nltk.downloader` line, and add its BSD-2-Clause notice to `THIRD_PARTY_LICENSES.txt`. Behavioural
consequences for the metric are in [`model-limitations.md`](model-limitations.md) §4.1.

### Summary verdict

**Every component in the distributed set is compatible with GPL-3.0-or-later.** No component needs
to be removed or replaced on licence grounds. Two elections are recorded (pyphen → GPL-2.0-or-later,
freetype → FTL), one obligation is highlighted (Apache-2.0 NOTICE files must travel), and three
defects are handed to their owning issues (F5 → #4; F7 → #75, fixed; F1 → #4).

---

## 9. How to regenerate this page

Run inside the project environment; this is exactly how the tables above were produced.

```bash
# 1. The audited runtime closure (what actually gets frozen).
python - <<'PY'
import importlib.metadata as md
from packaging.requirements import Requirement

def deps(name):
    out = []
    for raw in md.requires(name) or []:
        r = Requirement(raw)
        if r.marker is None or r.marker.evaluate({"extra": ""}):
            out.append(r.name)
    return out

seen, stack = {}, ["langdetect", "nltk", "textstat", "pypdf", "click",
                   "rich", "tomli-w", "tksheet", "pymupdf"]
while stack:
    n = stack.pop()
    if n.lower() in seen:
        continue
    d = md.distribution(n)
    m = d.metadata
    seen[n.lower()] = (d.version,
                       m.get("License-Expression") or (m.get("License") or "").splitlines()[:1],
                       [c for c in (m.get_all("Classifier") or []) if c.startswith("License")])
    stack += deps(n)
for k in sorted(seen):
    print(k, *seen[k], sep="\t")
PY

# 2. The licence files each wheel really ships -- authoritative, unlike the
#    metadata strings (finding F1).
python - <<'PY'
import importlib.metadata as md
for n in ("langdetect", "pyphen", "regex", "tqdm", "pymupdf"):
    d = md.distribution(n)
    print(n, [str(f) for f in (d.files or [])
              if any(k in str(f).upper() for k in ("LICEN", "COPYING", "NOTICE"))])
PY

# 3. Bundled data and vendored native libraries.
python -c "import nltk; print(nltk.data.find('tokenizers/punkt_tab'))"
python -c "import pyphen, os; print(len(os.listdir(os.path.dirname(pyphen.LANGUAGES['de']))))"
python -c "import sysconfig, os; sp=sysconfig.get_paths()['purelib']; print(os.listdir(sp+'/numpy.libs'))"
python -c "import sys, sqlite3, tkinter; print(sys.version, sqlite3.sqlite_version, tkinter.TkVersion)"
```

---

## 10. Revisit when

- A dependency is added, removed, or changes licence — **including a transitive one**; F1/F3/F4 all
  live in the transitive layer.
- Any **word-list-based** metric is added. ADR-0017 flags this specifically: word lists and
  lexicons routinely carry non-commercial or bespoke terms that fail the §1 test even when the code
  around them is MIT.
- A **local language model** is added (issue #44, SDD §12). Model *weights* are licensed separately
  from the inference code, and several popular licences (Llama Community, RAIL, CC-BY-NC) impose
  field-of-use restrictions that are incompatible with GPL-3.0-or-later.
- A harvester or any network component enters the shipped product — see the `text-unidecode` note in
  [§7](#7-present-in-the-dev-environment-but-not-dependencies).
- Before every tagged release: re-run [§9](#9-how-to-regenerate-this-page) and diff, since
  `THIRD_PARTY_LICENSES.txt` must match what the binary actually contains.
