# ADR-0017: Project license — copyleft FOSS (AGPL-3.0 or GPL-3.0)

**Status:** Accepted — direction settled; the **AGPL-3.0 vs GPL-3.0** leaf choice is left open (see [§Open question](#open-question)) pending institutional sign-off.
**Date:** 2026-06-24
**Drivers:** QA-PRIV, QA-GDPR (transparency / auditability), QA-REPRO (guaranteed source availability), US-ALL-PRIVACY; SDD §2.1.1 (extractor licensing); the desire to remove the single hardest pre-distribution blocker. **Supersedes** the "AGPL release gate" portions of [ADR-0011](0011-mvp-module-catalogue.md) and [ADR-0014](0014-distribution.md); reverses the `feedback_agpl_pymupdf` constraint.

## Decision

The application is released as **copyleft free software** with its source public. As a consequence:

1. **PyMuPDF stays.** `mod_extract_pymupdf` may be the extractor shipped in the distributed binary; it no longer has to be replaced before distribution.
2. **The AGPL contamination gate is retired.** The CI grep that forbade `import fitz`/`import pymupdf` under `tta/core/` (ADR-0011, ADR-0014, SDD §5.2) is removed. Keeping a copyleft dependency is no longer a problem to be guarded against — it is the chosen posture.
3. **Source is conveyed with every binary.** The project's public Git repository at the tagged release commit is the Corresponding Source; distributing the binary alongside a link to that tag satisfies the obligation.
4. **The library-comparison study (SDD §2.1.1) survives as research, not as a ship blocker.** Picking the best-quality extractor remains valuable; its "license compatibility with redistribution" axis becomes informative rather than decisive.

The choice between **AGPL-3.0** and **GPL-3.0** is deferred to a follow-up decision; both are compatible with everything below.

## Context

The earlier ADRs treated a copyleft dependency as a hazard because they carried an unstated assumption that the deliverable must not be copyleft — yet **no ADR ever decided the project's own outbound license.** This ADR makes that decision explicitly.

Two facts make copyleft cheap here, and one tempers it:

- **The app is offline (US-ALL-OFFLINE, QA-PRIV, §2.3).** AGPL's only substantive difference from GPL-3.0 is its §13 network-interaction clause. With no network use, §13 is **dormant**, so AGPL and GPL impose the same practical obligations: provide source to those you distribute to.
- **Dependencies are already compatible.** tksheet (MIT), matplotlib (PSF/BSD-style), click (BSD), rich (MIT), langdetect & nltk (Apache-2.0, one-way-compatible with GPLv3/AGPLv3), textstat/pypdf/tomli-w (MIT/BSD), tkinter (PSF). PyInstaller is GPL **with a bundling exception** that does not bind the frozen app. A one-time license audit should confirm this before release.
- **Auditability is a property of open-sourcing, not of AGPL specifically.** The privacy benefit — a professor's IT/ethics board can read the code and verify "local-only, no PII export" — would hold under any open license. Copyleft's distinct contribution is keeping derivatives and forks open, which suits a publication-linked measurement tool.

## Open question

**AGPL-3.0 vs GPL-3.0.** Both keep PyMuPDF and both retire the gate (GPLv3 §13 explicitly permits combining a GPLv3 work with an AGPLv3 dependency; for an offline app the AGPL terms on the PyMuPDF portion never trigger). The decision inputs:

| | AGPL-3.0 | GPL-3.0 |
|---|---|---|
| Offline app today | §13 dormant — no practical effect | identical practical effect |
| If a network/SaaS feature is ever added | already covered (source-to-users obligation) | **not** covered — a hosted fork could stay closed |
| Ecosystem stigma | highest; many orgs blocklist AGPL outright | lower; widely accepted |
| Whole-project licensing story | uniform, simplest to explain | relies on the GPLv3↔AGPLv3 combination clause for the PyMuPDF part |

Given §2.3 commits the project to offline operation, GPL-3.0 is "enough" and AGPL is belt-and-suspenders against a future the SDD says we will not build. AGPL is the stronger fit if there is any chance of a future hosted variant or if maximal copyleft is wanted on principle. **No recommendation is locked in here**; resolve once FH Wedel's policy on the license/IP of research work products is confirmed.

## Alternatives considered

- **Permissive (MIT/BSD/Apache-2.0).** Maximises adoption and reuse, but requires *removing* PyMuPDF (or buying Artifex's commercial license) — i.e. it keeps the extractor-swap blocker alive and forces re-validation of the ADR-0015 performance budgets. Rejected as the costlier path for an academic tool with no commercial ambition; revisit if industry adoption becomes a goal.
- **Status quo (swap to a non-AGPL extractor, stay license-flexible).** The pre-this-ADR plan. Defensible, but front-loads the extractor study as a release blocker and re-anchors performance budgets. Demoted by this ADR to research scope.
- **Dual-licensing (copyleft + commercial).** Overkill for the current threat/ambition model; revisit only if a commercial consumer appears.
- **Closed source.** Contradicts the auditability/transparency rationale (QA-PRIV/QA-GDPR) and the contribute-via-PR model (§2.3, ADR-0004). Rejected.

## Consequences

- ✅ **Packaging (ADR-0014) is unblocked immediately** — no extractor swap required to ship a lawful binary.
- ✅ **QA-RES is de-risked** — keeping the validated PyMuPDF extractor avoids re-anchoring the ADR-0015 budgets.
- ✅ **Reinforces QA-PRIV / QA-GDPR / QA-REPRO** — auditable source backs the local-only claim and guarantees the exact code behind any publication is available.
- ✅ The CI surface shrinks: the AGPL gate is deleted from the boundary checks.
- ⚠️ **Copyleft constrains the future catalogue.** All future modules — including the §12 LM-based and citation modules, and especially **word-list-based vocabulary metrics** (word lists often carry non-commercial or bespoke licenses) — must be license-compatible. Flag in §12.
- ⚠️ **AGPL (if chosen) carries adoption-policy risk** — some institutions/IT departments are AGPL-averse, a mild tension with US-RES-LOW-FRICTION / QA-PORT.
- ⚠️ **Ongoing obligation:** the distributed binary's exact Corresponding Source must stay available; release-tag hygiene matters.
- ℹ️ **Per-file license headers are not required** for the license to be valid — a single root `LICENSE` plus a stated project license suffices. The FSF *recommends* headers because files get copied out of context; given the contribute-via-PR model, lightweight **SPDX identifiers** (`SPDX-License-Identifier: …`) per file are a good compromise. Decided in the LICENSE ticket, not here.

## Revisit when

- A commercial consumer or industry-adoption goal appears (reconsider permissive or dual-licensing).
- An institution declines to deploy on license grounds (reconsider AGPL→GPL, or copyleft→permissive).
- A network/hosted variant is ever contemplated (the AGPL-vs-GPL choice becomes load-bearing rather than dormant).
