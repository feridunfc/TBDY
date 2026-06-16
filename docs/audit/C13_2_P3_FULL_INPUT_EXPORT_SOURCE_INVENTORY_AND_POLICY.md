# C13.2-P3 Full Input Export Source Inventory and Policy

## Purpose

This add-on adds an offline, ETABS-free source inventory for ETABS-exported input/model-definition workbooks. It answers what tables and columns appear in the export, which future TBDY check-engine source areas may benefit from those tables, and which exact live ETABS probes are still required before any source promotion or check implementation.

## Offline / ETABS-free boundary

The inventory tool reads an `.xlsx` or `.xlsm` workbook with `openpyxl` only. It does not import ETABS, COM, `comtypes`, `win32com`, or any project live provider. It does not require ETABS to be installed or open.

## Excel evidence is inventory only

Excel is allowed here only as ETABS exported input/model-definition evidence for table-name discovery, header/column discovery, future source-family discovery, live probe target refinement, check-engine readiness planning, and acceptance policy preparation.

Excel is forbidden as production source of truth, FeatureSnapshot source, CheckEngine input, engineering PASS/FAIL source, replacement for live ETABS, or stable source-contract promotion by itself.

## Source domains inventoried

The inventory groups possible source evidence across identity, material, beam, column, wall/pier, slab/area, story/global, modal, drift, loads/combos, design outputs, and foundations/soil domains.

## Story derived elevation policy

Story Definitions can provide Story/Name and Height. Tower and Base Story Definition can provide BSElev. Together these support a derived-elevation policy for later human review. A per-story Elevation direct column is not mandatory if derived elevation support is explicitly recorded and reviewed. Future promotion still requires exact live ETABS table proof.

## Wall/pier chain policy

Pier Section Properties can be direct geometry/material evidence when Story, Pier, width, and thickness columns exist. A literal Section column is not mandatory for Pier Section Properties if direct geometry exists.

Wall Object Connectivity, Wall Bays, Area Assigns - Pier Labels, Area Assigns - Sect Prop, Wall Property Def - Specified, and Area Section Props - Summary are supporting chain evidence. Alone they do not unlock wall/pier checks.

## Material properties policy

Material Properties - Basic Mechanical Properties, Concrete Data, and Rebar Data can identify raw material-property table/header candidates. Mechanical constants such as E1, G12, U12, Fc, Fy, or Fu are raw evidence only. Future promotion requires live exact table proof.

## Design/force semantic review policy

Design-output and force-result tables such as beam/column/wall design summaries, pier forces, frame forces, area forces, shell stresses, and joint reactions require semantic review. Excel export presence alone does not prove check semantics or envelope policy.

## Acceptance classes

The policy uses these planning classes only: VERIFIED_LIVE_CANDIDATE, EXCEL_EXPORT_EVIDENCE_ONLY, PARTIAL_CONTEXT_ONLY, NEEDS_LIVE_PROBE, SEMANTIC_REVIEW, and NOT_FOR_CHECK_UNLOCK.

## Merge blockers

C13.2-P3 remains blocked if live ETABS proof is not rerun after P3 hotfixes, if any output sets `safe_to_implement_checks_now` true, if any stable contract file changes, if FeatureResolver/CheckEngine/report renderer changes, if Excel evidence is treated as production input, or if an engineering verdict is created from Excel.

## P4 entry criteria

P4 can only be considered after C13.2-P3 live ETABS proof is rerun, material_properties is a verified live candidate, story_definitions is a verified live candidate with derived_elevation_supported true or explicit Elevation column, pier_section_properties is a verified live candidate with direct_section_geometry_present true, and no check unlock/stable promotion occurs without separate review.

## No checks unlocked

This add-on implements no checks, emits no CheckResult, creates no PASS/FAIL engineering verdicts, and does not promote stable contracts. `safe_to_implement_checks_now` remains false.
