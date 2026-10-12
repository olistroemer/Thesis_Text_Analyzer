# ADR-0009: Privacy metadata as code; statement is rendered

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** QA-GDPR, QA-PRIV; legal obligation under GDPR Art. 13 for transparency about data processing.

## Decision

A registry in `core/privacy_metadata.py` is the single source of truth for which fields and modules carry what category of data. The technical sections of the GDPR privacy statement are rendered deterministically from this registry by `tta privacy report`. Legal boilerplate (responsibility and data-subject rights, publisher contact) is a checked-in markdown stub, one per supported locale, appended at render time. CI fails if a schema column or registered module is missing from the registry.

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
tta privacy report --format md     # markdown — for ethics boards / institutional IT
tta privacy report --format json   # machine-readable
tta privacy report --format pdf    # PDF via pandoc/xelatex
```

The rendered output combines:

1. **Header** — generation time, app version, then an unnumbered plain-language **summary** generated from the registry (revision 2026-10-12, see *Legal stubs*).
2. **What we process** — derived from the field categories.
3. **Module-level processing** — derived from the module category declarations.
4. **Storage and retention** — derived from the `retention` fields.
5. **What leaves your machine** — derived from `exported=True` fields.
6. **Responsibility and your rights under GDPR** — checked-in markdown stub.
7. **Publisher and contact** — checked-in markdown stub.

Sections 1–5 regenerate every release. Sections 6–7 are checked-in legal stubs.

## Legal stubs (revision 2026-10-12, #6)

**Layout: one pair per locale.** `core/help/privacy/<locale>/rights_stub.md` (section 6) and `core/help/privacy/<locale>/contact_stub.md` (section 7; named `controller_stub.md` until the role split below), for `de` and `en`. The stub pair of the active locale is used ([ADR-0020](0020-i18n-mechanism.md) §4 resolution); a locale with no stub directory falls back to the German pair, because German is the default ([SDD §9.6](../SDD.md#96-i18n-posture)) and a statement with a missing legal section is worse than one in the default language. HTML comments are stripped before rendering, so a stub may carry a status comment for maintainers.

Why files per locale and not gettext msgids: the stubs are multi-paragraph legal prose whose **German text is the primary version** (the publisher is a German institution). As msgids, the English text would be the key and the German one its translation — the wrong way round for a legal text — and every editorial change to the German wording would orphan the catalogue entry. A file per locale keeps each version reviewable as a whole and keeps the German characters in data, not in `*.py` ([ADR-0018](0018-ascii-source.md)).

**One loader for both adapters.** `core/privacy_metadata.py` owns the lookup (`load_legal_stub()`) and a `render_statement_md()` that renders sections 1–7 in the active locale. `tta privacy report` and the GUI's **Help → Privacy statement** both call it. (Until #6 the GUI called `render_report_md()` without stubs, so the window the professor actually opens had **no** sections 6–7 — drift, not design.)

**Role split (revision 2026-10-12, owner decision, #6).** The first finalisation named Fachhochschule Wedel gGmbH as *controller* and listed Art. 15–21 as rights against it. That claimed a responsibility the project does not have, and it is withdrawn:

- **Local processing is the user's.** The application is a tool that runs entirely on the user's machine, offline, with no telemetry (section 4). Everything the registry marks `IDENTIFYING` or `CONTENT` — file names and paths, notes, tags, extracted text, tokenisations, full PDF metadata, tracebacks, diagnostics — exists only there. Processing it is done under the responsibility of the person running the application and their institution. FH Wedel and the project group only *provide the software*; they never receive that data and cannot act on it. **The project deliberately assumes no controllership for local processing.** Data-subject rights concerning it (in practice: students whose theses are analysed) are exercised against the using institution, and section 6 says so.
- **The export is treated as anonymous for the research team.** It carries no direct identifier (section 5; `excluded` rows and every `IDENTIFYING`/`CONTENT` column are stripped, [ADR-0007](0007-export-format.md)). Each thesis is keyed only by `theses.pdf_sha256`, a SHA-256 of the PDF's bytes. Without the PDF the research team has no means reasonably likely to be used to identify the author (GDPR Recital 26), and under the relative approach to identifiability taken by the CJEU (C-413/23 P, *EDPS v SRB*, 4 September 2025) data that is pseudonymous for its originator can be anonymous for a recipient who lacks the additional information. The hash's purpose is **deduplication only**: in the code it folds byte-identical files within a project (`Repository.assign_content_hash`, the `UNIQUE (source_id, pdf_sha256)` constraint), it travels unchanged through export and import (`core/export.py`, `core/importer.py`), and its documented cross-export role is recognising the same thesis contributed twice ([ADR-0006](0006-schema.md), ADR-0007). Nothing in the code uses it to look up a person. The statement deliberately makes **no promise about how the research team uses the hash** ("we do not use it to identify authors"): such a promise would imply that identification were generally possible, and the project's position is that it is not - attributing a hash to a person needs the PDF itself, which is not a means reasonably likely to be used (owner decision, 2026-10-12).
- **Residual risk, stated in the statement itself.** Anyone who holds the PDF can recompute its hash and find that thesis's row in an export — the using institution can, and so could anyone else holding the file. Beyond the hash, the exported metrics include coarse quasi-identifiers (institution, publication year, page count, degree type); in a very small cohort someone with outside knowledge might single out a thesis by them. The research team has neither the PDFs nor that knowledge and does not attempt it. Both residuals are why the assessment is listed for the data protection officer below.
- **Consequences for the statement.** Section 6 explains the split, routes rights about local processing to the using institution's data protection contact, states the export's anonymity assessment and the hash's residual honestly, offers deletion of exports already sent on request (a courtesy, not an Art. 17 obligation - but the statement simply offers it and does not argue the point), and keeps the right to lodge a complaint with a supervisory authority (Art. 77) **generic**. The ULD is no longer named: it is competent for FH Wedel's own processing, and naming it would imply that FH Wedel processes the data. Section 7 is **"Publisher and contact"**, not "Controller": the research project of the Data Science Project Group SS26 at Fachhochschule Wedel gGmbH, with the contact data published on FH Wedel's privacy-policy page (<https://www.fh-wedel.de/datenschutzrichtlinien/>, read 2026-10-12), and FH Wedel's data protection officer as the contact for data-protection questions about the application. Section 7 **names no person**: it refers to the privacy-policy page for the officer's contact details, so the statement stays correct when the office changes hands (owner decision, 2026-10-12). No student or project-member personal data appears in either stub.
- **Why Art. 13(1)(c) (legal basis) and a retention period are not stated for the receiving side.** Both are information duties of a controller about *its* processing of *personal* data. On the receiving side there is no personal data (anonymous export, above), so there is no processing for FH Wedel to state a legal basis or a retention period for. For the local processing, both belong to the using institution as its controller; section 4 still says exactly how long the application keeps data (until the project folder is deleted), so that institution can rely on it.

**Plain-language summary, generated.** Above section 1 the statement carries an unnumbered summary: the application works offline and sends nothing by itself; no data leaves the machine unless the user saves an export and passes it on; what an export contains; that a thesis is keyed only by a content fingerprint used for deduplication; who is responsible for what. It is rendered by `render_report_md()` from the registry, and each claim about the export is **conditional on the registry**: the "no personal names, no file names or paths, no notes or tags, no text" sentence is emitted only while no `IDENTIFYING`/`CONTENT` field and no artefact kind is exported, and the fingerprint sentence names the `CONTENT_HASH` columns actually exported. `tests/core/test_privacy.py` pins both directions, so the summary cannot drift from sections 1–5. The summary does **not** claim the user sees the export's content before sending it — the GUI shows a count and the file's location, not a preview; it claims only what is true: the export is a file the user saves and passes on themselves.

**Review status — stated plainly.** The wording was prepared by the project team on 2026-10-12 and revised the same day after the owner's decision on roles. **No qualified legal review has taken place.** The three points such a review would have had to confirm were **settled by the project owner on 2026-10-12** and are not release blockers:

1. the data protection officer of FH Wedel - reached via the contact details on FH Wedel's privacy-policy page, to which section 7 refers without naming a person - is the contact for data-protection questions about the application;
2. the export is anonymous for the research team (Recital 26, the relative approach of C-413/23 P, with the residual risks above);
3. the role split of section 6: local processing is under the using institution's responsibility, and FH Wedel and the project group assume no controllership.

**The German version prevails** (owner decision, 2026-10-12). The English sections are a convenience translation, and the English statement says so at the end of section 7.

## Alternatives considered

- **Maintaining the privacy statement as a separate Word document.** Drift between schema and statement is inevitable. Rejected.
- **Annotations on Python dataclasses.** Considered but couples the schema definition to the privacy registry; the explicit dict-of-`Field`s is easier to audit at a glance.

## Consequences

- ✅ Schema evolution and statement evolution cannot drift: a missing entry breaks CI.
- ✅ Researchers, IT staff, and ethics boards can run one command to see exactly what the app does with data.
- ✅ Export rules and the statement's "what leaves your machine" section can be cross-checked against the same registry.
- ⚠️ The legal stubs are finalised as **project-team wording** (#6, 2026-10-12, revised for the role split), not as legally reviewed text: no qualified legal review has taken place. The project owner settled the three points such a review would cover on 2026-10-12 (*Legal stubs*), so they do not block a release.
- ⚠️ The project assumes **no controllership for local processing** and treats the export as **anonymous for the research team**. Both rest on facts the code must keep true: no `IDENTIFYING`/`CONTENT` column may become exported, and `pdf_sha256` may be used for deduplication only. A change to either reopens this ADR.
- ⚠️ ~~Statement is in English in MVP; localisation deferred via the i18n pipeline.~~ **Superseded:** the MVP is now **German-first** (SDD §9.6) — the statement renders in the active locale (German by default), and the legal stubs exist per locale in German and English (#6, see *Legal stubs* above).

## Revisit when

- ~~Localisation of the privacy statement is requested by a non-English partner institution.~~ Done: the statement is German-first with an English version (#6).
- FH Wedel's data protection officer asks for changes to sections 6–7, or FH Wedel's published contact data change.
- Anything starts using `pdf_sha256` for more than deduplication, or an `IDENTIFYING`/`CONTENT` value becomes exported: the anonymity assessment and the role split above no longer hold.
- A third UI locale is added: it needs its own stub pair, otherwise its users get the German sections 6–7.
