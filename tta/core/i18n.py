"""Runtime translation and locale-aware formatting (SDD Sec. 9.6, ADR-0020).

One ``_()`` for the whole application. It lives in core, not in an adapter,
because core renders user-facing text itself: ``core/report.py`` produces the
entire HTML cohort report and ``core/privacy_metadata.py`` the entire GDPR
statement, and both must come out in the active locale. This does not breach
ADR-0002 - ``gettext`` is stdlib text lookup, not a UI toolkit.

Two marking functions, used for different reasons:

* ``_(msg)`` translates now. Use it at the point of *display*.
* ``N_(msg)`` translates nothing and only marks the literal so the extractor
  finds it. Use it wherever the English text has to stay the stored value -
  ``module_runs.reason`` is persisted AND exported, and a German msgid in the
  database would corrupt the research data set - or wherever the literal is a
  module-level constant evaluated before any locale is resolved.

Locale resolution is ``[ui] locale`` in ``tta.toml`` -> ``TTA_LOCALE`` ->
``de``, and deliberately never the OS locale: German-first is a product
decision, and German institutional IT commonly runs English-locale Windows,
so deriving the UI language from the machine would hand exactly the target
user an English UI (ADR-0020 records the full reasoning).

Source msgids are English and ASCII (ADR-0018). Every translated character
lives in ``tta/locale/<lang>/LC_MESSAGES/tta.mo``, which is data, not source.
"""

from __future__ import annotations

import gettext as _gettext
import os
from datetime import date, datetime
from importlib import resources

#: gettext domain; the catalogs are named after it.
DOMAIN = "tta"

#: SDD Sec. 9.6: German by default.
DEFAULT_LOCALE = "de"

#: The locales the application offers. "en" needs no catalog - English *is*
#: the msgid set, so it resolves to a NullTranslations (ADR-0020).
SUPPORTED_LOCALES = ("de", "en")

LOCALE_ENV_VAR = "TTA_LOCALE"
LOCALE_DIRNAME = "locale"

_translations: _gettext.NullTranslations | None = None
_active_locale: str | None = None


# -- locale resolution --------------------------------------------------------


def normalise_locale(value: object) -> str | None:
    """A supported locale tag from anything a config or env var might hold.

    Accepts "de", "DE", "de_DE", "de-DE", "de_DE.UTF-8". Returns None for
    anything unsupported, so callers can fall through to the next source
    rather than raising: a hand-edited ``tta.toml`` must never make the
    application unstartable.
    """
    if not isinstance(value, str):
        return None
    tag = value.strip().replace("-", "_").split("_")[0].split(".")[0].lower()
    return tag if tag in SUPPORTED_LOCALES else None


def resolve_locale(config_locale: object = None, env: dict | None = None) -> str:
    """``[ui] locale`` -> ``TTA_LOCALE`` -> ``DEFAULT_LOCALE`` (ADR-0020)."""
    environ = os.environ if env is None else env
    for candidate in (config_locale, environ.get(LOCALE_ENV_VAR)):
        tag = normalise_locale(candidate)
        if tag is not None:
            return tag
    return DEFAULT_LOCALE


def locale_root():
    """The installed catalog root (a Traversable, so a frozen build works)."""
    return resources.files("tta") / LOCALE_DIRNAME


def catalog_path(locale: str):
    """``tta/locale/<locale>/LC_MESSAGES/tta.mo`` as a Traversable."""
    return locale_root() / locale / "LC_MESSAGES" / f"{DOMAIN}.mo"


def _load(locale: str) -> _gettext.NullTranslations:
    """Load one compiled catalog, falling back to the msgids.

    The catalog is opened through ``importlib.resources`` rather than handed
    to ``gettext.translation`` as a directory, so no filesystem layout is
    assumed and the frozen single-file build (ADR-0014) needs no special case.
    """
    if locale == "en":
        return _gettext.NullTranslations()  # English is the msgid set
    try:
        with catalog_path(locale).open("rb") as handle:
            return _gettext.GNUTranslations(handle)
    except (OSError, AttributeError, ModuleNotFoundError):
        # Missing, unreadable or corrupt catalog. Falling back to the English
        # msgids is the only sane behaviour; failing to start over a missing
        # translation would be worse than an untranslated UI.
        return _gettext.NullTranslations()


def install(
    locale: str | None = None,
    *,
    config_locale: object = None,
    env: dict | None = None,
) -> str:
    """Make ``locale`` (or the resolved one) active. Returns the active tag.

    An explicit ``locale`` wins over everything - that is the switch a test or
    a ``--locale`` flag would use. Otherwise the ADR-0020 precedence applies.

    Deliberately not ``gettext.install()``: that injects ``_`` into builtins,
    which hides the dependency and shadows the interactive interpreter's ``_``.
    Callers import ``_`` from this module.
    """
    global _translations, _active_locale
    tag = normalise_locale(locale)
    if tag is None:
        tag = resolve_locale(config_locale, env)
    _translations = _load(tag)
    _active_locale = tag
    return tag


def active_locale() -> str:
    """The active locale tag, installing the resolved default on first use."""
    if _active_locale is None:
        install()
    assert _active_locale is not None  # install() always sets it
    return _active_locale


def available_locales() -> tuple[str, ...]:
    """Locales that can actually be selected: ``en`` plus every compiled
    catalog present in the installation."""
    found = ["en"]
    for tag in SUPPORTED_LOCALES:
        if tag != "en" and catalog_path(tag).is_file():
            found.append(tag)
    return tuple(sorted(found))


# -- marking ------------------------------------------------------------------


def _(message: str) -> str:
    """Translate ``message`` into the active locale."""
    if _translations is None:
        install()
    assert _translations is not None
    return _translations.gettext(message)


def N_(message: str) -> str:
    """Mark ``message`` for extraction without translating it (ADR-0020).

    For strings whose English form is the value that gets *stored* (module
    `na` reasons, privacy-registry prose) and for module-level constants
    evaluated before a locale exists. Translate them with ``_()`` at the
    point of display.
    """
    return message


# -- locale-aware formatting (SDD Sec. 9.6) -----------------------------------

#: (decimal separator, thousands separator) per locale. Not CLDR - two
#: locales, one table (ADR-0020 rejects a locale-data dependency).
_NUMBER_SEPARATORS = {"de": (",", "."), "en": (".", ",")}
_DATE_FORMATS = {"de": "%d.%m.%Y", "en": "%Y-%m-%d"}
_TIME_FORMAT = "%H:%M"


def _separators(locale: str | None) -> tuple[str, str]:
    tag = normalise_locale(locale) or active_locale()
    return _NUMBER_SEPARATORS.get(tag, _NUMBER_SEPARATORS["en"])


def format_number(
    value: float,
    decimals: int | None = None,
    *,
    grouping: bool = True,
    locale: str | None = None,
) -> str:
    """A number in the active locale's notation (German: decimal comma).

    ``decimals=None`` means "as many as the value needs": none for a whole
    number, two otherwise - the rule the grid and the report already used
    before they became locale-aware.
    """
    number = float(value)
    if decimals is None:
        decimals = 0 if number == int(number) else 2
    decimal_sep, group_sep = _separators(locale)
    text = f"{number:,.{decimals}f}" if grouping else f"{number:.{decimals}f}"
    # One pass, so the C-locale "," -> group_sep and "." -> decimal_sep
    # substitutions cannot feed into each other.
    return text.translate(str.maketrans({",": group_sep, ".": decimal_sep}))


def format_integer(value: float, *, grouping: bool = True, locale: str | None = None) -> str:
    """A whole number in the active locale's notation."""
    return format_number(value, 0, grouping=grouping, locale=locale)


def format_date(value: date | datetime, locale: str | None = None) -> str:
    """A date in the active locale's notation (German: 27.08.2026)."""
    tag = normalise_locale(locale) or active_locale()
    return value.strftime(_DATE_FORMATS.get(tag, _DATE_FORMATS["en"]))


def format_datetime(value: datetime, locale: str | None = None) -> str:
    """A date and time in the active locale's notation, to the minute."""
    return f"{format_date(value, locale)} {value.strftime(_TIME_FORMAT)}"
