# C13.5-P6 Live Frame Component Type Resolution

## Purpose

C13.5-P6 resolves live ETABS frame component type from an explicit observed source so the accepted geometry mapping path can emit FeatureSnapshot rows without label or section-name guessing.

## Background

C13.5-P5.1 proved:

```yaml
COM_attach: OK
assignment_table_read: OK
property_table_read: OK
display_array_parser: OK
accepted_mapping_path_reached: true
previous_blocker: COMPONENT_TYPE_NOT_EXPLICIT
```

The remaining blocker was that assignment rows did not contain explicit beam/column evidence.

## Implemented model

```python
LiveFrameComponentTypeEvidence(
    unique_name: str,
    component_type: "beam" | "column",
    source_table: str,
    source_column: str,
    raw_row: Mapping[str, object],
    join_key_column: str,
)
```

Rules:

```yaml
component_type_values:
  accepted:
    - beam
    - column
  normalization:
    - case cleanup
    - whitespace cleanup
  forbidden:
    - label-prefix inference
    - section-name inference
    - object-name inference
    - B/C prefix inference
```

## Component type source discovery

The live probe checks bounded candidate source tables for explicit component type columns such as:

```yaml
candidate_columns:
  - ComponentType
  - ObjectType
  - FrameType
  - DesignType
  - MemberType
  - ElementType
  - LineObjectType
  - Classification
```

Accepted join key preference:

```yaml
preferred_join_key: UniqueName
allowed_join_keys:
  - UniqueName
  - unique_name
  - ObjectUniqueName
  - LineUniqueName
  - FrameUniqueName
  - ObjectID
  - LineObjectID
```

The implementation does not use label prefix, section name, story-only, section-only, or object-name parsing as fallback.

## Snapshot emission conditions

FeatureSnapshot rows are emitted only when all observed evidence exists:

```yaml
required_for_snapshot:
  - explicit assignment row
  - explicit section property row
  - explicit SectProp -> Name join
  - explicit beam/column component type evidence
  - explicit numeric t2/t3 geometry values
  - proven unit evidence as mm
```

Output features remain limited to:

```yaml
beam:
  - beam_width_mm
  - beam_depth_mm
column:
  - column_width_mm
  - column_depth_mm
```

## Summary fields

`live_geometry_probe_summary.json` now includes:

```yaml
component_type_source_table: string | null
component_type_source_status: string
component_type_source_row_count: integer
component_type_resolved_row_count: integer
component_type_unresolved_row_count: integer
assignment_table_row_count: integer
property_table_row_count: integer
resolved_geometry_row_count: integer
snapshot_count: integer
diagnostic_count: integer
```

## Diagnostics

P6 adds/uses:

```yaml
component_type_diagnostics:
  - COMPONENT_TYPE_SOURCE_TABLE_MISSING
  - COMPONENT_TYPE_SOURCE_TABLE_FETCH_FAILED
  - COMPONENT_TYPE_SOURCE_TABLE_EMPTY
  - COMPONENT_TYPE_SOURCE_TABLE_PARSE_EMPTY
  - COMPONENT_TYPE_SOURCE_COLUMN_MISSING
  - COMPONENT_TYPE_VALUE_UNSUPPORTED
  - COMPONENT_TYPE_JOIN_KEY_MISSING
  - COMPONENT_TYPE_JOIN_NOT_FOUND
  - COMPONENT_TYPE_NOT_EXPLICIT
```

`COMPONENT_TYPE_NOT_EXPLICIT` remains for rows that still lack explicit type evidence.

## Scope audit

```yaml
scope_audit:
  CheckEngine_changed: false
  CheckResult_emitted: false
  section_name_parsing_added: false
  label_prefix_guessing_added: false
  unit_conversion_added: false
  product_smoke_auto_run_added: false
  explicit_component_type_source_used: true
  live_smoke_claimed: false
```

## Files changed by sprint intent

```yaml
allowed_files_touched:
  - tbdy_engine/features/live_etabs_geometry_probe.py
  - tbdy_engine/product/offline_acceptance.py
  - tests/c13_4_p9/test_offline_product_acceptance.py
  - tests/c13_5_p5/test_live_geometry_snapshot_from_accepted_mapping_negative_cases.py
  - tests/c13_5_p6/test_live_frame_component_type_resolution.py
  - tests/fixtures/c13_5_p6/fake_assignment_rows.json
  - tests/fixtures/c13_5_p6/fake_property_definition_rows.json
  - tests/fixtures/c13_5_p6/fake_component_type_rows.json
  - docs/audit/C13_5_P6_LIVE_FRAME_COMPONENT_TYPE_RESOLUTION.md
```

## Acceptance status

Not run in the connector session.

Required local commands:

```powershell
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_5_p6
python tools/run_offline_product_acceptance.py --out local_out/c13_5_p6_offline_acceptance
```

Expected after local validation:

```text
Offline product acceptance: OK
Failed: 0
```

## Optional live smoke

Manual only:

```powershell
python tools/probe_live_etabs_geometry_snapshot.py `
  --live-etabs `
  --out local_out/c13_5_p6_live_component_type_probe
```

No live pass and no product smoke pass is claimed in this sprint until those commands are actually run.
