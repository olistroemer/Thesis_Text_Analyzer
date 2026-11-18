#!/usr/bin/env python
"""Generate the reference aggregates the app ships (ADR-0025, SDD Sec. 9.8).

    python tools/reference_aggregates.py --project <reference project> \\
        --harvest-root <harvester>/data --source "HU edoc + ETH RC, run 2026-11" \\
        [--status interim|release] [--out tta/core/report_assets/reference_aggregates.json]

Researcher tooling, like ``tools/screenshots.py``: not part of the ``tta``
package and never frozen into a binary. It reads

* a **reference project** - a project folder (``tta.sqlite`` inside) or the
  database file itself - strictly read-only (SQLite ``mode=ro``, never
  ``Project.open``, which may migrate), so it can read a project another
  process is still analysing;
* the **harvest metadata** - ``<harvest-root>/<host>/theses.sqlite`` per
  repository host, also read-only - for the field (DDC main class) of each
  reference thesis, joined by PDF file stem through ``downloads.pdf_path``.

The pure half (population rule, statistics, thresholds, file format) is
``tta.core.reference``; this file only knows the harvester's layout.
"""

from __future__ import annotations

import argparse
import datetime
import html
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tta  # noqa: E402
from tta.core import reference  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "tta" / "core" / reference.ASSETS_DIR / reference.AGGREGATES_FILENAME

#: ``.../data/<host>/pdfs/<stem>.pdf`` - the harvester's download layout.
PDF_IN_HARVEST = re.compile(
    r"^(?P<root>.*?)[\\/]data[\\/](?P<host>[^\\/]+)[\\/]pdfs[\\/](?P<stem>[^\\/]+)\.pdf$",
    re.IGNORECASE,
)

_SUBJECT = re.compile(r"<dc:subject[^>]*>([^<]*)</dc:subject>")
_DDC_URI = re.compile(r"info:eu-repo/classification/ddc/([0-9][0-9.]*)")
_DDC_SHORT = re.compile(r"^\s*ddc:([0-9][0-9.]*)\s*$")
_DDC_LABELLED = re.compile(r"^\s*([0-9]{3}(?:\.[0-9]+)?)\s+\S")


def ddc_codes(raw_xml: str) -> list[str]:
    """DDC codes of an OAI-DC record in document order, de-duplicated.
    ETH: ``info:eu-repo/classification/ddc/NNN``; edoc: ``ddc:NNN`` and
    labelled ``NNN Label`` subjects."""
    seen: list[str] = []
    for match in _SUBJECT.finditer(raw_xml or ""):
        subject = html.unescape(match.group(1)).strip()
        hit = _DDC_URI.search(subject) or _DDC_SHORT.match(subject) or _DDC_LABELLED.match(subject)
        if hit:
            code = hit.group(1).rstrip(".")
            if code not in seen:
                seen.append(code)
    return seen


def ddc_main_class(code: str | None) -> str | None:
    """``"621.3"`` -> ``"600"``; None for anything that is not a DDC number."""
    if not code:
        return None
    try:
        hundreds = int(float(code)) // 100 * 100
    except ValueError:
        return None
    main = f"{hundreds:03d}"
    return main if main in reference.FIELDS else None


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_fields(harvest_db: Path) -> dict[str, str | None]:
    """``{pdf file stem: DDC main class or None}`` for one harvest DB."""
    conn = _connect_ro(harvest_db)
    try:
        stem_by_handle = {
            row["handle"]: Path(row["pdf_path"].replace("\\", "/")).stem
            for row in conn.execute(
                "SELECT handle, pdf_path FROM downloads WHERE pdf_path IS NOT NULL"
            )
        }
        fields: dict[str, str | None] = {}
        for row in conn.execute(
            "SELECT handle, raw_record_xml FROM records WHERE deleted = 0"
        ):
            stem = stem_by_handle.get(row["handle"])
            if stem is not None:
                codes = ddc_codes(row["raw_record_xml"] or "")
                fields[stem] = ddc_main_class(codes[0]) if codes else None
        return fields
    finally:
        conn.close()


def project_database(path: Path) -> Path:
    candidate = path / "tta.sqlite" if path.is_dir() else path
    if not candidate.is_file():
        raise SystemExit(f"reference_aggregates: no project database at {candidate}")
    return candidate


def read_project(db_path: Path):
    """(theses, analysed_with) - theses as (pdf_path, {metric: value}) for every
    local, non-excluded thesis; analysed_with the module versions behind the
    current results."""
    conn = _connect_ro(db_path)
    try:
        paths = {
            row["id"]: row["pdf_path"]
            for row in conn.execute(
                "SELECT t.id, t.pdf_path FROM theses t JOIN sources s ON s.id = t.source_id "
                "WHERE s.kind = 'local' AND t.excluded = 0"
            )
        }
        values: dict[int, dict[str, object]] = {tid: {} for tid in paths}
        versions: set[str] = set()
        for row in conn.execute(
            "SELECT thesis_id, module_name, module_version, metric_name, value_num, value_text "
            "FROM v_current_metrics WHERE metric_name IS NOT NULL"
        ):
            if row["thesis_id"] in values:
                value = row["value_num"] if row["value_num"] is not None else row["value_text"]
                values[row["thesis_id"]][row["metric_name"]] = value
                versions.add(f"{row['module_name']} {row['module_version']}")
        return [(paths[tid], values[tid]) for tid in paths], sorted(versions)
    finally:
        conn.close()


def reference_theses(theses, harvest_root: Path | None, log=print):
    """The reference population (``reference.reference_split``) with fields."""
    field_tables: dict[str, dict[str, str | None] | None] = {}
    out, linked, garbled = [], 0, 0
    for pdf_path, values in theses:
        if values.get("extraction_quality") == "garbled":
            garbled += 1
            continue
        split = reference.reference_split(values)
        if split is None:
            continue
        thesis_type, language, year = split
        field_code = None
        location = PDF_IN_HARVEST.match(pdf_path or "")
        if location is not None:
            host = location.group("host")
            if host not in field_tables:
                root = harvest_root if harvest_root is not None else Path(location.group("root")) / "data"
                db = Path(root) / host / "theses.sqlite"
                field_tables[host] = load_fields(db) if db.is_file() else None
                if field_tables[host] is None:
                    log(f"warning: no harvest database for {host} at {db}")
            table = field_tables[host]
            if table is not None and location.group("stem") in table:
                linked += 1
                field_code = table[location.group("stem")]
        out.append(
            reference.ReferenceThesis(
                thesis_type, language, field_code, year, reference.derive_metrics(values)
            )
        )
    log(
        f"{len(theses)} theses read, {garbled} garbled left out, {len(out)} in the "
        f"reference population, {linked} linked to harvest metadata, "
        f"{sum(t.field is not None for t in out)} with a DDC field"
    )
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, required=True,
                        help="reference project folder (or its tta.sqlite), read-only")
    parser.add_argument("--harvest-root", type=Path, default=None,
                        help="the harvester's data/ folder holding <host>/theses.sqlite "
                             "(default: derived from each PDF path)")
    parser.add_argument("--source", required=True,
                        help="provenance text stored in the file (corpus, run)")
    parser.add_argument("--status", choices=("interim", "release"), default="release")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv=None, log=print) -> int:
    args = parse_args(argv)
    theses, analysed_with = read_project(project_database(args.project))
    population = reference_theses(theses, args.harvest_root, log=log)
    document = reference.build_aggregates(
        population,
        status=args.status,
        source=args.source,
        generated=datetime.date.today().isoformat(),
        generator=f"tools/reference_aggregates.py (tta {tta.__version__})",
        analysed_with=analysed_with,
    )
    text = reference.dump_aggregates(document)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    log(f"wrote {args.out}: {len(document['rows'])} buckets, {len(text.encode())} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
