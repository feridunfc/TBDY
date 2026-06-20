# C13.5-P6.2 Numeric String Length-Unit Normalization

Status: IMPLEMENTED_ON_BRANCH_NOT_LOCALLY_VERIFIED

Branch:

```text
sprint/c13-5-p6-2-numeric-string-unit-normalization
```

## Scope

C13.5-P6.2 parses live ETABS concrete rectangular geometry dimensions when the locked table returns plain numeric strings and normalizes supported runtime ETABS present length units to the report unit `mm`.

This sprint uses the locked live geometry sources from `docs/audit/C13_5_LIVE_ETABS_GEOMETRY_SOURCE_LOCK.md`:

- Component type source: `Frame Assignments - Summary`
- Component type join key: `UniqueName`
- Component type column: `Type`, with existing fixture aliases preserved only inside the locked source boundary
- Section assignment source: `Frame Assignments - Section Properties`
- Section property column: `SectProp`
- Rectangular geometry source: `Frame Section Property Definitions - Concrete Rectangular`
- Section key column: `Name`
- Width column: `t2`
- Depth column: `t3`

## What changed

- Plain numeric geometry strings such as `0.4`, `0.87`, `1`, and `1.5` are parsed explicitly.
- Runtime source length unit is read from `SapModel.GetPresentUnits_2()` when display-table geometry values require runtime unit evidence.
- `SapModel.GetDatabaseUnits_2()` is preserved as secondary evidence.
- Supported ETABS length units are normalized to `mm` with the strict factor map:
  - `um -> 0.001`
  - `mm -> 1.0`
  - `cm -> 10.0`
  - `m -> 1000.0`
  - `in -> 25.4`
  - `ft -> 304.8`
- Every normalized geometry feature preserves:
  - `raw_value`
  - `raw_value_type`
  - `parsed_value`
  - `source_unit`
  - `target_unit`
  - `normalization_factor_to_mm`
  - `normalized_value`
  - `normalized_unit`
  - `present_units_raw`
  - `database_units_raw`
  - `source_table`
  - `source_column`

## Diagnostics

The implementation emits existing data-layer diagnostics only:

- `GEOMETRY_DIMENSION_VALUE_NOT_NUMERIC`
- `GEOMETRY_UNIT_EVIDENCE_MISSING`
- `GEOMETRY_UNIT_NORMALIZATION_UNSUPPORTED`

## What did not change

- No section name parsing.
- No B/C prefix inference.
- No dimension guessing.
- No table discovery or broad table hunting.
- No ETABS present-unit mutation.
- No engineering verdicts in the feature layer.
- No checks/product/UI/Excel production changes.

## Verification status

Local commands were not run in this connector session. The branch must be pulled locally and verified with:

```powershell
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_5_p6
pytest -q tests/c13_5_p5
pytest -q tests/c13_5_p6_2
python tools/run_offline_product_acceptance.py --out local_out/c13_5_p6_2_offline_acceptance
```

Live smoke was not run in this connector session.
