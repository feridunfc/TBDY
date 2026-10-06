# COLUMN-R1 E0 supervisor handoff

## Scope and checkpoint

- Base HEAD: `951a9b156d53210c7a8520bebfa291a3e3b38ee4`
- Base TREE: `289fd8e9123a192d260257a270ac62bfeed9faf6`
- Fetched `origin/main` and confirmed exact base; clean dedicated worktree created.
- Branch: `worker/column-r1-e0-report-delivery-20260927`
- Scope: exact top-level blocker census plus offline canonical report delivery.
- No live ETABS access, source-model mutation, engineering-authority patch, or E1/E2 implementation.

## E0-A evidence

- See `docs/COLUMN_R1_E0_BLOCKER_CENSUS.md` for all 260 component memberships, exact tokens, combinations, story groups and source fields/hashes.
- Receipt and slim summary agree exactly: 260 UNRESOLVED, 0 READY.
- 12 exact blocker tokens, 450 occurrences, 14 exact combinations.
- First exposed prerequisite gate: A18 on 118; A17 tolerance on 142.
- A19 co-occurs on 56 of the 118; no A19-only component.
- Receipt proves B6=0 and StartDesign=0; A38/A39/A40 present; composition PASS.
- A17 tolerance is checked only after accumulated A18/A19 prerequisites return clean.
- A19 co-occurrence does not establish that A18 caused the free-length gap.
- Eq.7.13 global-uncracked blocker is absent from top-level tokens; its nested population scope is NOT_ESTABLISHED by these inputs.
- No assertion that the 12 top-level tokens are the complete nested engineering blocker inventory.

## E0-B gap classification

**EXTEND_EXISTING** acceptance harness; **ADAPT_EXISTING** print CSS in the existing HTML owner; all model/projection/package owners reused.

Inspected owners:
- `unified_building_report.BuildingReportModel`: immutable canonical reconciled truth.
- `building_report_projection.project_building_report_view`: both views consume that same model.
- `building_report_package.build_building_report_package`: canonical JSON, HTML, real PDF, XLSX, manifest and deterministic ZIP already implemented.
- `building_report_package.verify_building_report_package`: existing package integrity owner reused.
- `tools/run_column_r1_public_acceptance.py`: previously persisted observations/receipt only.

Minimal change:
- Add `_persist_report_package(model, output)` to the existing harness.
- Build and verify through existing owners; persist canonical ZIP without overwriting an existing file; verify persisted SHA256.
- After composition acceptance, call it with the exact `result.building_report_model` from the already-completed `execute_project(...)`.
- Record `report_delivery.filename`, `.sha256`, `.size_bytes` in the receipt.
- Renderer/integrity/I/O failures propagate to the existing receipt error path.
- Engineering status is not consulted to upgrade, suppress or reinterpret the report.
- Real public-root rendering exposed a WeasyPrint pagination assertion for oversized component grids.
- Isolating the Components section reproduced the failure; block flow rendered it successfully (7 pages).
- Add only `.component-grid{display:block}` inside existing print CSS; screen layout and report content are unchanged.
- This is a pagination defect repair, not a new renderer or report redesign. HTML/source-render hashes naturally account for the CSS change.
- No new model, renderer, denominator, FCR, public DTO or engineering calculation.

## Delivery contract and validation scope

ZIP members remain exactly:
`building_report_model.json`, `engineering.html`, `audit.html`,
`engineering.pdf`, `audit.pdf`, `engineering.xlsx`, `audit.xlsx`, `manifest.json`.

New offline test reuses the existing two-column public-root fixture with fake ETABS I/O and real engineering/report owners.
It removes the fixture's reviewed tolerance to exercise an all-UNRESOLVED public result.
An additional bounded pagination regression reproduces the former failure with 80 source-reference links; all 80 must survive in the real multipage PDF.
The public-root test proves repeat ZIP byte identity, exact canonical JSON, readable real PDF/XLSX,
preserved component truth, unchanged execution counters, failure propagation and no overwrite.
This is offline fixture proof, not a new live-backed B-BLOK report or a 260-column rendering performance test.
The full two-column fixture produces 275 Engineering PDF pages and 290 Audit PDF pages; production population rendering scale is not established by this validation.
Fixture ZIP SHA256 (both runs): `609090bdf49d76609e8b7040579a4c2ed8e00a2a82847135d88a581fd6c0e865`.

Validation groups:
- Compile/import and `git diff --check`: **PASS**.
- Existing A40 + canonical package tests after all fixes: **25 PASS** (25.48 s; exit 0).
- Projection/HTML/PDF, public population/B6/mixed-root and B5/B6 boundary guards (148 PASS before the print-only repair; affected renderers retested below).
- New public-root delivery and negative cases: **4 PASS** (346.74 s; real PDF/XLSX, two byte-identical packages).
- New oversized-component pagination regression: **1 PASS** (also included in the final renderer suite).
- HTML/PDF/professional-report regression after the print fix: **92 PASS** (179.09 s; exit 0).

Changed paths:
- `docs/COLUMN_R1_E0_BLOCKER_CENSUS.md`
- `docs/COLUMN_R1_E0_HANDOFF.md`
- `tools/run_column_r1_public_acceptance.py`
- `tbdy_engine/product_reports/building_report_html_ur1c.py`
- `tests/application/test_column_r1_report_delivery.py`
- `tests/product_reports/test_building_report_pdf.py`

## Next engineering edge

E1: census existing reviewed story-translation tolerance authority in repository and project documents; bind only an approved source-backed value.
No guessed epsilon or inference from ETABS numerical noise.
E1 alone is not promised to unlock all columns: 118 expose earlier A18 prerequisites, including 56 A19 co-occurrences.
E2: determine whole-system uncracked evidence scope from local nested evidence when needed; do not reinterpret top-level absence as resolution.

The next required live acceptance remains deferred until engineering-authority repairs are accepted.
Before that run, verify the pinned report toolchain offline on the supervisor host using the focused report tests.
The existing live command/arguments remain unchanged; the same successful public-root result now persists the canonical ZIP.
Do not perform a live run only to render a report, or request upload of the 480 MB forensic artifact.
