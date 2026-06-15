# C13.2-P1 Semantic Promotion Hotfix

This hotfix tightens the Excel-guided live verification gate after a successful
live run exposed two over-permissive promotion recommendations.

## Problem

A live table being present is not enough for `VERIFIED_LIVE`.  The live source
must also prove the semantic source role requested by the `family_id`.

Two observed mismatches are explicitly blocked:

1. `material_properties`
   - Excel evidence may point to `Mat Prop - Basic Mech Props`.
   - A live match to `Material List by Story` is not valid proof of basic
     mechanical material properties such as `E1`, `G12`, `U12`, density/unit
     weight, or unit mass.
   - Result: `NEEDS_LIVE_PROBE` unless live headers prove basic mechanical
     material properties.

2. `frame_section_material_assignments`
   - Excel evidence may point to `Frame Prop - Summary`.
   - A live match to `Frame Assignments - Section Properties` proves object to
     section assignment only; it does not prove section-to-material mapping when
     the `Material` header is absent.
   - Result: `NEEDS_LIVE_PROBE` unless live headers include material mapping
     evidence.

## Added context-only families

The gate may still report context-only verified sources when semantically named:

- `material_list_by_story`
  - source role: `quantity_or_inventory_context_only`
  - check unlock: false

- `frame_section_assignments`
  - source role: `section_assignment_context_only`
  - check unlock: false

These families may help future contract planning but must not unlock checks.

## Promotion rule

`VERIFIED_LIVE` now requires all of the following:

- live mode is active
- the table is fetched live
- expected header validation passes
- sample rows are fetched
- semantic source-role validation passes
- design/force output tables are not involved

`KEYWORD_TABLE_HEADER_MATCH` cannot promote a family by itself.  Header proof and
semantic source-role proof must pass.

## Architecture guardrail

This remains a verification-gate sprint only:

- no catalog edits
- no schema edits
- no FeatureResolver edits
- no CheckEngine edits
- no report renderer edits
- no product check edits
- `safe_to_implement_checks_now: false`
- `full_c13_2_contract_expansion_now: false`

## Final micro-hotfix: frame section assignment vs material mapping

A live match to `Frame Assignments - Section Properties` with headers like
`Story`, `Label`, `UniqueName`, `Shape`, `AutoSelect`, `SectProp` must not promote
`frame_section_material_assignments` to `VERIFIED_LIVE`.

That table proves object-to-section assignment only. It does not prove
section-to-material mapping because `Material` is absent.

Final required behavior:

```yaml
frame_section_material_assignments:
  recommended_status: NEEDS_LIVE_PROBE
  can_expand_contract_now: false
  can_implement_check_now: false
  blocker: "live table proves section assignment, not material assignment; Material header missing"

frame_section_assignments:
  recommended_status: VERIFIED_LIVE
  source_role: section_assignment_context_only
  check_unlock_allowed: false
```

`c13_2_expansion_decision_report.json` must not list
`frame_section_material_assignments` under `verified_live_families`, and must list
it under `needs_live_probe_families` when only section assignment evidence exists.
