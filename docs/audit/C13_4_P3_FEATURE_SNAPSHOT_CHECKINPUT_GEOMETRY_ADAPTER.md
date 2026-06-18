# C13.4-P3 FeatureSnapshot CheckInput Geometry Adapter

## 1. Sprint purpose

C13.4-P3 adds a narrow adapter that prepares typed geometry check execution inputs from already-resolved `FeatureSnapshot` data. The adapter targets only the accepted C13.4-P1 geometry checks:

- `column_geometry_min_dimension`
- `beam_geometry_min_width`
- `beam_geometry_min_depth`
- `beam_depth_width_ratio`

The sprint is an input-preparation slice. It does not add new engineering formulas or replace `MinimalCheckEngine`.

## 2. Adapter boundary

The adapter lives at:

```text
tbdy_engine/checks/input_adapter.py
```

Boundary rules:

- Input side: `FeatureSnapshot` or a simple mapping fixture used by tests.
- Output side: immutable typed `GeometryCheckInput` bundles.
- Execution side: current `MinimalCheckEngine.run_check(check_id, snapshot, coverage)` contract remains unchanged.

## 3. What the adapter does

The adapter:

- reads geometry features from an existing snapshot;
- validates required geometry feature availability;
- validates feature status is `RESOLVED`;
- validates required unit metadata is exactly `mm`;
- creates `CoverageRow` objects with geometry-only runnable coverage;
- preserves `FeatureEvidence` per required feature;
- returns `CheckInputBuildResult` containing typed inputs and typed preparation diagnostics.

## 4. What the adapter explicitly does not do

The adapter does not:

- read ETABS;
- read Excel;
- fetch table registry data;
- run combo policy;
- run section-state policy;
- select governing combinations;
- calculate flexure, shear, rebar, capacity design, SCWB, PMM, drift, or final building compliance;
- emit engineering verdict statuses;
- perform unit conversion;
- infer missing unit metadata.

## 5. Input/output contract

Primary API:

```python
def build_geometry_check_inputs_from_feature_snapshot(
    snapshot: FeatureSnapshot | Mapping[str, object],
) -> CheckInputBuildResult:
    ...
```

Executable output is always:

```python
GeometryCheckInput(
    check_id=...,
    component_id=...,
    component_type=...,
    story=...,
    section=...,
    required_features=...,
    snapshot=FeatureSnapshot(...),
    coverage=CoverageRow(...),
    evidence_by_feature=...,
)
```

The adapter does not return executable plain dictionaries.

## 6. Strict typing policy

The new production data contracts are frozen, slotted dataclasses:

- `GeometryCheckInput`
- `CheckInputBuildDiagnostic`
- `CheckInputBuildResult`

`GeometryCheckInput` is not a tuple payload. Mapping fixtures are accepted only at the function boundary and are normalized before executable inputs are produced.

## 7. Missing data behavior

Missing or non-executable feature data blocks only the affected check input.

Examples:

- missing `beam_depth_mm` blocks `beam_geometry_min_depth` and `beam_depth_width_ratio`;
- missing `beam_width_mm` blocks `beam_geometry_min_width` and `beam_depth_width_ratio`;
- unsupported component types produce no executable geometry input and return an `OUT_OF_SCOPE` preparation diagnostic.

The adapter emits input-preparation diagnostics only. It does not emit structural pass/fail results.

## 8. Unit policy

Required units:

| Feature | Required unit |
| --- | --- |
| `beam_width_mm` | `mm` |
| `beam_depth_mm` | `mm` |
| `column_width_mm` | `mm` |
| `column_depth_mm` | `mm` |

Wrong unit metadata, such as `cm`, blocks the affected check input. Missing unit metadata also blocks the affected check input. The adapter does not multiply, normalize, or infer units.

## 9. Evidence traceability policy

For each executable `GeometryCheckInput`, `evidence_by_feature` preserves the original `FeatureEvidence` objects for every required feature. The integration tests run:

```text
FeatureSnapshot
→ GeometryCheckInput
→ MinimalCheckEngine.run_check(input.check_id, input.snapshot, input.coverage)
→ CheckResult.evidence
```

and verify that `source_table`, `source_column`, `raw_value`, `normalized_value`, and `unit` remain present in the resulting `CheckResult.evidence` payload.

## 10. Legacy boundary statement

`input_adapter.py` imports only current pipeline contracts from:

- `tbdy_engine.coverage.models`
- `tbdy_engine.features.evidence`
- `tbdy_engine.features.snapshot`
- `tbdy_engine.features.value`

It does not import forbidden legacy/runtime/design paths. The existing legacy boundary audit scans `tbdy_engine/checks/*.py`, which includes `tbdy_engine/checks/input_adapter.py`.

## 11. Acceptance outputs

Required commands:

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_4_p1
pytest -q tests/c13_4_p2
pytest -q tests/c13_4_p3
```

Connector implementation note: this patch was authored through the GitHub connector. The sandbox environment could not clone GitHub because DNS resolution for `github.com` was unavailable, so these acceptance commands were not executed in this session. Actual local or CI outputs must be recorded before marking the PR ready for review.

Current recorded status:

| Command | Status |
| --- | --- |
| `python -m compileall -q tbdy_engine tools tests` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tbdy_engine/tools/validate_contract_constitution.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tools/audit_legacy_boundary.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p1` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p2` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p3` | NOT_RUN_IN_CONNECTOR_SESSION |
