# C13.4-P4 Geometry Vertical Slice Runner

## 1. Sprint purpose

C13.4-P4 adds a deterministic local artifact runner for the already-accepted geometry-only execution path:

```text
FeatureSnapshot-like JSON
→ C13.4-P3 GeometryCheckInput adapter
→ C13.4-P1 MinimalCheckEngine
→ canonical CheckResult JSON artifacts
```

The runner is a reproducible vertical slice for local fixtures. It does not add engineering checks.

## 2. Runner boundary

The runner module lives at:

```text
tbdy_engine/checks/geometry_vertical_slice.py
```

The CLI entry point lives at:

```text
tools/run_geometry_vertical_slice.py
```

The runner reads local JSON, calls existing geometry-only adapter and engine contracts, and writes JSON artifacts to a local output directory.

## 3. What the runner does

The runner:

- reads one local JSON FeatureSnapshot-like input file;
- supports the three documented input shapes: wrapper object, single snapshot object, and list of snapshot objects;
- loads `tbdy_engine/catalogs/check_catalog.yaml` or an explicitly provided catalog directory;
- calls `build_geometry_check_inputs_from_feature_snapshot(...)`;
- runs executable inputs through `MinimalCheckEngine.run_check(check_id, snapshot, coverage)`;
- writes `check_results.json`;
- writes `adapter_diagnostics.json`;
- writes `run_summary.json`;
- writes `run_manifest.json`;
- preserves input evidence into serialized CheckResult payloads;
- returns a typed `GeometryVerticalSliceResult`.

## 4. What the runner explicitly does not do

The runner does not:

- read ETABS;
- read Excel;
- fetch from live providers;
- fetch table registry data;
- run combo policy;
- run section-state policy;
- select force envelopes;
- select governing combinations;
- calculate beam flexure;
- calculate beam shear;
- calculate rebar adequacy;
- calculate capacity design;
- calculate SCWB;
- calculate column PMM;
- calculate drift compliance;
- produce final building compliance verdicts;
- execute legacy runtime/design paths;
- patch missing units or normalize dimensions.

## 5. Input JSON contract

Supported shapes are exactly:

### Shape A — wrapper object

```json
{
  "snapshots": [
    {
      "component_type": "beam",
      "component_id": "B1",
      "identity": {
        "story": "+14.5",
        "section": "B40x70"
      },
      "features": {}
    }
  ]
}
```

### Shape B — single snapshot object

```json
{
  "component_type": "beam",
  "component_id": "B1",
  "identity": {},
  "features": {}
}
```

### Shape C — list of snapshots

```json
[
  {
    "component_type": "beam",
    "component_id": "B1",
    "identity": {},
    "features": {}
  }
]
```

Unsupported broad or undocumented shapes raise a clear exception at module level or return nonzero from the CLI.

## 6. Output artifact contract

The runner writes exactly these P4 artifacts:

```text
check_results.json
adapter_diagnostics.json
run_summary.json
run_manifest.json
```

### check_results.json

An array of canonical `CheckResult` dictionary payloads. The runner uses `CheckResult.as_dict()` when available and preserves `CheckResult.evidence` as carried by the engine.

### adapter_diagnostics.json

An array of adapter diagnostic payloads containing:

- `check_id`
- `component_id`
- `component_type`
- `status`
- `reason`
- `missing_features`
- `invalid_features`
- `evidence_by_feature`

Adapter diagnostics do not contain engine decision statuses.

### run_summary.json

Deterministic run counts:

- `status`
- `snapshot_count`
- `executable_input_count`
- `check_result_count`
- `adapter_diagnostic_count`
- `check_result_status_counts`
- `check_id_counts`
- `component_type_counts`

`component_type_counts` counts input snapshots, not generated CheckResults.

### run_manifest.json

Run provenance:

- runner name;
- input path;
- input SHA-256;
- output directory;
- catalog directory;
- deterministic artifact file list;
- scope marker;
- forbidden-scope declaration.

## 7. Determinism policy

The runner is deterministic:

- snapshot processing follows input order;
- adapter input processing follows adapter output order;
- JSON files are written using `indent=2`, `sort_keys=True`, and UTF-8 encoding;
- summary count maps are sorted by key;
- artifact file list is fixed.

## 8. Missing data behavior

Missing or invalid geometry input remains an input-preparation diagnostic. The runner does not synthesize failed CheckResults.

Examples:

- missing `beam_depth_mm` produces adapter diagnostics for `beam_geometry_min_depth` and `beam_depth_width_ratio`;
- wrong `beam_width_mm` unit blocks `beam_geometry_min_width` and `beam_depth_width_ratio`;
- unsupported component types produce `OUT_OF_SCOPE` adapter diagnostics.

The run status remains `OK` when the runner completes normally, even if adapter diagnostics exist.

## 9. Unit policy

Unit validation remains owned by the C13.4-P3 adapter. The P4 runner does not:

- convert `cm` to `mm`;
- infer units from feature names;
- patch missing unit metadata;
- normalize feature values.

The runner passes FeatureSnapshot-like JSON payloads into the adapter and records the resulting diagnostics.

## 10. Evidence traceability policy

Input feature evidence is preserved into `check_results.json`. Tests verify that these evidence fields survive serialization:

- `source_table`
- `actual_table_name`
- `source_column`
- `source_row`
- `raw_value`
- `normalized_value`
- `unit`
- `resolver`

The runner does not replace evidence with summaries.

## 11. Legacy boundary statement

The new runner module imports only active pipeline contracts:

- `tbdy_engine.checks.engine`
- `tbdy_engine.checks.input_adapter`
- `tbdy_engine.checks.result`

The legacy boundary audit scans `tbdy_engine/checks/*.py`, so `tbdy_engine/checks/geometry_vertical_slice.py` is included. A P4 test also checks the CLI script text for forbidden legacy import paths.

## 12. Acceptance outputs

Required commands:

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_4_p1
pytest -q tests/c13_4_p2
pytest -q tests/c13_4_p3
pytest -q tests/c13_4_p4
python tools/run_geometry_vertical_slice.py --feature-snapshot tests/fixtures/c13_4_p4/geometry_feature_snapshots.json --out local_out/c13_4_p4_geometry_vertical_slice
```

Connector implementation note: this patch was authored through the GitHub connector. The sandbox environment cannot perform a local checkout or execute the repository test suite, so no acceptance PASS is claimed in this session.

Current recorded status:

| Command | Status |
| --- | --- |
| `python -m compileall -q tbdy_engine tools tests` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tbdy_engine/tools/validate_contract_constitution.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tools/audit_legacy_boundary.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p1` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p2` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p3` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p4` | NOT_RUN_IN_CONNECTOR_SESSION |
| CLI smoke command | NOT_RUN_IN_CONNECTOR_SESSION |
