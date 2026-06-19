# C13.5-P5 Live Geometry FeatureSnapshot From Accepted Mapping

## 1. Sprint purpose

C13.5-P5 consumes the accepted C13.5-P4 geometry mapping and emits live geometry FeatureSnapshot rows from observed ETABS table values. It only touches the live provider / FeatureSnapshot generation boundary.

## 2. P4 accepted mapping result

The accepted mapping is explicit-column only:

```yaml
property_table_key: Frame Section Property Definitions - Concrete Rectangular
width_column: t2
depth_column: t3
mapping_basis: explicit_columns_only
```

## 3. Join policy

The P5 join policy is:

```yaml
assignment_table: Frame Assignments - Section Properties
assignment_section_column: SectProp
property_table: Frame Section Property Definitions - Concrete Rectangular
property_name_column: Name
join: SectProp -> Name
```

`t2` maps to width and `t3` maps to depth. The values must be observed numeric table values.

## 4. FeatureSnapshot output policy

Resolved rows are transformed into FeatureSnapshot entries only for explicit beam/column component types. The emitted feature IDs are:

```yaml
beam:
  - beam_width_mm
  - beam_depth_mm
column:
  - column_width_mm
  - column_depth_mm
```

If the component type is not explicit in the assignment row, the probe emits a diagnostic and does not guess from label text.

## 5. Evidence/provenance requirements

Each resolved feature value preserves source evidence through the FeatureEvidence source row, including:

```yaml
provider: ETABS_LIVE
source_table_assignment: Frame Assignments - Section Properties
source_table_property: Frame Section Property Definitions - Concrete Rectangular
assignment_section_column: SectProp
property_name_column: Name
width_column: t2
depth_column: t3
story: observed Story
label: observed Label
unique_name: observed UniqueName
section_name: observed SectProp / Name
mapping_basis: explicit_columns_only
```

The feature evidence `source_column` is the explicit property-table source column (`t2` or `t3`), not a derived feature name.

## 6. Missing data diagnostic policy

The provider does not guess. It emits diagnostics and no resolved row for:

```yaml
- missing accepted mapping
- missing assignment table rows
- missing property table rows
- missing SectProp assignment column
- missing Name property column
- unmatched SectProp -> Name
- missing t2/t3
- non-numeric t2/t3
- unit not proven as mm
- component type not explicit
```

## 7. Why section-name parsing remains forbidden

Section labels such as `B40x70` or `C40x50` are never parsed. They are used only as opaque join keys between `SectProp` and `Name`.

## 8. Why unit conversion remains forbidden

P5 emits values only when the observed table row proves `unit: mm` or matching `t2_unit/t3_unit: mm`. It does not convert cm, m, or any other unit to mm.

## 9. Why CheckEngine / CheckResult are not touched

P5 remains in the feature layer:

```text
ETABS Live Provider -> FeatureSnapshot
```

It does not run checks, does not emit engineering pass/fail decisions, and does not change check thresholds or product smoke semantics.

## 10. Offline acceptance result

Connector implementation session status:

```yaml
implemented:
  - AcceptedGeometryMapping contract
  - accepted mapping row provider
  - assignment/property row join resolver
  - FeatureSnapshot output from explicit t2/t3 mapping
  - provenance/evidence preservation
  - missing data diagnostics
  - fake fixture tests
  - hidden CLI fixture mode for tests
  - P9 offline acceptance update to include tests/c13_5_p5
  - command count update to 17

not_run_in_connector_session:
  - python -m compileall -q tbdy_engine tools tests
  - python tbdy_engine/tools/validate_contract_constitution.py
  - python tools/audit_legacy_boundary.py
  - pytest -q tests/c13_4_p1
  - pytest -q tests/c13_4_p2
  - pytest -q tests/c13_4_p3
  - pytest -q tests/c13_4_p4
  - pytest -q tests/c13_4_p5
  - pytest -q tests/c13_4_p6
  - pytest -q tests/c13_4_p7
  - pytest -q tests/c13_4_p8
  - pytest -q tests/c13_4_p9
  - pytest -q tests/c13_4_p10
  - pytest -q tests/c13_5_p1
  - pytest -q tests/c13_5_p2
  - pytest -q tests/c13_5_p3
  - pytest -q tests/c13_5_p4
  - pytest -q tests/c13_5_p5
  - python tools/run_offline_product_acceptance.py --out local_out/c13_5_p5_offline_acceptance
```

Expected local acceptance after validation:

```text
Offline product acceptance: OK
Commands: 17
Failed: 0
```

## 11. Optional live ETABS smoke command

Manual only, not CI:

```powershell
python tools/probe_live_etabs_geometry_snapshot.py --live-etabs --out local_out/c13_5_p5_live_geometry_probe
```

If FeatureSnapshot rows are produced, the product smoke may then be run manually:

```powershell
python tools/run_geometry_product_smoke.py `
  --feature-snapshot local_out/c13_5_p5_live_geometry_probe/feature_snapshot.json `
  --out local_out/c13_5_p5_live_geometry_product_smoke
```

No live or product smoke pass is claimed unless those commands actually run.

## 12. Next sprint expectation

The next sprint can inspect real live diagnostics and decide whether missing live rows are caused by component-type evidence, unit evidence, table access, or model content. It must still avoid section-name parsing, unit conversion, and geometry guessing.
