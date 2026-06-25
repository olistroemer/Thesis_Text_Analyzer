#!/usr/bin/env python
"""Write a tiny English-prose PDF for the frozen-binary smoke test (issue #4).

Used by the ``build-linux`` CI job and for local verification of the
PyInstaller --onefile binaries: it produces enough EN text that the full
module pipeline (language -> tokenize -> readability) is applicable, so a
clean ``0 errors`` run proves the bundled NLTK punkt_tab data and SQL
migrations work inside the frozen executable.

Usage: ``python tests/make_sample_pdf.py <out.pdf>``
"""

from __future__ import annotations

import sys

import fitz  # PyMuPDF

# Same prose the test suite uses (tests/conftest.py ENGLISH_PARAGRAPH): ~45
# words with plenty of EN function words, repeated to clear the language and
# extraction-quality applicability thresholds.
ENGLISH_PARAGRAPH = (
    "The analysis of student theses is an interesting task for the research team. "
    "Many of the documents are written with care, and they contain long sentences "
    "about the methods and the results of the work. The reader can follow the "
    "argument from the first page to the conclusion."
)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: make_sample_pdf.py <out.pdf>")
    out = sys.argv[1]
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        rect = page.rect + (72, 72, -72, -72)
        page.insert_textbox(rect, " ".join([ENGLISH_PARAGRAPH] * 4), fontsize=10)
    doc.save(out)
    doc.close()


if __name__ == "__main__":
    main()
