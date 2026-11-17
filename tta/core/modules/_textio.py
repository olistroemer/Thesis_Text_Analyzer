"""The one writer for text and JSON artefacts (SDD Sec. 6.4 "Encoding rule", #95).

A PDF text layer or Info dict can yield *lone surrogates* - code points in
U+D800..U+DFFF without a partner, e.g. ``\\udc5b``. Python strings hold them,
strict UTF-8 cannot encode them, so ``write_text(..., encoding="utf-8")``
raised ``UnicodeEncodeError`` and the module ended in ``error``. The rule:
replace every lone surrogate with U+FFFD in the final string, right before
it is written, and report how many were replaced.

A Python ``str`` stores a non-BMP character as one code point, never as a
surrogate pair, so every code point in the surrogate range is lone by
definition.
"""

from __future__ import annotations

import re
from pathlib import Path

REPLACEMENT_CHARACTER = "\ufffd"

_SURROGATE_RE = re.compile("[\ud800-\udfff]")


def replace_lone_surrogates(text: str) -> tuple[str, int]:
    """``text`` with every lone surrogate replaced by U+FFFD, and the count."""
    return _SURROGATE_RE.subn(REPLACEMENT_CHARACTER, text)


def write_text_artefact(path: Path, text: str) -> int:
    """Write ``text`` as UTF-8 under the encoding rule; returns the number of
    lone surrogates replaced (the module's ``surrogates_replaced`` diagnostic)."""
    clean, replaced = replace_lone_surrogates(text)
    path.write_text(clean, encoding="utf-8")
    return replaced
