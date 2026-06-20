# C13.5-P6.1 Design Type Column Alias Hotfix

## Purpose

C13.5-P6.1 recognizes the live ETABS spaced component type column alias:

```text
Design Type
```

This is a narrow hotfix for `Frame Assignments - Summary`. It does not add broad table hunting or fallback classification.

## User-provided live ETABS evidence

```yaml
table: "Frame Assignments - Summary"
columns:
  - Story
  - Label
  - UniqueName
  - Design Type
  - Length
  - Analysis Section
  - Design Section
  - Axis Angle
  - Max Station Spacing
  - Min Number Stations
  - Releases
  - User Offsets
values_seen:
  Design Type:
    - Beam
    - Column
    - Brace
    - Null
```

## Implementation

```yaml
added_alias:
  - "Design Type"
preserved_aliases:
  - DesignType
  - ComponentType
  - ObjectType
  - FrameType
  - MemberType
  - ElementType
  - LineObjectType
  - Classification
accepted_values:
  Beam: beam
  Column: column
unsupported_values:
  - Brace
  - Null
  - any other value
```

Unsupported values produce `COMPONENT_TYPE_VALUE_UNSUPPORTED`; they are not classified as beam or column.

## Scope audit

```yaml
scope_audit:
  broad_table_search_added: false
  CheckEngine_changed: false
  CheckResult_emitted: false
  section_name_parsing_added: false
  label_prefix_guessing_added: false
  unit_conversion_added: false
  product_smoke_auto_run_added: false
  design_type_spaced_alias_added: true
  live_smoke_claimed: false
```

## Acceptance status

Not run in this connector session. Required local commands:

```powershell
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_5_p6
pytest -q tests/c13_5_p5
python tools/run_offline_product_acceptance.py --out local_out/c13_5_p6_1_offline_acceptance
```

Expected:

```text
Offline product acceptance: OK
Commands: 18
Failed: 0
```

## Optional live smoke

Manual only:

```powershell
python tools/probe_live_etabs_geometry_snapshot.py `
  --live-etabs `
  --out local_out/c13_5_p6_1_live_design_type_alias_probe
```

No live smoke pass and no product smoke pass is claimed here.
