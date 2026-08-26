"""Repository over the project database (SDD Sec. 8.1, ADR-0006).

The repository is the only code that writes SQL. It is used exclusively
from the main process (ADR-0013: workers never touch the DB).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tta
from tta.core.types import Thesis

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tta.core.artefacts import ArtefactStore


# Paths per add transaction (#61): large enough that a folder add is a
# handful of commits, small enough that a failure part-way keeps the
# chunks already committed and the dedup IN (...) list stays modest.
_ADD_CHUNK = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_to_thesis(row: sqlite3.Row) -> Thesis:
    return Thesis(
        id=row["id"],
        pdf_sha256=row["pdf_sha256"],
        pdf_path=row["pdf_path"],
        pdf_filename=row["pdf_filename"],
        excluded=bool(row["excluded"]),
    )


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @contextmanager
    def transaction(self):
        """Single transaction; the runner commits once per thesis (ADR-0013)."""
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    # -- sources ---------------------------------------------------------

    def ensure_local_source(self, name: str = "Local", institution: str | None = None) -> int:
        """The single `kind='local'` row of a fresh DB (ADR-0006)."""
        row = self.conn.execute("SELECT id FROM sources WHERE kind = 'local'").fetchone()
        if row is not None:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO sources (name, kind, institution, app_version, created_at)"
            " VALUES (?, 'local', ?, ?, ?)",
            (name, institution, tta.__version__, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    # -- theses ----------------------------------------------------------

    def add_thesis(self, pdf_path: Path | str) -> Thesis:
        """Add one thesis; a one-element delegate to :meth:`add_theses`.

        Instant add (ADR-0006 rev. 4, #38): no file read, so adding a folder
        of PDFs never feels like the app hung (US-RES-LOW-FRICTION).
        ``pdf_sha256`` is left NULL; dedup keys on ``(source_id, pdf_path)``.
        A re-added path updates its filename/size and keeps identity and run
        history. The content hash and content-dedup are applied lazily at
        run time (:meth:`assign_content_hash`). Thesis type is a detected
        metric, not an add-time attribute (ADR-0019, #9)."""
        return self.add_theses([pdf_path])[0]

    def add_theses(self, pdf_paths: "Sequence[Path | str]") -> list[Thesis]:
        """Add many theses in **one transaction per chunk**, not one commit per
        file (ADR-0006 rev. 6, #61).

        The rev. 4 "instant add" claim held for the *file* work (nothing is
        read) but not for the *transaction* work: committing per row cost one
        fsync per PDF, which is what made adding a folder feel slow. Here the
        local ``source_id`` is resolved once, every path is ``stat``-ed
        **before** the transaction opens (so a vanished file aborts the chunk
        with nothing written, as :meth:`add_thesis` always did), the dedup
        lookup is a single batched ``SELECT`` for the whole chunk rather than
        one per file, and the chunk commits once.

        Returns one :class:`Thesis` per **distinct** path, in first-appearance
        order; a path repeated inside one batch resolves to a single row, just
        as re-adding it would. Batches larger than ``_ADD_CHUNK`` are split
        across transactions, so a failure part-way does not discard the chunks
        that already committed (and the ``IN (...)`` list stays well inside
        SQLite's host-parameter limit)."""
        # First-appearance order, de-duplicated; the last Path object for a
        # given path string wins, mirroring "a re-add updates the row".
        unique: dict[str, Path] = {}
        for pdf_path in pdf_paths:
            path = Path(pdf_path)
            unique[str(path)] = path
        keys = list(unique)
        if not keys:
            return []
        source_id = self.ensure_local_source()  # once for the batch, not per file
        theses: list[Thesis] = []
        for start in range(0, len(keys), _ADD_CHUNK):
            theses.extend(
                self._add_theses_chunk(source_id, unique, keys[start:start + _ADD_CHUNK])
            )
        return theses

    def _add_theses_chunk(
        self, source_id: int, unique: dict[str, Path], keys: list[str]
    ) -> list[Thesis]:
        """One chunk of :meth:`add_theses`: one transaction, one commit."""
        # cheap: metadata only, not a full read - and outside the transaction,
        # so a missing file leaves the database untouched.
        sizes = {key: unique[key].stat().st_size for key in keys}
        placeholders = ",".join("?" * len(keys))
        added_at = _now()
        ids: list[int] = []
        with self.transaction():  # a single commit for the whole chunk (#61)
            existing = {
                row["pdf_path"]: row["id"]
                for row in self.conn.execute(
                    "SELECT id, pdf_path FROM theses"
                    f" WHERE source_id = ? AND pdf_path IN ({placeholders})",
                    (source_id, *keys),
                )
            }
            for key in keys:
                path = unique[key]
                thesis_id = existing.get(key)
                if thesis_id is not None:
                    self.conn.execute(
                        "UPDATE theses SET pdf_filename = ?, pdf_size_bytes = ? WHERE id = ?",
                        (path.name, sizes[key], thesis_id),
                    )
                else:
                    cur = self.conn.execute(
                        "INSERT INTO theses (source_id, pdf_sha256, pdf_size_bytes, pdf_path,"
                        " pdf_filename, added_at)"
                        " VALUES (?, NULL, ?, ?, ?, ?)",
                        (source_id, sizes[key], key, path.name, added_at),
                    )
                    thesis_id = cur.lastrowid
                ids.append(thesis_id)
        # one read-back for the chunk instead of one get_thesis per file
        rows = {
            row["id"]: _row_to_thesis(row)
            for row in self.conn.execute(
                f"SELECT * FROM theses WHERE id IN ({','.join('?' * len(ids))})", ids
            )
        }
        return [rows[thesis_id] for thesis_id in ids]

    def assign_content_hash(self, thesis: Thesis) -> int:
        """Lazily compute + persist ``pdf_sha256`` and apply content-dedup
        (ADR-0006 rev. 4, #38). Called from the main process at run time
        (workers never touch the DB, ADR-0013).

        Returns the *canonical* thesis id: normally the thesis's own id;
        but if the freshly-computed hash matches an already-hashed sibling
        in the same source (two paths, byte-identical content), that sibling
        is canonical and this row is folded into it - the canonical adopts
        the most-recently-seen path and the duplicate's redundant runs,
        metrics, artefact references and row are removed. No-op (returns the
        id unchanged) when the hash is already set."""
        row = self.conn.execute(
            "SELECT id, source_id, pdf_sha256, pdf_path, pdf_filename, pdf_size_bytes"
            " FROM theses WHERE id = ?",
            (thesis.id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"no thesis with id {thesis.id}")
        if row["pdf_sha256"] is not None:
            return row["id"]
        sha = sha256_of(Path(row["pdf_path"]))
        sibling = self.conn.execute(
            "SELECT id FROM theses WHERE source_id = ? AND pdf_sha256 = ? AND id <> ?",
            (row["source_id"], sha, row["id"]),
        ).fetchone()
        if sibling is None:
            self.conn.execute(
                "UPDATE theses SET pdf_sha256 = ? WHERE id = ?", (sha, row["id"])
            )
            self.conn.commit()
            return row["id"]
        canonical = sibling["id"]
        with self.transaction():
            self.conn.execute(
                "UPDATE theses SET pdf_path = ?, pdf_filename = ?, pdf_size_bytes = ?"
                " WHERE id = ?",
                (row["pdf_path"], row["pdf_filename"], row["pdf_size_bytes"], canonical),
            )
            # One delete implementation, shared with delete_thesis (#63). The
            # inner helper is called rather than delete_thesis itself because
            # the canonical row's path update and the duplicate's removal must
            # land in this one transaction. No disk purge is needed: the folded
            # row has a NULL hash, so it was never run and cached nothing - the
            # row deletes below are defensive.
            self._delete_thesis_rows(row["id"])
        return canonical

    def get_thesis(self, thesis_id: int) -> Thesis:
        row = self.conn.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        if row is None:
            raise KeyError(f"no thesis with id {thesis_id}")
        return _row_to_thesis(row)

    def list_theses(self, *, local_only: bool = True, include_excluded: bool = True) -> list[Thesis]:
        query = (
            "SELECT t.* FROM theses t JOIN sources s ON s.id = t.source_id WHERE 1=1"
        )
        if local_only:
            query += " AND s.kind = 'local'"  # runner filter, US-RES-LOCAL-RERUN
        if not include_excluded:
            query += " AND t.excluded = 0"
        return [_row_to_thesis(r) for r in self.conn.execute(query + " ORDER BY t.id")]

    def set_excluded(self, thesis_id: int, excluded: bool) -> None:
        self.conn.execute(
            "UPDATE theses SET excluded = ? WHERE id = ?", (1 if excluded else 0, thesis_id)
        )
        self.conn.commit()

    def purge_analysis(self, thesis_id: int, store: "ArtefactStore | None" = None) -> None:
        """Scrub an excluded thesis's cached analysis (US-PROF-EXCLUDE, #11).

        The one sanctioned break in append-only history (ADR-0006 rev. 5): in
        a single transaction, delete this thesis's ``metric_values`` (joined
        via its ``module_runs``), ``artefact_files`` and ``module_runs`` rows
        - keeping the ``theses`` row (with ``excluded=1``) so its content-
        addressed identity is remembered and it is never silently re-analysed.
        The on-disk ``artefacts/<thesis_id>/`` tree (the PII-bearing files) is
        removed afterwards via ``store.purge`` when a ``store`` is supplied.
        The source PDF is untouched.

        Delete order respects the ``run_id`` foreign keys: ``metric_values``
        and ``artefact_files`` reference ``module_runs(id)``, so they go first.
        The filesystem removal follows the DB commit; if ``store.purge`` raises
        (e.g. a locked file), the DB scrub has already committed - state is
        consistent - and the error propagates so the caller can warn that the
        local artefact files were not fully removed. Those files never leave the
        machine (ADR-0007), so an incomplete scrub is a local-only warning.
        """
        with self.transaction():
            self.conn.execute(
                "DELETE FROM metric_values WHERE run_id IN"
                " (SELECT id FROM module_runs WHERE thesis_id = ?)",
                (thesis_id,),
            )
            self.conn.execute("DELETE FROM artefact_files WHERE thesis_id = ?", (thesis_id,))
            self.conn.execute("DELETE FROM module_runs WHERE thesis_id = ?", (thesis_id,))
        if store is not None:
            store.purge(thesis_id)

    def _delete_thesis_rows(self, thesis_id: int) -> None:
        """Every row belonging to one thesis, the `theses` row included.

        The single delete implementation (ADR-0006 rev. 7, #63): shared by
        :meth:`delete_thesis` and by the content-dedup fold in
        :meth:`assign_content_hash`, which needs the deletes inside its own
        transaction. Caller owns the transaction and the filesystem step.

        Delete order respects the ``run_id`` foreign keys: ``metric_values``
        and ``artefact_files`` reference ``module_runs(id)``, so they go first,
        and ``theses`` goes last."""
        self.conn.execute(
            "DELETE FROM metric_values WHERE run_id IN"
            " (SELECT id FROM module_runs WHERE thesis_id = ?)",
            (thesis_id,),
        )
        self.conn.execute("DELETE FROM artefact_files WHERE thesis_id = ?", (thesis_id,))
        self.conn.execute("DELETE FROM module_runs WHERE thesis_id = ?", (thesis_id,))
        self.conn.execute("DELETE FROM theses WHERE id = ?", (thesis_id,))

    def delete_thesis(self, thesis_id: int, store: "ArtefactStore | None" = None) -> None:
        """Forget a thesis entirely - the harder version of exclude (#63).

        The second sanctioned break in append-only history (ADR-0006 rev. 7).
        Where :meth:`purge_analysis` deliberately **keeps** the ``theses`` row
        so an excluded thesis's content-addressed identity is remembered, this
        deletes the row too: a PDF added by mistake has no identity worth
        remembering, and a remembered row would keep blocking a clean re-add of
        the same file. Afterwards the same PDF adds again as a fresh thesis with
        a fresh id and no history.

        In one transaction: the thesis's ``metric_values`` (joined via its
        ``module_runs``), ``artefact_files``, ``module_runs`` and ``theses``
        rows. The on-disk ``artefacts/<thesis_id>/`` tree is then removed via
        ``store.purge`` when a ``store`` is supplied - after the commit, and
        with the same contract as :meth:`purge_analysis`: an ``OSError`` from
        the filesystem step propagates (the DB deletion has already committed,
        so state is consistent) and the caller warns that the local artefact
        files were not fully removed. Those files never leave the machine
        (ADR-0007), so an incomplete removal is a local-only warning. The
        source PDF is untouched.

        Removing an unknown id raises ``KeyError`` rather than silently
        succeeding, so an adapter cannot report a removal that never happened.
        """
        if self.conn.execute(
            "SELECT 1 FROM theses WHERE id = ?", (thesis_id,)
        ).fetchone() is None:
            raise KeyError(f"no thesis with id {thesis_id}")
        with self.transaction():
            self._delete_thesis_rows(thesis_id)
        if store is not None:
            store.purge(thesis_id)

    # -- runs and metrics --------------------------------------------------

    def latest_runs(self) -> dict[tuple[int, str], sqlite3.Row]:
        """Current row per (thesis, module) - planning input (ADR-0013)."""
        rows = self.conn.execute(
            "SELECT * FROM v_module_run_history WHERE recency_rank = 1"
        ).fetchall()
        return {(r["thesis_id"], r["module_name"]): r for r in rows}

    def module_duration_stats(self) -> dict[str, float]:
        """Per-module cost rate for the size-weighted ETA (#39, SDD Sec. 5.5).

        Returns, per module, the mean over past **successful** (``ok``) runs of
        ``duration_ms / pdf_size_bytes`` - a rate in milliseconds per byte.
        Only runs with a recorded ``duration_ms`` and a **positive** PDF size
        contribute (guards divide-by-zero and NULL sizes); a module with no
        such history is simply absent from the result (the estimator then
        falls back to the rate observed so far in the current run)."""
        rows = self.conn.execute(
            "SELECT mr.module_name AS name, mr.duration_ms AS dur, t.pdf_size_bytes AS size"
            " FROM module_runs mr JOIN theses t ON t.id = mr.thesis_id"
            " WHERE mr.status = 'ok' AND mr.duration_ms IS NOT NULL"
            " AND t.pdf_size_bytes IS NOT NULL AND t.pdf_size_bytes > 0"
        ).fetchall()
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for row in rows:
            rate = row["dur"] / row["size"]
            sums[row["name"]] = sums.get(row["name"], 0.0) + rate
            counts[row["name"]] = counts.get(row["name"], 0) + 1
        return {name: sums[name] / counts[name] for name in sums}

    def thesis_sizes(self) -> dict[int, int]:
        """Thesis id -> PDF size in bytes, for weighting the ETA by the size of
        the theses still to process (#39). Theses whose size is unknown (NULL)
        are omitted; ``add_thesis`` records the size (a cheap ``stat``), so this
        is populated from add time even before a thesis is analysed."""
        rows = self.conn.execute(
            "SELECT id, pdf_size_bytes FROM theses WHERE pdf_size_bytes IS NOT NULL"
        ).fetchall()
        return {row["id"]: row["pdf_size_bytes"] for row in rows}

    def record_run(
        self,
        thesis_id: int,
        module_name: str,
        module_version: str,
        status: str,
        *,
        reason: str | None = None,
        error_traceback: str | None = None,
        started_at: str | None = None,
        duration_ms: int | None = None,
        metrics: dict[str, Any] | None = None,
        notes: dict[str, Any] | None = None,
    ) -> int:
        """Append one module run with its metric values; returns run_id.

        Metric typing per Sec. 8.1: numbers (incl. bools) land in value_num,
        strings in value_text, None in neither. ``notes`` is stored as
        JSON; it may contain content-derived values and is therefore
        stripped from exports (Sec. 8.3.1).
        """
        cur = self.conn.execute(
            "INSERT INTO module_runs (thesis_id, module_name, module_version, status,"
            " reason, error_traceback, notes, started_at, duration_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                thesis_id,
                module_name,
                module_version,
                status,
                reason,
                error_traceback,
                json.dumps(notes, ensure_ascii=False) if notes else None,
                started_at or _now(),
                duration_ms,
            ),
        )
        run_id = cur.lastrowid
        for name, value in (metrics or {}).items():
            value_num: float | None = None
            value_text: str | None = None
            if isinstance(value, bool):
                value_num = float(value)
            elif isinstance(value, (int, float)):
                value_num = float(value)
            elif isinstance(value, str):
                value_text = value
            elif value is not None:
                raise TypeError(
                    f"metric {name!r} of {module_name}: unsupported value type {type(value).__name__}"
                )
            self.conn.execute(
                "INSERT INTO metric_values (run_id, metric_name, value_num, value_text)"
                " VALUES (?, ?, ?, ?)",
                (run_id, name, value_num, value_text),
            )
        return run_id

    # -- artefact references ----------------------------------------------

    def record_artefact(self, thesis_id: int, kind: str, relative_path: str, run_id: int) -> None:
        self.conn.execute(
            "INSERT INTO artefact_files (thesis_id, kind, relative_path, run_id)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT (thesis_id, kind) DO UPDATE SET relative_path = excluded.relative_path,"
            " run_id = excluded.run_id",
            (thesis_id, kind, relative_path, run_id),
        )

    def current_artefacts(self, thesis_id: int) -> dict[str, str]:
        rows = self.conn.execute(
            "SELECT kind, relative_path FROM artefact_files WHERE thesis_id = ?", (thesis_id,)
        ).fetchall()
        return {r["kind"]: r["relative_path"] for r in rows}

    # -- current metrics (grid / report binding) ----------------------------

    def current_metrics(self, *, local_only: bool = True) -> list[sqlite3.Row]:
        query = "SELECT * FROM v_current_metrics"
        if local_only:
            query += " WHERE source_id IN (SELECT id FROM sources WHERE kind = 'local')"
        return self.conn.execute(query + " ORDER BY thesis_id, module_name, metric_name").fetchall()
