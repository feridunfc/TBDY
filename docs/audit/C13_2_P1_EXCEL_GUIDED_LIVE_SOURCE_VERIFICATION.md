# C13.2-P1 — Excel-Guided Live ETABS Source Verification Gate

## Purpose

This sprint is a verification gate before any full contract/schema/feature catalog expansion.

Excel exports are used only to discover candidate ETABS table names, headers, aliases, and likely source families. Excel is not production input, not a FeatureSnapshot source, not a CheckEngine source, and never sufficient for `VERIFIED_LIVE`.

## Hard rule

`VERIFIED_LIVE` requires live ETABS proof:

- live ETABS connection succeeds
- candidate table is found/fetched live
- live headers are fetched
- expected header proof passes using alias-aware validation
- sample rows are fetched live, or a meaningful successful empty table is explicitly proven
- semantic meaning is safe

Design/force output sources remain `SEMANTIC_REVIEW` even when live headers and rows exist. They cannot unlock checks in this sprint.

## Added tool

```powershell
python tools/probe_excel_guided_live_contract_sources.py `
  --excel-inventory path/to/etabs_export.xlsx `
  --out local_out/c13_2_p1_excel_guided_live_probe `
  --live-etabs `
  --probe-profile verification_gate `
  --max-candidate-tables-per-family 3 `
  --max-sample-rows 50 `
  --preferred-output-case Crack_SeisY_UpSoil
```

Parse-only mode:

```powershell
python tools/probe_excel_guided_live_contract_sources.py `
  --excel-inventory path/to/etabs_export.xlsx `
  --out local_out/c13_2_p1_excel_inventory_parse_only
```

Parse-only mode must never produce `VERIFIED_LIVE`.

## Output artifacts

- `connection_report.json`
- `excel_inventory_parse_report.json`
- `excel_table_family_classification.json`
- `live_available_tables.json`
- `excel_to_live_table_match_report.json`
- `live_header_comparison_report.json`
- `live_sample_rows_report.json`
- `source_promotion_recommendation.json`
- `semantic_review_sources.json`
- `needs_live_probe_sources.json`
- `c13_2_expansion_decision_report.json`
- `C13_2_P1_EXCEL_GUIDED_LIVE_SOURCE_VERIFICATION.md`

## Profile behavior

`current_product` remains the safe default for the P0 tool. This P1 tool defaults to `verification_gate` because it requires explicit Excel inventory and is a verification gate, not a default live product probe.

Profiles:

- current_product
- column_geometry
- story_global
- material_context
- beam_design_outputs
- column_design_outputs
- wall_area
- verification_gate

## Column geometry gate

The report evaluates whether live evidence supports column geometry contract expansion:

- `Frame Assignments - Summary` has `Type == Column` rows
- column rows have `DesignSect`
- column `DesignSect` values match concrete rectangular section `Name`
- concrete rectangular section rows expose width/depth (`t2/t3` or aliases)

If passed, status is `VERIFIED_LIVE_FOR_COLUMN_GEOMETRY_CONTRACT`. This still does not implement checks.

## Current safe check capacity

The product remains limited to approximately five safe geometry/modal-report items:

- beam geometry width/depth/ratio style checks
- column geometry contract/report readiness
- modal cumulative UX/UY report verdict

No full TBDY expansion is unlocked.

## Still blocked

- rebar checks
- beam flexure
- beam shear
- capacity design
- column axial/PMM/shear
- wall checks
- story drift checks
- base shear checks

## Files intentionally not touched

- FeatureResolver
- CheckEngine
- catalogs
- schemas
- report renderer
- product checks
- Streamlit/apps/runtime/archx/runner_v2
