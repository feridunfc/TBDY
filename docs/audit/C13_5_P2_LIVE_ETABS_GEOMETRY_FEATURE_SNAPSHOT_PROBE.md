# C13.5-P2 Live ETABS Geometry FeatureSnapshot Probe

## 1. Sprint purpose

C13.5-P2 adds an explicit opt-in read-only live ETABS geometry probe that writes FeatureSnapshot JSON compatible with the existing geometry product pipeline.

The probe is for observed geometry only:

```text
beam_width_mm
beam_depth_mm
column_width_mm
column_depth_mm
```

No new engineering checks are added.

## 2. Why this is read-only

The probe reads observed geometry rows and serializes feature-layer data. It does not mutate the ETABS model, does not run check execution, and does not emit result-layer objects.

The probe output is data only:

```text
feature_snapshot.json
live_geometry_probe_summary.json
live_geometry_probe_diagnostics.json
live_geometry_probe_manifest.json
```

## 3. Why CI does not require ETABS

Live ETABS access is optional local smoke only. CI uses fake provider tests and the existing offline acceptance path.

The CLI refuses live probing unless the caller passes:

```bash
--live-etabs
```

Without this flag the CLI exits without attempting an ETABS connection.

The module is import-safe on machines without ETABS because COM import is isolated inside the live provider boundary.

## 4. FeatureSnapshot output contract

The probe writes:

```text
<out>/feature_snapshot.json
```

The JSON uses the existing wrapper shape:

```json
{
  "snapshots": [
    {
      "component_id": "B1",
      "component_type": "beam",
      "features": {
        "beam_width_mm": {
          "status": "RESOLVED",
          "value": 300.0,
          "unit": "mm",
          "semantic_role": "GEOMETRY",
          "evidence": []
        },
        "beam_depth_mm": {
          "status": "RESOLVED",
          "value": 600.0,
          "unit": "mm",
          "semantic_role": "GEOMETRY",
          "evidence": []
        }
      },
      "identity": {
        "label": "B1",
        "story": "+14.5",
        "section": "B40x70"
      }
    }
  ]
}
```

Column snapshots use:

```text
column_width_mm
column_depth_mm
```

## 5. Evidence/provenance policy

Resolved features require evidence. Evidence preserves:

```text
source_table
actual_table_name
source_column
source_row
raw_value
normalized_value
unit
resolver
evidence_status
```

The probe does not invent evidence. Missing values have empty evidence and corresponding diagnostics.

## 6. Unit policy

Required unit is exactly:

```text
mm
```

No conversion is allowed. The probe does not convert cm, m, inch, or any unproven unit to mm.

## 7. Missing data policy

If a required dimension is not present in the provider row, the feature is written as:

```text
status: MISSING
value: null
evidence: []
```

A `NO_DATA` diagnostic is emitted. Missing geometry never becomes a structural failure inside the probe.

## 8. Wrong unit policy

If the provider row reports a unit other than `mm`, the feature is written as non-executable feature-layer data and a `BLOCKED` diagnostic is emitted.

No converted value is written.

## 9. Optional live smoke command

Live ETABS smoke is manual and Windows-only:

```powershell
python tools/probe_live_etabs_geometry_snapshot.py --live-etabs --out local_out/c13_5_p2_live_geometry_probe
```

Do not claim this as passing unless it is actually run on a machine with ETABS open and accessible.

## 10. Existing product pipeline handoff command

The probe does not run product smoke automatically. The user may explicitly hand off the generated snapshot:

```powershell
python tools/run_geometry_product_smoke.py --feature-snapshot local_out/c13_5_p2_live_geometry_probe/feature_snapshot.json --out local_out/c13_5_p2_live_geometry_product_smoke
```

## 11. Explicitly excluded engineering scope

Excluded from this sprint:

- new engineering checks;
- flexure;
- shear;
- rebar;
- capacity design;
- SCWB;
- column PMM;
- drift;
- modal mass;
- load combination selection;
- force envelope selection;
- Excel production input;
- Streamlit UI;
- final building compliance verdict;
- implicit unit conversion;
- section-name parsing;
- deriving dimensions from labels;
- guessing missing width/depth;
- running check execution inside the probe;
- producing result-layer objects inside the probe.

## 12. Acceptance outputs

Required offline acceptance commands:

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_4_p1
pytest -q tests/c13_4_p2
pytest -q tests/c13_4_p3
pytest -q tests/c13_4_p4
pytest -q tests/c13_4_p5
pytest -q tests/c13_4_p6
pytest -q tests/c13_4_p7
pytest -q tests/c13_4_p8
pytest -q tests/c13_4_p9
pytest -q tests/c13_4_p10
pytest -q tests/c13_5_p1
pytest -q tests/c13_5_p2
python tools/run_offline_product_acceptance.py --out local_out/c13_5_p2_offline_acceptance
```

Expected final offline command output:

```text
Offline product acceptance: OK
Commands: 14
Failed: 0
```

Connector implementation note: this patch was authored through the GitHub connector. Local acceptance commands were not executed in this session, so no PASS is claimed here.
