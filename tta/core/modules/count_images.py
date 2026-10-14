"""`mod_count_images` - catalogue #9 (SDD Sec. 7.1, 7.4).

Counts images from the PDF structure via pypdf's object model and never
decodes one (#85): per page, the distinct image XObjects reachable from the
page's resources (recursing into Form XObjects) plus the inline images
(`BI ... ID ... EI`) in the page content and in every Form XObject walked.
Only content streams are decompressed; image data is skipped, so neither
Pillow nor pypdf's image-decoding path (`page.images`, `_xobj_to_image`) is
ever touched.

A POC for smarter figure analysis (SDD Sec. 12): fragments are not
clustered, so vector-heavy theses under-count and tiled rasters over-count.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, StreamObject

from tta.core.i18n import N_
from tta.core.modules.base import Applicability, Module, ModuleSpec, RunContext, RunResult
from tta.core.types import Thesis

# PDF lexical classes (ISO 32000-1, 7.2.2). Regex fragments (raw bytes, the
# regex engine resolves the escapes) and the plain byte set.
_WS = rb"\x00\t\n\x0c\r "
_WS_BYTES = b"\x00\t\n\x0c\r "
_DELIM = rb"()<>\[\]{}/%"
# A token boundary before an operator: start, whitespace or a closing
# delimiter -- not `/`, which would make the letters part of a name.
_BEFORE = rb"(?<![^" + _WS + rb")>\]}])"
_AFTER = rb"(?![^" + _WS + _DELIM + rb"])"
_BI = _BEFORE + rb"BI" + _AFTER
_BI_CANDIDATE = re.compile(_BI)
# Careful scan: string literal start, comment start, or a `BI` operator.
_SCAN = re.compile(rb"[(%]|" + _BI)
# Inside an inline-image dictionary: string literal, comment, or `ID` plus
# the single whitespace byte that separates it from the image data.
_ID_SCAN = re.compile(rb"[(%]|" + _BEFORE + rb"ID[" + _WS + rb"]")
# End of inline-image data: a whitespace-delimited `EI`.
_EI = re.compile(rb"[" + _WS + rb"]EI" + _AFTER)
_STRING_SPECIAL = re.compile(rb"[()\\]")
_EOL = re.compile(rb"[\r\n]")
_LENGTH = re.compile(rb"/L(?:ength)?[" + _WS + rb"]+(\d+)")


def _skip_string(data: bytes, pos: int) -> int:
    """Return the index after the literal string whose `(` ends at `pos`."""
    depth = 1
    while True:
        m = _STRING_SPECIAL.search(data, pos)
        if m is None:
            return len(data)
        ch = m.group()
        pos = m.end()
        if ch == b"\\":
            pos += 1
        elif ch == b"(":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return pos


def _skip_comment(data: bytes, pos: int) -> int:
    m = _EOL.search(data, pos)
    return len(data) if m is None else m.end()


def _skip_inline_image(data: bytes, pos: int) -> tuple[bool, int]:
    """Skip the inline image whose `BI` ends at `pos`, without decoding it.

    Returns (an `ID` was found, index after the image). The data after `ID`
    is skipped by its `/L`/`/Length` when that lands on `EI`, else up to the
    next whitespace-delimited `EI`.
    """
    dict_start = pos
    while True:
        m = _ID_SCAN.search(data, pos)
        if m is None:
            return False, len(data)
        tok = m.group()
        if tok == b"(":
            pos = _skip_string(data, m.end())
        elif tok == b"%":
            pos = _skip_comment(data, m.end())
        else:
            break
    data_start = m.end()
    length = _LENGTH.search(data, dict_start, m.start())
    if length is not None:
        j = data_start + int(length.group(1))
        limit = min(len(data), j + 64)
        while j < limit and data[j] in _WS_BYTES:
            j += 1
        if data.startswith(b"EI", j):
            return True, j + 2
    ei = _EI.search(data, data_start)
    return True, (len(data) if ei is None else ei.end())


def count_inline_images(data: bytes) -> int:
    """Count `BI ... ID ... EI` inline images in a decompressed content stream.

    Byte-level, not pypdf's `ContentStream` parser: a cheap regex pre-check
    rejects content without a candidate `BI` token; otherwise strings and
    comments are skipped (so `(BI)` shown as text never counts) and each
    image's data is skipped, never decoded.
    """
    if _BI_CANDIDATE.search(data) is None:
        return 0
    n = 0
    pos = 0
    while True:
        m = _SCAN.search(data, pos)
        if m is None:
            return n
        tok = m.group()
        if tok == b"(":
            pos = _skip_string(data, m.end())
        elif tok == b"%":
            pos = _skip_comment(data, m.end())
        else:
            found, pos = _skip_inline_image(data, m.end())
            if found:
                n += 1


def _resolve(obj: Any) -> Any:
    return None if obj is None else obj.get_object()


def _content_bytes(contents: Any) -> bytes:
    """Decompressed bytes of a `/Contents` entry (a stream or an array of them)."""
    contents = _resolve(contents)
    if isinstance(contents, StreamObject):
        return contents.get_data()
    if isinstance(contents, ArrayObject):
        parts = []
        for item in contents:
            item = _resolve(item)
            if isinstance(item, StreamObject):
                parts.append(item.get_data())
        return b"\n".join(parts)
    return b""


def _key(obj: Any) -> Any:
    """Identity of a PDF object: its indirect reference (streams always have one)."""
    ref = getattr(obj, "indirect_reference", None)
    return (ref.idnum, ref.generation) if ref is not None else id(obj)


class _Counter:
    """Per-document walk; caches each Form XObject's own inline-image count."""

    def __init__(self) -> None:
        self._form_inline: dict[Any, int] = {}

    def count_page(self, page: DictionaryObject) -> int:
        images: set[Any] = set()
        forms: set[Any] = set()
        inline = count_inline_images(_content_bytes(page.get("/Contents")))
        inline += self._walk(page, images, forms)
        return len(images) + inline

    def _walk(self, owner: DictionaryObject, images: set[Any], forms: set[Any]) -> int:
        """Add the image XObjects reachable from `owner`'s resources to `images`.

        Recurses into Form XObjects not yet in `forms` (the per-page visited
        set, which also ends cycles) and returns their inline-image count.
        """
        resources = _resolve(owner.get("/Resources"))
        if not isinstance(resources, DictionaryObject):
            return 0
        xobjects = _resolve(resources.get("/XObject"))
        if not isinstance(xobjects, DictionaryObject):
            return 0
        inline = 0
        for name in list(xobjects.keys()):
            xobj = _resolve(xobjects.get(name))
            if not isinstance(xobj, StreamObject):
                continue
            subtype = xobj.get("/Subtype")
            key = _key(xobj)
            if subtype == "/Image":
                images.add(key)
            elif subtype == "/Form" and key not in forms:
                forms.add(key)
                inline += self._form_inline_count(xobj, key)
                inline += self._walk(xobj, images, forms)
        return inline

    def _form_inline_count(self, form: StreamObject, key: Any) -> int:
        cached = self._form_inline.get(key)
        if cached is None:
            cached = count_inline_images(form.get_data())
            self._form_inline[key] = cached
        return cached


def count_images(path: str) -> int:
    """`n_images` for the PDF at `path` (counting rule: SDD Sec. 7.1, 7.4)."""
    reader = PdfReader(path)
    counter = _Counter()
    return sum(counter.count_page(page) for page in reader.pages)


class CountImages(Module):
    spec = ModuleSpec(
        name="mod_count_images",
        version="0.2.0",
        produces_metrics=("n_images",),
    )

    def applicable(self, thesis: Thesis) -> Applicability:
        if Path(thesis.pdf_path).suffix.lower() != ".pdf":
            return Applicability(ok=False, reason=N_("not a PDF"))
        return Applicability(ok=True)

    def run(self, ctx: RunContext) -> RunResult:
        return RunResult(metrics={"n_images": count_images(ctx.thesis.pdf_path)})
