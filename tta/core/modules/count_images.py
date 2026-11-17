"""`mod_count_images` - catalogue #9 (SDD Sec. 7.1, 7.4).

Counts images from the PDF structure via pypdf's object model and never
decodes one (#85): per page, the distinct image XObjects reachable from the
page's resources (recursing into Form XObjects) plus the inline images
(`BI ... ID ... EI`) in the page's own content, each only if both its pixel
sides are at least `MIN_IMAGE_SIDE_PX` (ADR-0021). Only the page content
streams are decompressed; image data is skipped and sizes come from the
image dictionaries, so neither Pillow nor pypdf's image-decoding path
(`page.images`, `_xobj_to_image`) is ever touched.

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
# delimiter -- not `/`, which would make the letters part of a name. Checked
# in Python after a literal-first regex match: a regex lookbehind in front of
# the literal defeats the engine's fast literal search (~50x slower on MBs of
# image data).
_BEFORE_BYTES = _WS_BYTES + b")>]}"
_AFTER = rb"(?![^" + _WS + _DELIM + rb"])"
_BI = re.compile(rb"BI" + _AFTER)
# Careful scan: string literal start, comment start, or a `BI` candidate.
_SCAN = re.compile(rb"[(%]|BI" + _AFTER)
# Inside an inline-image dictionary: string literal, comment, or `ID` plus
# the single whitespace byte that separates it from the image data.
_ID_SCAN = re.compile(rb"[(%]|ID[" + _WS + rb"]")
# End of inline-image data: `EI`, preceded by whitespace (checked in Python).
_EI = re.compile(rb"EI" + _AFTER)
_STRING_SPECIAL = re.compile(rb"[()\\]")
_EOL = re.compile(rb"[\r\n]")
_LENGTH = re.compile(rb"/L(?:ength)?[" + _WS + rb"]+(\d+)")
# Pixel size in an inline-image dictionary: abbreviated or full key names.
_INLINE_W = re.compile(rb"/(?:Width|W)(?![A-Za-z])[" + _WS + rb"]*(\d+)")
_INLINE_H = re.compile(rb"/(?:Height|H)(?![A-Za-z])[" + _WS + rb"]*(\d+)")

# Images with a pixel side below this do not count (ADR-0021, #85): on the
# exp-22 corpus the 1 px spike and its 2 px tail (35.8 % of all counted
# images) were rules, dotted lines, 1x1 masks and 1-2 px slices of logos.
# Deliberately a constant, not a setting.
MIN_IMAGE_SIDE_PX = 3


def _big_enough(width: Any, height: Any) -> bool:
    """True if both sides are integers >= MIN_IMAGE_SIDE_PX (unreadable -> False)."""
    return (isinstance(width, int) and isinstance(height, int)
            and not isinstance(width, bool) and not isinstance(height, bool)
            and width >= MIN_IMAGE_SIDE_PX and height >= MIN_IMAGE_SIDE_PX)


def _at_boundary(data: bytes, start: int) -> bool:
    """True if an operator matched at `start` begins a token."""
    return start == 0 or data[start - 1] in _BEFORE_BYTES


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


def _skip_inline_image(data: bytes, pos: int) -> tuple[int, int]:
    """Skip the inline image whose `BI` ends at `pos`, without decoding it.

    Returns (index of its `ID` operator, i.e. the end of its dictionary, or
    -1 if there is none; index after the image). The data after `ID` is
    skipped by its `/L`/`/Length` when that lands on `EI`, else up to the
    next whitespace-delimited `EI`.
    """
    dict_start = pos
    while True:
        m = _ID_SCAN.search(data, pos)
        if m is None:
            return -1, len(data)
        tok = m.group()
        if tok == b"(":
            pos = _skip_string(data, m.end())
        elif tok == b"%":
            pos = _skip_comment(data, m.end())
        elif _at_boundary(data, m.start()):
            break
        else:
            pos = m.start() + 1
    dict_end = m.start()
    data_start = m.end()
    length = _LENGTH.search(data, dict_start, m.start())
    if length is not None:
        j = data_start + int(length.group(1))
        limit = min(len(data), j + 64)
        while j < limit and data[j] in _WS_BYTES:
            j += 1
        if data.startswith(b"EI", j):
            return dict_end, j + 2
    pos = data_start + 1
    while True:
        ei = _EI.search(data, pos)
        if ei is None:
            return dict_end, len(data)
        if data[ei.start() - 1] in _WS_BYTES:
            return dict_end, ei.end()
        pos = ei.start() + 1


def count_inline_images(data: bytes) -> int:
    """Count `BI ... ID ... EI` inline images in a decompressed content stream.

    Byte-level, not pypdf's `ContentStream` parser: a cheap regex pre-check
    rejects content without a candidate `BI` token; otherwise strings and
    comments are skipped (so `(BI)` shown as text never counts) and each
    image's data is skipped, never decoded. An image counts only if its
    dictionary gives both `/W` and `/H` (or `/Width`, `/Height`) of at least
    MIN_IMAGE_SIDE_PX.
    """
    pos = 0
    while True:  # cheap pre-check: any `BI` operator candidate at all?
        m = _BI.search(data, pos)
        if m is None:
            return 0
        if _at_boundary(data, m.start()):
            break
        pos = m.start() + 1
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
        elif not _at_boundary(data, m.start()):
            pos = m.start() + 1
        else:
            start = m.end()
            dict_end, pos = _skip_inline_image(data, start)
            if dict_end >= 0 and _inline_big_enough(data[start:dict_end]):
                n += 1


def _inline_big_enough(head: bytes) -> bool:
    w = _INLINE_W.search(head)
    h = _INLINE_H.search(head)
    return w is not None and h is not None and _big_enough(int(w.group(1)), int(h.group(1)))


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


def _collect_image_xobjects(owner: DictionaryObject, images: set[Any], forms: set[Any]) -> None:
    """Add the keys of image XObjects reachable from `owner`'s resources to `images`.

    Recurses into Form XObjects not yet in `forms` (the per-page visited set,
    which also ends cycles). Form content is never read.
    """
    resources = _resolve(owner.get("/Resources"))
    if not isinstance(resources, DictionaryObject):
        return
    xobjects = _resolve(resources.get("/XObject"))
    if not isinstance(xobjects, DictionaryObject):
        return
    for name in list(xobjects.keys()):
        xobj = _resolve(xobjects.get(name))
        if not isinstance(xobj, StreamObject):
            continue
        subtype = xobj.get("/Subtype")
        key = _key(xobj)
        if subtype == "/Image":
            if _big_enough(_resolve(xobj.get("/Width")), _resolve(xobj.get("/Height"))):
                images.add(key)
        elif subtype == "/Form" and key not in forms:
            forms.add(key)
            _collect_image_xobjects(xobj, images, forms)


def count_page_images(page: DictionaryObject) -> int:
    """Distinct image XObjects reachable from the page plus inline images in its content.

    Both only if at least MIN_IMAGE_SIDE_PX on each side (ADR-0021).
    """
    images: set[Any] = set()
    _collect_image_xobjects(page, images, set())
    return len(images) + count_inline_images(_content_bytes(page.get("/Contents")))


def count_images(path: str) -> int:
    """`n_images` for the PDF at `path` (counting rule: SDD Sec. 7.1, 7.4)."""
    reader = PdfReader(path)
    return sum(count_page_images(page) for page in reader.pages)


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
