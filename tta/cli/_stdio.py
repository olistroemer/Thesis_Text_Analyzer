"""What the CLI's text streams must survive on Windows (ADR-0003 output rules).

Kept out of ``tta.cli.main`` so the catalogue's source references there stay
put (ADR-0020); nothing in here is user-facing text.
"""

from __future__ import annotations

import codecs
import csv
import io
import sys


def replace_unencodable_output() -> None:
    """Never let printing a character abort a command.

    A console on Windows takes any text (Python writes it as UTF-16), but a
    redirected or piped stdout there is encoded in the ANSI code page (cp1252
    on a German or English install), with CPython's Windows default error
    handler "surrogateescape" - which, like "strict", raises for a real
    character the code page lacks. A thesis whose file name holds one (a
    Polish "L with stroke", say) made `tta list` die with UnicodeEncodeError
    (exit 70) half-way through the table, and `--format csv` with it. On such
    a stream those characters are now replaced with "?". UTF-8 streams (every
    POSIX desktop, a Windows console, PYTHONUTF8=1) can encode any text and
    are left alone, as is stderr's backslashreplace. JSON output is unaffected
    either way: it is ASCII-escaped, which is what makes it the lossless
    scripting contract.
    """
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        if codecs.lookup(stream.encoding).name == "utf-8":
            continue
        if stream.errors in ("strict", "surrogateescape"):
            stream.reconfigure(errors="replace")


def write_csv_rows(stream, rows, fieldnames) -> None:
    """``rows`` as CSV with RFC 4180 "\\r\\n" row ends on every OS.

    csv ends every row with its own "\\r\\n" (as the profiling export file
    does). Handed a text-mode stdout that translates "\\n" - the Windows
    default - that came out as "\\r\\r\\n", so the rows are rendered first and
    written to the byte stream untranslated, in the text stream's own
    encoding and error policy.
    """
    rendered = io.StringIO(newline="")
    writer = csv.DictWriter(rendered, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    stream.flush()
    stream.buffer.write(rendered.getvalue().encode(stream.encoding, stream.errors))
    stream.buffer.flush()
