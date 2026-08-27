"""The shipped catalogs, and the gates that stop them drifting (#28, ADR-0020).

Both the `.po` and the compiled `.mo` are committed, because gettext needs the
`.mo` at run time and a from-source checkout has no build step to make one -
and a missing `.mo` fails *silently*, so a German-first application would just
come up in English. The price of committing a binary is drift, and these tests
are how that price is paid: the `.mo` is recompiled into memory and
**byte-compared** with the committed file, so a `.po` edit without a recompile
fails here instead of shipping.
"""

import gettext
import importlib.util
import pathlib
import sys

import pytest

from tta.core import i18n

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCALE_ROOT = REPO_ROOT / "tta" / "locale"
COMPILER_PATH = REPO_ROOT / "packaging" / "compile_catalogs.py"
CATALOG_PATH = REPO_ROOT / "packaging" / "pocatalog.py"


def _load_script(path, name):
    """Load a packaging script by path (see tests/packaging/conftest.py)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: a dataclass resolves its annotations through
    # sys.modules[cls.__module__], which is None for a module loaded purely
    # from a spec.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def compiler():
    return _load_script(COMPILER_PATH, "tta_compile_catalogs")


@pytest.fixture(scope="session")
def pocatalog():
    return _load_script(CATALOG_PATH, "tta_pocatalog")


def po_paths():
    return sorted(LOCALE_ROOT.glob("*/LC_MESSAGES/tta.po"))


def _read(pocatalog, path):
    return pocatalog.read_po(path.read_text(encoding="utf-8"), origin=str(path))


# -- the German catalog exists and is the default -----------------------------


def test_the_german_catalog_ships():
    """SDD Sec. 9.6 makes `de` the locale a professor gets on first run, so its
    compiled catalog is not optional."""
    assert (LOCALE_ROOT / "de" / "LC_MESSAGES" / "tta.po").is_file()
    assert (LOCALE_ROOT / "de" / "LC_MESSAGES" / "tta.mo").is_file()


def test_german_is_what_you_get_with_nothing_configured():
    """The end-to-end version of the default: no config, no env var, German UI."""
    assert i18n.resolve_locale(None, env={}) == "de"
    try:
        i18n.install(config_locale=None, env={})
        assert i18n.active_locale() == "de"
        assert i18n._("Run all") != "Run all", "the de catalog did not load"
        assert i18n._("Run all") == "Alle analysieren"
    finally:
        i18n.install("en")


def test_both_locales_are_selectable():
    assert i18n.available_locales() == ("de", "en")


def test_the_compiled_catalog_loads_through_stdlib_gettext():
    """Read with ``gettext`` itself, not with our own reader - the point of
    committing a `.mo` is that the stdlib can open it."""
    with i18n.catalog_path("de").open("rb") as handle:
        translation = gettext.GNUTranslations(handle)
    assert translation.gettext("Ready") == "Bereit"
    assert translation.info()["language"] == "de"


# -- the gates ----------------------------------------------------------------


@pytest.mark.parametrize("path", po_paths(), ids=lambda p: p.parent.parent.name)
def test_the_committed_mo_matches_its_po(compiler, path, tmp_path):
    """Recompile and byte-compare. This is what stops the committed binary
    from drifting away from the source a translator actually edits."""
    target = path.with_suffix(".mo")
    recompiled = compiler.compile_po(path)
    scratch = tmp_path / "tta.mo"
    scratch.write_bytes(recompiled)
    assert target.read_bytes() == scratch.read_bytes(), (
        "%s is stale - run: python packaging/compile_catalogs.py" % target.name
    )


@pytest.mark.parametrize("path", po_paths(), ids=lambda p: p.parent.parent.name)
def test_the_compiler_is_deterministic(compiler, path):
    assert compiler.compile_po(path) == compiler.compile_po(path)


@pytest.mark.parametrize("path", po_paths(), ids=lambda p: p.parent.parent.name)
def test_no_message_is_left_untranslated(pocatalog, path):
    """A partial catalog is a UI that mixes languages sentence by sentence.
    Better to fail the build than to ship one."""
    missing = _read(pocatalog, path).untranslated()
    assert missing == [], "%d untranslated msgids in %s: %r" % (
        len(missing), path.parent.parent.name, missing[:5],
    )


@pytest.mark.parametrize("path", po_paths(), ids=lambda p: p.parent.parent.name)
def test_placeholders_survive_translation(pocatalog, path):
    """A dropped or renamed ``{path}`` is a KeyError at render time, in the
    locale nobody on the team reads first."""
    bad = pocatalog.placeholder_mismatches(_read(pocatalog, path))
    assert bad == [], bad


@pytest.mark.parametrize("path", po_paths(), ids=lambda p: p.parent.parent.name)
def test_the_catalog_covers_exactly_the_template(pocatalog, path):
    """No msgid the source has lost, none it has gained. An obsolete msgstr
    makes the untranslated count above lie."""
    template = _read(pocatalog, LOCALE_ROOT / "tta.pot")
    catalog = _read(pocatalog, path)
    assert set(catalog.entries) == set(template.entries), (
        "run: python packaging/extract_messages.py --update"
    )


@pytest.mark.parametrize("path", po_paths(), ids=lambda p: p.parent.parent.name)
def test_the_catalog_declares_its_language_and_utf8(pocatalog, path):
    header = _read(pocatalog, path).header
    assert "Language: %s\n" % path.parent.parent.name in header
    assert "charset=UTF-8" in header


def test_the_catalogs_are_where_the_loader_looks():
    """The layout is a contract between the compiler, the loader, the
    PyInstaller spec and pyproject's package-data."""
    for path in po_paths():
        locale = path.parent.parent.name
        assert str(i18n.catalog_path(locale)).endswith(
            "%s/LC_MESSAGES/tta.mo" % locale
        )


# -- ADR-0018: the German lives in data, never in source ----------------------


def test_the_translations_really_are_non_ascii(pocatalog):
    """The whole reason the catalogs exist as data files: German needs umlauts,
    and ADR-0018 forbids them in *.py. If this passed with pure-ASCII msgstrs
    somebody had transliterated the German instead of translating it."""
    catalog = _read(pocatalog, LOCALE_ROOT / "de" / "LC_MESSAGES" / "tta.po")
    non_ascii = [e for e in catalog.sorted_entries() if not e.msgstr.isascii()]
    assert len(non_ascii) > 20, "suspiciously little non-ASCII in the de catalog"


def test_every_msgid_is_ascii(pocatalog):
    """The msgids ARE the source strings (ADR-0018)."""
    for path in po_paths() + [LOCALE_ROOT / "tta.pot"]:
        for msgid in _read(pocatalog, path).entries:
            assert msgid.isascii(), (path.name, msgid)


# -- the reader is strict on purpose ------------------------------------------


def test_the_reader_rejects_plural_forms(pocatalog):
    """ADR-0020 does not support plurals, so a msgid_plural must be an error
    rather than a message that is silently dropped from the catalog."""
    text = 'msgid ""\nmsgstr "Language: de\\n"\n\nmsgid "x"\nmsgid_plural "xs"\nmsgstr[0] "y"\n'
    with pytest.raises(pocatalog.CatalogError, match="msgid_plural"):
        pocatalog.read_po(text)


def test_the_reader_rejects_a_duplicate_msgid(pocatalog):
    text = (
        'msgid ""\nmsgstr "Language: de\\n"\n\n'
        'msgid "x"\nmsgstr "a"\n\nmsgid "x"\nmsgstr "b"\n'
    )
    with pytest.raises(pocatalog.CatalogError, match="duplicate"):
        pocatalog.read_po(text)


def test_a_po_round_trips_through_the_reader_and_writer(pocatalog):
    """The merge step rewrites the .po in place, so a round trip has to be
    lossless or `--update` would corrupt a translator's work."""
    path = LOCALE_ROOT / "de" / "LC_MESSAGES" / "tta.po"
    original = path.read_text(encoding="utf-8")
    catalog = pocatalog.read_po(original, origin=str(path))
    assert pocatalog.write_po(catalog, template=False) == original


def test_an_untranslated_message_is_omitted_from_the_mo(pocatalog):
    """An empty msgstr in a .mo would translate the string to "" and blank the
    UI; msgfmt drops such entries so gettext falls back to the msgid."""
    catalog = pocatalog.Catalog(header="Language: de\n")
    catalog.entries["translated"] = pocatalog.Entry("translated", "uebersetzt")
    catalog.entries["untranslated"] = pocatalog.Entry("untranslated", "")
    payload = pocatalog.write_mo(catalog)
    assert b"translated" in payload
    assert b"untranslated" not in payload
