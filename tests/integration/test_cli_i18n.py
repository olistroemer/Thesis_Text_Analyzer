"""The CLI's rendered help really is German under `de` (#29, ADR-0020).

This file exists because a catalogue-contents test was not enough. The `de`
catalogue was complete and every gate was green while `tta --help` still came
up half-German: click takes a command's help from the function **docstring**,
a docstring cannot be wrapped in `_()`, and 20 commands were getting their
help that way. The catalogue was right; nothing rendered it.

So the assertions here are on what the process actually prints, in a
subprocess with `TTA_LOCALE=de` - and structurally over the whole command
tree, so a command added later cannot quietly go back to its docstring.

The subprocess is not incidental. `help=_(...)` on a decorator resolves when
`tta.cli.main` is imported, so the locale has to be set before the import -
which this process, running under `TTA_LOCALE=en`, cannot undo.
"""

import gettext
import os
import re
import subprocess
import sys
from pathlib import Path

import click
import pytest

from tta.cli.main import cli
from tta.core import i18n

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Internal cross-references that belong in a developer docstring and must
#: never reach a professor's terminal.
INTERNAL_REFERENCE = re.compile(r"#\d+|ADR-\d|Sec\. \d|US-[A-Z]{2,}|QA-[A-Z]{2,}")


def commands():
    """(dotted name, Command) for the whole tree, root group included."""

    def walk(command, path=()):
        full = path + (command.name,)
        yield " ".join(full), command
        if isinstance(command, click.Group):
            for sub in command.commands.values():
                yield from walk(sub, full)

    return list(walk(cli))


COMMANDS = commands()
IDS = [name for name, _command in COMMANDS]


def top_level():
    """The commands the root `tta --help` listing shows.

    By DEPTH, not by "the name has no space in it": every name here is
    prefixed with the root group, so `tta doctor` has a space and that test
    silently skipped the entire tree.
    """
    return [(name, command) for name, command in COMMANDS if len(name.split()) == 2]


@pytest.fixture(scope="module")
def german():
    """The `de` catalogue, read straight off disk.

    Not `i18n.install("de")`: the point is to compare what the CLI rendered
    against the catalogue independently of this process's active locale.
    """
    with i18n.catalog_path("de").open("rb") as handle:
        return gettext.GNUTranslations(handle)


def run_cli(*args, locale="de"):
    """`python -m tta.cli.main ...` in a subprocess under one locale."""
    # The pipe's encoding is pinned on both ends. Left alone, the child picks
    # the locale's codec (cp1252 on Windows) or whatever PYTHONIOENCODING the
    # developer exports, and text=True decodes with the locale's - two
    # independent choices that disagree as soon as one of them is UTF-8.
    env = dict(os.environ, TTA_LOCALE=locale, PYTHONPATH=str(REPO_ROOT),
               PYTHONIOENCODING="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "tta.cli.main", *args],
        capture_output=True,
        encoding="utf-8",
        check=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    return completed.stdout


# -- what the process actually prints -----------------------------------------


def test_the_command_list_is_german(german):
    """The defect, pinned. `tta --help` is the most visible text the CLI has,
    and every line of the Commands: block used to be English."""
    rendered = " ".join(run_cli("--help").split())
    listed = top_level()
    assert len(listed) >= 13, "the root listing lost commands: %r" % (listed,)
    for name, command in listed:
        english = command.get_short_help_str(limit=200)
        if not english:
            continue
        translated = german.gettext(english)
        assert translated != english, "%s has no German short help" % name
        # click truncates the list line, so match on a leading slice that is
        # still long enough to be unambiguous
        head = " ".join(translated.split())[:40]
        assert head in rendered, "%s renders %r, not the German" % (name, head)


def test_no_english_command_help_survives_in_the_command_list():
    """The complement: a half-translated listing must fail even if the German
    lines above are all present."""
    rendered = " ".join(run_cli("--help").split())
    leaked = []
    for name, command in top_level():
        english = " ".join(command.get_short_help_str(limit=200).split())[:40]
        if english and english in rendered:
            leaked.append((name, english))
    assert leaked == [], leaked


@pytest.mark.parametrize(
    "argv, expected",
    [
        (("doctor", "--help"), "Diagnosedaten f"),
        (("remove", "--help"), "vollst"),
        (("export", "--help"), "Forschungsexport"),
        (("db", "--help"), "Projektdatenbank"),
        (("privacy", "report", "--help"), "Datenschutzerkl"),
    ],
)
def test_each_commands_own_help_page_is_german(argv, expected):
    """A group's help page and a leaf's multi-paragraph body, not just the
    one-line summary in the parent's listing."""
    rendered = run_cli(*argv)
    assert expected in rendered, rendered


def test_the_help_page_of_a_leaf_keeps_both_paragraphs():
    """The long form is the part `short_help` does not cover; if only the
    summary were translated this would still be English."""
    rendered = " ".join(run_cli("remove", "--help").split())
    assert "Die st" in rendered  # "Die staerkere Form von `exclude`"
    assert "PDF-Quelldatei wird nie angetastet" in rendered


def test_english_is_still_selectable_end_to_end():
    """`en` resolves to the msgids, so the same invocation comes out English."""
    rendered = run_cli("--help", locale="en")
    assert "Create, migrate or compact the project database." in rendered
    assert "Projektdatenbank" not in rendered


# -- structurally, over the whole tree ----------------------------------------


@pytest.mark.parametrize("name, command", COMMANDS, ids=IDS)
def test_every_command_has_explicit_help_not_its_docstring(name, command):
    """The root cause, guarded. A command whose help comes from `__doc__` is a
    command that cannot be translated at all."""
    docstring = (command.callback.__doc__ or "") if command.callback else ""
    assert command.help, "%s has no help at all" % name
    assert command.help.strip() != docstring.strip(), (
        "%s takes its help from the docstring - pass help=_(...) on the "
        "decorator instead (ADR-0020)" % name
    )


@pytest.mark.parametrize("name, command", COMMANDS, ids=IDS)
def test_every_commands_help_is_in_the_german_catalogue(name, command, german):
    """Covers `short_help` too, which the rendered-output tests above can only
    see for top-level commands."""
    for label, text in (("help", command.help), ("short_help", command.short_help)):
        if not text:
            continue
        translated = german.gettext(text)
        assert translated != text, "%s %s is not translated: %r" % (name, label, text)
        assert translated.strip(), "%s %s translates to nothing" % (name, label)


@pytest.mark.parametrize("name, command", COMMANDS, ids=IDS)
def test_no_internal_reference_reaches_the_user(name, command, german):
    """`doctor` used to advertise "(#42, ADR-0003)" to a professor, because its
    help *was* its docstring. The docstring is the right home for that; the
    user-facing help is not - in either locale."""
    for label, text in (("help", command.help), ("short_help", command.short_help)):
        if not text:
            continue
        for rendered, tongue in ((text, "en"), (german.gettext(text), "de")):
            found = INTERNAL_REFERENCE.search(rendered)
            assert found is None, "%s %s (%s) leaks %r" % (
                name, label, tongue, found.group(0),
            )


@pytest.mark.parametrize("name, command", COMMANDS, ids=IDS)
def test_every_option_help_is_translated(name, command, german):
    """The same rule for option help, which was already wrapped - so this is a
    regression guard rather than a fix."""
    for parameter in command.params:
        text = getattr(parameter, "help", None)
        if not text:
            continue
        assert german.gettext(text) != text, "%s %s: %r" % (
            name, parameter.name, text,
        )


def test_the_developer_docstrings_are_still_there():
    """The fix is additive: the cross-references stay where a maintainer looks
    for them. If a later change "tidies up" by deleting the docstrings, the
    reasoning behind `doctor` and `remove` goes with them."""
    from tta.cli.main import doctor, remove

    assert "ADR-0003" in (doctor.callback.__doc__ or "")
    assert "#63" in (remove.callback.__doc__ or "")


# -- the accepted limitation --------------------------------------------------


def test_clicks_own_chrome_is_still_english():
    """A KNOWN, accepted limitation (ADR-0020), asserted so it stays visible
    and deliberate rather than looking like an oversight.

    "Usage:", "Options:", "Commands:" and the --help option's own description
    come from click's formatter, not from us. Overriding them means
    subclassing click's HelpFormatter and Context and re-implementing its
    layout - out of scope for the MVP. If this test ever fails because the
    chrome IS German, delete it and the ADR's limitation note together.
    """
    rendered = run_cli("--help")
    assert "Usage:" in rendered
    assert "Options:" in rendered
    assert "Commands:" in rendered
    assert "Show this message and exit." in rendered
