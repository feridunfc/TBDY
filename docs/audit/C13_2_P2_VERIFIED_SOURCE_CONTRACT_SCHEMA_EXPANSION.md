# C13.2-P2 Verified Live Source Contract + Schema Expansion

## Decision

```yaml
C13_2_P2_decision:
  do_contract_schema_expansion: true
  source_basis: C13_2_P1_VERIFIED_LIVE_only
  do_new_engineering_checks: false
  do_feature_resolver_runtime_changes: false
  do_check_engine_changes: false
  safe_to_implement_checks_now: false
```

This sprint is the first human-approved promotion from the C13.2-P1 Excel-guided live verification gate into stable contract files. It converts only human-reviewed `VERIFIED_LIVE` families into table/source/feature contracts.

Excel remains inventory and probe-planning evidence only. It is not a runtime source, FeatureSnapshot source, CheckEngine input, or production source of truth.

## Promoted VERIFIED_LIVE families

```yaml
verified_live_families_added:
  - frame_assignments_summary
  - concrete_rectangular_frame_sections
  - modal_participating_mass
  - story_drifts
  - story_max_over_avg_drifts
  - base_reactions
  - material_list_by_story
  - concrete_material_properties
  - rebar_material_properties
  - frame_section_assignments
  - frame_section_material_assignments
  - area_assignments_summary
  - wall_section_properties
  - pier_assignments
```

## Preserved blockers

```yaml
needs_live_probe_preserved:
  material_properties:
    reason: Material List tables do not prove E1/G12/U12/basic mechanical properties.
  pier_section_properties:
    reason: live/header/semantic proof incomplete.
  story_definitions:
    reason: live table headers did not fully prove expected story definition semantics.
```

## Semantic review preserved

```yaml
semantic_review:
  pier_forces:
    check_unlock_allowed: false
  design_outputs:
    status: SEMANTIC_REVIEW
    check_unlock_allowed: false
```

## Critical semantic distinctions

```yaml
frame_section_assignments:
  live_table_name: Frame Assignments - Section Properties
  source_role: section_assignment_context_only
  proves: frame object -> assigned section property
  does_not_prove: section property -> material mapping
  check_unlock_allowed: false

frame_section_material_assignments:
  live_table_name: Frame Section Property Definitions - Summary
  source_role: section_property_material_mapping
  required_columns:
    - Name
    - Material
    - Shape
  check_unlock_allowed: false

material_list_by_story:
  live_table_name: Material List by Story
  source_role: quantity_or_inventory_context_only
  check_unlock_allowed: false

material_properties:
  evidence_status: NEEDS_LIVE_PROBE
  source_role: basic_mechanical_material_properties
  must_not_use:
    - Material List by Story
    - Material List by Object Type
    - Material List by Section Prop
  check_unlock_allowed: false
```

## Current safe product capacity

```yaml
current_safe_check_capacity:
  current_safe_check_count: 5
  basis:
    - live verified frame identity
    - live verified rectangular section geometry
    - live verified modal mass
    - column Type and DesignSect mapping evidence
  conclusion:
    - current product is still geometry/modal-report limited
    - full TBDY is not unlocked
    - safe_to_implement_checks_now: false
```

## Still blocked check families

```yaml
blocked_check_families:
  rebar:
    reason: provided/required rebar semantics not reviewed for CheckEngine use
  beam_flexure:
    reason: moment envelope and rebar semantics require live + semantic review
  beam_shear:
    reason: shear demand/design output semantics require live + semantic review
  column_axial_pmm:
    reason: force/design summary/PMM semantics not verified for checks
  wall_checks:
    reason: area/pier/wall semantics not verified for engineering checks
  story_drift:
    reason: drift output-case/selection semantics not approved for check contract
  base_shear:
    reason: seismic/base-reaction semantics not approved for check contract
```

## Validation

Run:

```powershell
python -m compileall -q tbdy_engine tests tools
pytest tests/c13_2_p0 -q
pytest tests/c13_2_p1 -q
pytest tests/c13_2_p2 -q
pytest tests/contracts -q
pytest tests/c13_1 -q
pytest tests/c13_0 -q
python tools/validate_c13_2_p2_verified_source_contracts.py
```

Expected validator summary includes:

```yaml
safe_to_implement_checks_now: false
semantic_guardrail_errors: 0
cross_reference_errors: 0
```

## Backward Compatibility Hotfix

Applied after full repository contract tests exposed two compatibility regressions:

1. `table_registry.yaml` must preserve `metadata.version: "1.0"` because the existing Contract Constitution validator/schema treats this as an invariant.
2. Existing feature contracts still reference legacy table keys such as `frame_assignments`. P2 now preserves legacy keys as compatibility aliases instead of rewriting feature catalog semantics.

Compatibility aliases added:

```yaml
frame_assignments:
  compatibility_alias_for: frame_assignments_summary
frame_section_properties:
  compatibility_alias_for: concrete_rectangular_frame_sections
modal_results:
  compatibility_alias_for: modal_participating_mass
```

These aliases do not unlock engineering checks and are excluded from the promoted verified-live family count.


## Backward compatibility hotfix

C13.2-P2 preserves the existing Contract Constitution source-entry shape. Every
`etabs_feature_source_contract.yaml` source row keeps the legacy required fields:
`source_type`, `source_owner`, `row_selection_rule`, `evidence_required`, and
`display_selection_required`. New P2 fields are additive metadata only.

Legacy `feature_catalog.source.table_key` references are preserved through table
registry compatibility aliases, including `frame_assignments`,
`frame_section_properties`, `modal_results`, `material_concrete_data`,
`material_rebar_data`, and `wall_section_data`. These aliases do not increase the
C13.2-P2 promoted verified-live source count and keep `check_unlock_allowed: false`.


## C13.2-P2 legacy feature-id compatibility hotfix

The repository Contract Constitution validator requires every `etabs_feature_source_contract.yaml` `feature_id` to already exist in `feature_catalog.yaml`. Therefore C13.2-P2 does not introduce new dotted feature IDs such as `frame.unique_name` or `story_drift.value` unless they are first added to `feature_catalog` in a separate approved sprint.

This revision maps verified live source families only onto existing feature catalog feature IDs and keeps all new source evidence contract-only with `check_unlock_allowed: false`.


## Final Legacy Constitution Source Contract Hotfix

The existing `validate_contract_constitution` function has source-contract-specific invariants beyond JSON Schema.
This package preserves them without changing FeatureResolver, CheckEngine, renderer, or product checks:

- Story drift feature source rows now include `preferred_output_case_default: Crack_SeisY_UpSoil`.
- Base reaction rows explicitly set `identity_requirements.requires_story: false` and `requires_component_id: false`.
- Modal cumulative mass rows use `aggregation: max_cumulative` and forbid `fixed_mode_10_only`.
- Legacy beam geometry source contract rows remain `source_type: direct_api` and forbid `section_name_inference`; C13.2-P2 live table proof is additive metadata only.
- `safe_to_implement_checks_now` remains `false`; `promoted_verified_live_entries` remains `14`.

## C13.2-P2 Story Drift Legacy Invariant Hotfix

The existing Contract Constitution validator requires each of these source contract entries to carry the exact Story Drifts display-selection invariant:

- `story_drift_value`
- `story_drift_max_mm`
- `story_drift_output_case`
- `story_drift_direction`

Required fields are preserved in `etabs_feature_source_contract.yaml`:

```yaml
canonical_table_key: story_drifts
display_selection_required: true
preferred_output_case_default: Crack_SeisY_UpSoil
```

This is a compatibility hotfix only. It does not alter FeatureResolver, CheckEngine, report renderer, product logic, catalogs beyond the verified source contract package, or engineering check unlock state.



## Legacy direct_api schema invariant hotfix

The existing Contract Constitution schema requires `api_path` and `raw_fields` on `source_type: direct_api` feature source rows. C13.2-P2 preserves that legacy shape for `beam_length_mm`, `beam_width_mm`, and `beam_depth_mm`; this is source provenance metadata only and does not unlock checks.


## Direct API schema invariant hotfix

Existing Contract Constitution schema expects `api_path` to be an array, not a scalar string. Direct API source rows for `beam_length_mm`, `beam_width_mm`, and `beam_depth_mm` therefore keep `api_path` as ordered API-call arrays and `raw_fields` as raw API field arrays. No check unlock is introduced.
