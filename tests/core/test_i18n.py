"""The i18n foundation: locale resolution, marking, formatting (#29, ADR-0020).

The suite as a whole runs under the English catalog (tests/conftest.py) so
assertions can quote the msgid. This file is where the **German default** is
asserted explicitly, because nothing else does: SDD Sec. 9.6 makes `de` the
locale a professor gets on first run, and that is a product commitment, not
an implementation detail.
"""

import datetime
import importlib.util
import pathlib

import pytest

from tta.core import i18n
from tta.core.config import Config, load_config, save_config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EXTRACTOR_PATH = REPO_ROOT / "packaging" / "extract_messages.py"
POT_PATH = REPO_ROOT / "tta" / "locale" / "tta.pot"


def _load_script(path, name):
    """Load a packaging script by path.

    It cannot be imported as ``packaging.<name>``: the repo's ``packaging/``
    directory is not a Python package and the name collides with the
    third-party ``packaging`` distribution (the same reason
    tests/packaging/conftest.py loads check_build.py this way).
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def extractor():
    return _load_script(EXTRACTOR_PATH, "tta_extract_messages")


# -- locale resolution (ADR-0020) ---------------------------------------------


def test_the_default_locale_is_german():
    """SDD Sec. 9.6: German-first. With nothing configured anywhere, `de`."""
    assert i18n.DEFAULT_LOCALE == "de"
    assert i18n.resolve_locale(None, env={}) == "de"


def test_the_env_var_overrides_the_default():
    assert i18n.resolve_locale(None, env={"TTA_LOCALE": "en"}) == "en"


def test_the_config_overrides_the_env_var():
    """`[ui] locale` in the project's tta.toml is the user's own setting and
    wins over the ambient environment."""
    assert i18n.resolve_locale("en", env={"TTA_LOCALE": "de"}) == "en"
    assert i18n.resolve_locale("de", env={"TTA_LOCALE": "en"}) == "de"


def test_the_os_locale_is_never_consulted(monkeypatch):
    """ADR-0020's most deliberate decision.

    A German professor on English-locale Windows - which German institutional
    IT commonly ships - must still get the German UI. Asserted by setting every
    variable the stdlib's locale machinery reads and checking nothing moves.
    """
    for name in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.setenv(name, "en_US.UTF-8")
    assert i18n.resolve_locale(None, env={}) == "de"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("de", "de"),
        ("DE", "de"),
        ("de_DE", "de"),
        ("de-DE", "de"),
        ("de_DE.UTF-8", "de"),
        ("  en  ", "en"),
        ("fr", None),          # not offered
        ("", None),
        ("nonsense", None),
        (None, None),
        (7, None),             # a hand-edited tta.toml can hold anything
        (True, None),
    ],
)
def test_locale_tags_are_normalised_and_unsupported_ones_rejected(value, expected):
    assert i18n.normalise_locale(value) == expected


def test_an_unsupported_configured_locale_falls_through_rather_than_raising():
    """A hand edit must not make the application unstartable (ADR-0020)."""
    assert i18n.resolve_locale("klingon", env={"TTA_LOCALE": "en"}) == "en"
    assert i18n.resolve_locale("klingon", env={}) == "de"


def test_install_returns_the_active_locale_and_an_explicit_argument_wins():
    try:
        assert i18n.install("de") == "de"
        assert i18n.active_locale() == "de"
        assert i18n.install("en", config_locale="de") == "en"
        assert i18n.active_locale() == "en"
    finally:
        i18n.install("en")


def test_english_is_selectable_and_needs_no_catalog():
    """ADR-0020: English *is* the msgid set, so it costs no bytes."""
    assert "en" in i18n.SUPPORTED_LOCALES
    assert "en" in i18n.available_locales()
    assert not i18n.catalog_path("en").is_file()


# -- marking -------------------------------------------------------------------


def test_translating_under_english_returns_the_msgid_unchanged():
    i18n.install("en")
    for msgid in ("Ready", "Run all", "Add files", "{count} theses"):
        assert i18n._(msgid) == msgid


def test_an_unknown_msgid_falls_back_to_itself_in_every_locale():
    """The gettext fallback is load-bearing: a parameterised `na` reason has no
    catalog entry and must render as its stored English text, not as blank."""
    for locale in i18n.SUPPORTED_LOCALES:
        i18n.install(locale)
        assert i18n._("unsupported language: it") == "unsupported language: it"
    i18n.install("en")


def test_marking_without_translating_is_the_identity():
    assert i18n.N_("Excluded") == "Excluded"


def test_a_missing_catalog_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.setattr(i18n, "catalog_path", lambda locale: pathlib.Path("/nope/tta.mo"))
    try:
        assert i18n.install("de") == "de"  # still the active locale...
        assert i18n._("Ready") == "Ready"  # ...just untranslated
    finally:
        i18n.install("en")


# -- locale-aware formatting (SDD Sec. 9.6) ------------------------------------


@pytest.mark.parametrize(
    "value, decimals, grouping, en, de",
    [
        (1000, None, False, "1000", "1000"),
        (1000, None, True, "1,000", "1.000"),
        (1234567, 0, True, "1,234,567", "1.234.567"),
        (12.5, None, False, "12.50", "12,50"),
        (12.345, 2, False, "12.35", "12,35"),
        (0.5, 1, False, "0.5", "0,5"),
        (-1234.5, 1, True, "-1,234.5", "-1.234,5"),
        (9000, 0, True, "9,000", "9.000"),
    ],
)
def test_numbers_follow_the_active_locale(value, decimals, grouping, en, de):
    """German uses a decimal comma and a dot for thousands - the single most
    visible locale difference in a grid full of numbers."""
    assert i18n.format_number(value, decimals, grouping=grouping, locale="en") == en
    assert i18n.format_number(value, decimals, grouping=grouping, locale="de") == de


def test_number_formatting_defaults_to_the_installed_locale():
    try:
        i18n.install("de")
        assert i18n.format_number(1234.5) == "1.234,50"
        i18n.install("en")
        assert i18n.format_number(1234.5) == "1,234.50"
    finally:
        i18n.install("en")


def test_integers_never_grow_a_decimal_part():
    assert i18n.format_integer(1500, locale="de") == "1.500"
    assert i18n.format_integer(1500, grouping=False, locale="de") == "1500"


def test_dates_and_times_follow_the_active_locale():
    day = datetime.date(2026, 8, 27)
    moment = datetime.datetime(2026, 8, 27, 9, 5)
    assert i18n.format_date(day, locale="en") == "2026-08-27"
    assert i18n.format_date(day, locale="de") == "27.08.2026"
    assert i18n.format_datetime(moment, locale="en") == "2026-08-27 09:05"
    assert i18n.format_datetime(moment, locale="de") == "27.08.2026 09:05"


# -- the tta.toml key ----------------------------------------------------------


def test_the_locale_round_trips_through_tta_toml(tmp_path):
    save_config(tmp_path, Config(ui_locale="en"))
    assert (tmp_path / "tta.toml").read_text(encoding="utf-8").count('locale = "en"') == 1
    assert load_config(tmp_path).ui_locale == "en"


def test_no_configured_locale_means_resolve_it(tmp_path):
    """Absent, not "de": the env var must still be able to speak (ADR-0020)."""
    save_config(tmp_path, Config())
    assert "locale" not in (tmp_path / "tta.toml").read_text(encoding="utf-8")
    assert load_config(tmp_path).ui_locale is None


def test_a_nonsense_locale_in_tta_toml_is_ignored(tmp_path):
    (tmp_path / "tta.toml").write_text('[ui]\nlocale = "klingon"\n', encoding="utf-8")
    assert load_config(tmp_path).ui_locale is None
    (tmp_path / "tta.toml").write_text("[ui]\nlocale = 7\n", encoding="utf-8")
    assert load_config(tmp_path).ui_locale is None


# -- the template is in step with the source ----------------------------------


def test_the_committed_pot_matches_the_source(extractor):
    """Regenerate and compare (ADR-0020). A wrapped string that never reached
    the template is a string no translator can see, and the failure mode is a
    single English sentence in a German dialog."""
    assert POT_PATH.is_file(), "run: python packaging/extract_messages.py"
    assert POT_PATH.read_text(encoding="utf-8") == extractor.render(), (
        "tta/locale/tta.pot is stale - run: python packaging/extract_messages.py"
    )


def test_the_extractor_is_deterministic(extractor):
    assert extractor.render() == extractor.render()


def test_the_template_carries_no_timestamp(extractor):
    """A POT-Creation-Date would make the byte-compare gate above useless."""
    assert "POT-Creation-Date" not in extractor.render()


def test_the_extractor_only_takes_literals(extractor, tmp_path):
    """A runtime-computed msgid cannot enter the catalog - it would be a
    msgstr lookup that silently misses in production."""
    source = tmp_path / "tta" / "sample.py"
    source.parent.mkdir()
    source.write_text(
        "from tta.core.i18n import N_, _\n"
        "name = 'x'\n"
        "a = _('a literal')\n"
        "b = N_('a marked literal')\n"
        "c = _('implicit ' 'concatenation')\n"
        "d = _('explicit ' + 'concatenation')\n"
        "e = _(f'{name} interpolated')\n"
        "f = _(name)\n"
        "g = _('with a keyword', extra=1)\n"
        "h = gettext('a different callable')\n",
        encoding="utf-8",
    )
    found = [msgid for msgid, _ref in extractor.extract_file(source, tmp_path)]
    assert found == [
        "a literal",
        "a marked literal",
        "implicit concatenation",
        "explicit concatenation",
    ]


def test_the_template_carries_source_references(extractor):
    catalog = extractor.build_catalog()
    entry = catalog.entries["Add files"]
    assert any(reference.startswith("tta/ui/tk/") for reference in entry.references)


def test_every_marked_string_is_ascii(extractor):
    """ADR-0018: the msgids ARE the source strings, so they are ASCII by
    construction. Asserted anyway - a non-ASCII msgid would mean German text
    had leaked into a *.py file."""
    for msgid in extractor.build_catalog().entries:
        assert msgid.isascii(), msgid
