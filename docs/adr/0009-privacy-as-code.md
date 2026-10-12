# ADR-0009: Privacy metadata as code; statement is rendered

**Status:** Accepted
**Date:** 2026-06-03
**Drivers:** QA-GDPR, QA-PRIV; legal obligation under GDPR Art. 13 for transparency about data processing.

## Decision

A registry in `core/privacy_metadata.py` is the single source of truth for which fields and modules carry what category of data. The technical sections of the GDPR privacy statement are rendered deterministically from this registry by `tta privacy report`. Legal boilerplate (data-subject rights, controller contact) is a checked-in markdown stub, one per supported locale, appended at render time. CI fails if a schema column or registered module is missing from the registry.

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

1. **Header** — generation time, app version.
2. **What we process** — derived from the field categories.
3. **Module-level processing** — derived from the module category declarations.
4. **Storage and retention** — derived from the `retention` fields.
5. **What leaves your machine** — derived from `exported=True` fields.
6. **Your rights under GDPR** — checked-in markdown stub.
7. **Controller contact** — checked-in markdown stub.

Sections 1–5 regenerate every release. Sections 6–7 are checked-in legal stubs.

## Legal stubs (revision 2026-10-12, #6)

**Layout: one pair per locale.** `core/help/privacy/<locale>/rights_stub.md` (section 6) and `core/help/privacy/<locale>/controller_stub.md` (section 7), for `de` and `en`. The stub pair of the active locale is used ([ADR-0020](0020-i18n-mechanism.md) §4 resolution); a locale with no stub directory falls back to the German pair, because German is the default ([SDD §9.6](../SDD.md#96-i18n-posture)) and a statement with a missing legal section is worse than one in the default language. HTML comments are stripped before rendering, so a stub may carry a status comment for maintainers.

Why files per locale and not gettext msgids: the stubs are multi-paragraph legal prose whose **German text is the primary version** (the controller is a German institution). As msgids, the English text would be the key and the German one its translation — the wrong way round for a legal text — and every editorial change to the German wording would orphan the catalogue entry. A file per locale keeps each version reviewable as a whole and keeps the German characters in data, not in `*.py` ([ADR-0018](0018-ascii-source.md)).

**One loader for both adapters.** `core/privacy_metadata.py` owns the lookup (`load_legal_stub()`) and a `render_statement_md()` that renders sections 1–7 in the active locale. `tta privacy report` and the GUI's **Help → Privacy statement** both call it. (Until #6 the GUI called `render_report_md()` without stubs, so the window the professor actually opens had **no** sections 6–7 — drift, not design.)

**Content.** Section 7 names the legal controller of the research project, **Fachhochschule Wedel gGmbH**, and its data protection officer as the contact for exercising the rights, with the contact data published on FH Wedel's privacy-policy page (<https://www.fh-wedel.de/datenschutzrichtlinien/>, read 2026-10-12). The project group remains named as the research project, not as the controller. Section 6 states the rights of Art. 15, 16, 17, 18, 20 and 21 GDPR and the right to lodge a complaint with a supervisory authority (Art. 77), naming the authority competent for FH Wedel: the Unabhängiges Landeszentrum für Datenschutz Schleswig-Holstein (ULD), which states on its own website that it supervises non-public bodies seated in Schleswig-Holstein (<https://www.datenschutzzentrum.de/ueber-uns/>, contact data from <https://www.datenschutzzentrum.de/kontakt/>, both read 2026-10-12). No student or project-member personal data appears in either stub.

**Review status — stated plainly.** The wording was prepared by the project team on 2026-10-12. **No qualified legal review has taken place.** FH Wedel's data protection officer should confirm sections 6–7 before the first public release, in particular:

1. that FH Wedel gGmbH is the controller for the research project, and whether the statement must also address the case where a user at *another* institution runs the application on its own machine (the stubs name FH Wedel only);
2. that the data protection officer is the right contact for rights requests concerning this project;
3. the **legal basis** of the processing (Art. 13(1)(c) GDPR), which sections 1–7 do not state, and with it which of the listed rights apply in full (portability under Art. 20 and objection under Art. 21 depend on the legal basis);
4. how long the research team keeps exports it has received (section 4 covers only the local project folder);
5. naming the ULD as the competent supervisory authority;
6. whether the English version is a convenience translation with the German text prevailing.

## Alternatives considered

- **Maintaining the privacy statement as a separate Word document.** Drift between schema and statement is inevitable. Rejected.
- **Annotations on Python dataclasses.** Considered but couples the schema definition to the privacy registry; the explicit dict-of-`Field`s is easier to audit at a glance.

## Consequences

- ✅ Schema evolution and statement evolution cannot drift: a missing entry breaks CI.
- ✅ Researchers, IT staff, and ethics boards can run one command to see exactly what the app does with data.
- ✅ Export rules and the statement's "what leaves your machine" section can be cross-checked against the same registry.
- ⚠️ The legal stubs are finalised as **project-team wording** (#6, 2026-10-12), not as legally reviewed text: no qualified legal review has taken place, and FH Wedel's data protection officer should confirm them before the first public release (see *Legal stubs* above for the list of points).
- ⚠️ ~~Statement is in English in MVP; localisation deferred via the i18n pipeline.~~ **Superseded:** the MVP is now **German-first** (SDD §9.6) — the statement renders in the active locale (German by default), and the legal stubs exist per locale in German and English (#6, see *Legal stubs* above).

## Revisit when

- ~~Localisation of the privacy statement is requested by a non-English partner institution.~~ Done: the statement is German-first with an English version (#6).
- FH Wedel's data protection officer asks for changes to sections 6–7, or the controller's published contact data change.
- A third UI locale is added: it needs its own stub pair, otherwise its users get the German sections 6–7.
