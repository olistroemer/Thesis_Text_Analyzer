"""Unit tests for mod_count_images (SDD Sec. 7.1 #9, counting rule Sec. 7.4, #85)."""

import dataclasses
import subprocess
import sys
import textwrap
import zlib
from pathlib import Path

import pytest

from tta.core.modules.count_images import CountImages, count_inline_images
from tests.conftest import make_thesis

REPO_ROOT = Path(__file__).resolve().parents[2]

# A 1x1 RGB image XObject; its data is never read by the module.
IMAGE = (b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 "
         b"/ColorSpace /DeviceRGB /BitsPerComponent 8 >>", b"\xff\x00\x00")
# An inline image whose data cannot be decoded: DCT filter over garbage (and
# decoding DCT needs Pillow in any case). 0.1.0 failed on it.
BAD_INLINE = b"q 10 0 0 10 0 0 cm BI /W 4 /H 4 /CS /RGB /BPC 8 /F /DCT ID \x00\x01BI\x02\xff EI Q\n"
GOOD_INLINE = b"q BI /W 2 /H 1 /CS /G /BPC 8 ID \x10\x20 EI Q\n"


def _pdf(objects: dict, page_ids: list) -> bytes:
    """Build a classic-xref PDF. `objects` maps id -> dict bytes or (dict bytes, stream data).

    Object 1 is the catalog and 2 the page tree; `page_ids` are the page objects.
    """
    kids = b" ".join(b"%d 0 R" % i for i in page_ids)
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(page_ids)}
    objs.update(objects)
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        body = objs[num]
        out += b"%d 0 obj\n" % num
        if isinstance(body, tuple):
            head, data = body
            assert head.endswith(b">>")
            out += head[:-2] + b" /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"
        else:
            out += body
        out += b"\nendobj\n"
    size = max(objs) + 1
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for num in range(1, size):
        if num in offsets:
            out += b"%010d 00000 n \n" % offsets[num]
        else:
            out += b"0000000000 65535 f \n"
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


def _page(resources: bytes, contents: int) -> bytes:
    return (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources "
            + resources + b" /Contents %d 0 R >>" % contents)


def _form(resources: bytes, content: bytes) -> tuple:
    return (b"<< /Type /XObject /Subtype /Form /BBox [0 0 1 1] /Resources " + resources + b" >>", content)


def _count(build_ctx, tmp_path, objects, page_ids, name="t.pdf"):
    path = tmp_path / name
    path.write_bytes(_pdf(objects, page_ids))
    return CountImages().run(build_ctx(thesis=make_thesis(path))).metrics["n_images"]


@pytest.fixture
def pdf_with_images(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "with_images.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # Two different images: PyMuPDF stores identical pixmaps once (one object
    # under two names), which counts once on the page (SDD Sec. 7.4).
    for shade, x in ((200, 72), (100, 200)):
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8))
        pixmap.clear_with(shade)
        page.insert_image(fitz.Rect(x, 72, x + 72, 144), pixmap=pixmap)
    doc.new_page()  # second page, no images
    doc.save(path)
    doc.close()
    return path


def test_counts_embedded_images(build_ctx, pdf_with_images):
    thesis = make_thesis(pdf_with_images)
    result = CountImages().run(build_ctx(thesis=thesis))
    assert result.metrics == {"n_images": 2}


def test_text_only_pdf_has_zero(build_ctx, sample_thesis):
    result = CountImages().run(build_ctx(thesis=sample_thesis))
    assert result.metrics == {"n_images": 0}


def test_applicable_only_for_pdf(sample_thesis):
    not_pdf = dataclasses.replace(sample_thesis, pdf_path="/tmp/x.docx")
    assert not CountImages().applicable(not_pdf).ok


def test_version_bumped_for_changed_counting_rule():
    assert CountImages.spec.version == "0.2.0"


def test_image_xobject(build_ctx, tmp_path):
    objects = {3: _page(b"<< /XObject << /Im1 4 0 R >> >>", 5), 4: IMAGE,
               5: (b"<< >>", b"q 10 0 0 10 0 0 cm /Im1 Do Q")}
    assert _count(build_ctx, tmp_path, objects, [3]) == 1


def test_inline_images_in_flate_content(build_ctx, tmp_path):
    content = zlib.compress(GOOD_INLINE + b"BT (BI not an image ID x EI) Tj ET\n"
                            b"% BI in a comment\n" + GOOD_INLINE)
    objects = {3: _page(b"<< >>", 4), 4: (b"<< /Filter /FlateDecode >>", content)}
    assert _count(build_ctx, tmp_path, objects, [3]) == 2


def test_nested_form_xobject(build_ctx, tmp_path):
    # page -> form 5 -> form 6 -> image 4. Form 6 also holds an inline image,
    # which does not count: only the page's own content is scanned (SDD Sec. 7.4).
    objects = {
        3: _page(b"<< /XObject << /Fm1 5 0 R >> >>", 7),
        4: IMAGE,
        5: _form(b"<< /XObject << /Fm2 6 0 R >> >>", b"/Fm2 Do"),
        6: _form(b"<< /XObject << /Im1 4 0 R >> >>", b"/Im1 Do " + GOOD_INLINE),
        7: (b"<< >>", b"/Fm1 Do"),
    }
    assert _count(build_ctx, tmp_path, objects, [3]) == 1


def test_same_xobject_counts_once_per_page(build_ctx, tmp_path):
    # Image 4 on two pages; on page 3 drawn twice, under two names and inside a form.
    objects = {
        3: _page(b"<< /XObject << /ImA 4 0 R /ImB 4 0 R /Fm 6 0 R >> >>", 7),
        5: _page(b"<< /XObject << /Im1 4 0 R >> >>", 8),
        4: IMAGE,
        6: _form(b"<< /XObject << /Im 4 0 R >> >>", b"/Im Do"),
        7: (b"<< >>", b"/ImA Do /ImA Do /ImB Do /Fm Do"),
        8: (b"<< >>", b"/Im1 Do"),
    }
    assert _count(build_ctx, tmp_path, objects, [3, 5]) == 2


def test_form_xobject_cycle_terminates(build_ctx, tmp_path):
    objects = {
        3: _page(b"<< /XObject << /Fa 5 0 R >> >>", 7),
        4: IMAGE,
        5: _form(b"<< /XObject << /Fb 6 0 R /Im 4 0 R >> >>", b"/Fb Do"),
        6: _form(b"<< /XObject << /Fa 5 0 R >> >>", b"/Fa Do"),
        7: (b"<< >>", b"/Fa Do"),
    }
    assert _count(build_ctx, tmp_path, objects, [3]) == 1


def test_missing_and_broken_resources_count_zero(build_ctx, tmp_path):
    objects = {
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>",  # no resources, no contents
        4: _page(b"<< /XObject << /Im 99 0 R /N null /D << >> >> >>", 5),  # dangling / non-stream entries
        5: (b"<< >>", b"/Im Do"),
    }
    assert _count(build_ctx, tmp_path, objects, [3, 4]) == 0


def test_undecodable_inline_image_is_counted(build_ctx, tmp_path):
    """0.1.0 decoded inline images via page.images: Pillow needed, garbage DCT data failed."""
    from pypdf import PdfReader

    objects = {3: _page(b"<< >>", 4), 4: (b"<< >>", BAD_INLINE)}
    path = tmp_path / "bad_inline.pdf"
    path.write_bytes(_pdf(objects, [3]))
    with pytest.raises(Exception):  # the 0.1.0 counting path
        len(PdfReader(path).pages[0].images)
    assert _count(build_ctx, tmp_path, objects, [3], name="bad_inline_new.pdf") == 1


@pytest.mark.parametrize("data, expected", [
    (b"", 0),
    (b"BT (BI) Tj ET", 0),
    (b"BT (a \\) BI ( nested ) ) Tj ET", 0),
    (b"/BI 1 def", 0),
    (b"BI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI", 1),
    (b"BI/W 1/H 1/BPC 8/CS/G ID \x00 EI\nBI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI", 2),
    # /L skips data that contains " EI " instead of stopping there.
    (b"BI /W 5 /H 1 /BPC 8 /CS /G /L 5 ID x EI  EI BI ", 1),
    (b"BI /W 1 /H 1 ID \x00", 1),  # truncated data: counted, scan ends
    (b"BI /W 1 /H 1", 0),  # no ID: not an image
])
def test_count_inline_images(data, expected):
    assert count_inline_images(data) == expected


def test_pil_is_never_imported(tmp_path):
    """The module must not reach Pillow or pypdf's image-decoding path (#85)."""
    path = tmp_path / "mixed.pdf"
    path.write_bytes(_pdf({
        3: _page(b"<< /XObject << /Im1 4 0 R >> >>", 5), 4: IMAGE,
        5: (b"<< >>", b"/Im1 Do " + BAD_INLINE),
    }, [3]))
    script = textwrap.dedent("""
        import sys
        attempts = []

        class Blocker:
            def find_spec(self, name, path=None, target=None):
                if name == "PIL" or name.startswith("PIL."):
                    attempts.append(name)
                    raise ImportError("PIL blocked by test")
                return None

        sys.meta_path.insert(0, Blocker())
        from tta.core.modules.count_images import count_images
        attempts.clear()  # pypdf probes for PIL at import time; only the run matters
        n = count_images(sys.argv[1])
        assert n == 2, n
        assert not attempts, attempts
        assert "pypdf.generic._image_xobject" not in sys.modules
        assert not any(m == "PIL" or m.startswith("PIL.") for m in sys.modules)
        print("ok")
    """)
    proc = subprocess.run([sys.executable, "-c", script, str(path)], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"
