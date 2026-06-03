# ADR-0009: Privacy metadata as code; statement is rendered

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** QA-GDPR, QA-PRIV; legal obligation under GDPR Art. 13 for transparency about data processing.

## Decision

A registry in `core/privacy_metadata.py` is the single source of truth for which fields and modules carry what category of data. The technical sections of the GDPR privacy statement are rendered deterministically from this registry by `pds privacy report`. Legal boilerplate (data-subject rights, controller contact) is a reviewed markdown stub appended at render time. CI fails if a schema column or registered module is missing from the registry.

## Categories

```python
class Category(str, Enum):
    TECHNICAL      = "technical"       # versions, durations, etc. No PII.
    CONTENT_HASH   = "content_hash"    # cryptographic fingerprints. No PII.
    METRIC         = "metric"          # numeric/textual analysis output.
    CONTENT        = "content"         # raw or near-raw text — high PII risk.
    IDENTIFYING    = "identifying"     # paths/filenames/notes — direct PII.
```

Each `Field` declares: `table`, `column`, `category`, `purpose`, `exported`, `retention`.
Each `Module` declares: `name`, `reads_categories`, `writes_categories`, `purpose`.
Each `ArtefactKind` declares: `kind`, `category`, `description`, `exported` (always `False` for content/identifying kinds in MVP).

## Generation

```
pds privacy report --format md     # markdown — for ethics boards / institutional IT
pds privacy report --format json   # machine-readable
pds privacy report --format pdf    # PDF via pandoc/xelatex
```

The rendered output combines:

1. **Header** — generation time, app version.
2. **What we process** — derived from the field categories.
3. **Module-level processing** — derived from the module category declarations.
4. **Storage and retention** — derived from the `retention` fields.
5. **What leaves your machine** — derived from `exported=True` fields.
6. **Your rights under GDPR** — checked-in markdown stub.
7. **Controller contact** — checked-in markdown stub.

Sections 1–5 regenerate every release. Sections 6–7 are reviewed legal stubs.

## Alternatives considered

- **Maintaining the privacy statement as a separate Word document.** Drift between schema and statement is inevitable. Rejected.
- **Annotations on Python dataclasses.** Considered but couples the schema definition to the privacy registry; the explicit dict-of-`Field`s is easier to audit at a glance.

## Consequences

- ✅ Schema evolution and statement evolution cannot drift: a missing entry breaks CI.
- ✅ Researchers, IT staff, and ethics boards can run one command to see exactly what the app does with data.
- ✅ Export rules and the statement's "what leaves your machine" section can be cross-checked against the same registry.
- ⚠️ Legal stubs still need human review.
- ⚠️ Statement is in English in MVP; localisation deferred via the i18n pipeline.

## Revisit when

Localisation of the privacy statement is requested by a non-English partner institution.
