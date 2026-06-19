# C13.5-P1 Column Geometry Vertical Slice

## 1. Sprint purpose

C13.5-P1 expands the existing geometry-only vertical slice with two explicit column geometry checks:

- `column_geometry_min_width`
- `column_geometry_min_depth`

The existing `column_geometry_min_dimension` check is preserved.

## 2. Why this sprint is geometry-only

The sprint evaluates only already-observed column section dimensions in millimeters. It does not read live ETABS, does not evaluate forces, and does not claim structural design adequacy.

## 3. New check IDs

```text
column_geometry_min_width: observed column_width_mm >= 300.0 mm
column_geometry_min_depth: observed column_depth_mm >= 300.0 mm
```

Both checks are explicit geometry checks. They use the same canonical CheckResult shape as the existing geometry slice.

## 4. New feature requirements

The modular C13.5-P1 feature overlay defines:

```text
column_width_mm
column_depth_mm
```

Both are column geometry features with required unit `mm`.

## 5. Unit policy

Required unit is exactly `mm`.

No conversion is allowed. A value in `cm` is not converted to `mm`; it is blocked by the adapter.

## 6. Missing data policy

Missing `column_width_mm` or `column_depth_mm` does not become a structural failure. The adapter produces diagnostics according to existing conventions:

- missing required feature -> `NO_DATA`
- non-resolved/invalid/wrong-unit feature -> `BLOCKED`

## 7. Wrong unit policy

Wrong unit is `BLOCKED` at adapter boundary. There is no silent unit conversion and no inferred value.

## 8. Adapter behavior

For a resolved column snapshot with `column_width_mm` and `column_depth_mm` in `mm`, the adapter now builds inputs for:

- `column_geometry_min_dimension`
- `column_geometry_min_width`
- `column_geometry_min_depth`

The adapter emits no `OK` or `FAIL` statuses.

## 9. Check engine behavior

The check layer emits `OK` or `FAIL` only for resolved executable inputs:

- `column_geometry_min_width`: `value >= 300.0`
- `column_geometry_min_depth`: `value >= 300.0`

Below-limit resolved geometry emits `FAIL` at the check layer only.

## 10. Report behavior

The 9 existing Markdown table names remain unchanged. The `column_geometry_detail` table now includes rows for:

- `column_geometry_min_dimension`
- `column_geometry_min_width`
- `column_geometry_min_depth`

No final building compliance verdict is emitted.

## 11. Bundle validator impact

The bundle validator remains structure-oriented and accepts the expanded bundle:

```text
check_result_count: 6
adapter_diagnostic_count: 0
report_table_count: 9
```

Existing invalid-status, invalid-report, malformed-artifact, guardrail, and forbidden-scope validations remain active.

## 12. Golden regression impact

The committed golden fingerprint now contains six checks:

```text
beam_depth_width_ratio
beam_geometry_min_depth
beam_geometry_min_width
column_geometry_min_depth
column_geometry_min_dimension
column_geometry_min_width
```

The fingerprint remains path-normalized and contains no timestamps or raw Markdown.

## 13. Offline acceptance gate impact

The P9 offline acceptance command plan now includes:

```bash
python -m pytest -q tests/c13_5_p1
```

The command is placed after C13.4-P8 tests and before the P8 golden regression command.

Expected offline acceptance command count is now 13.

## 14. Explicitly excluded engineering scope

Excluded from this sprint:

- ETABS live fetching;
- Excel production input;
- Streamlit UI;
- load combinations;
- reinforcement checks;
- capacity checks;
- column PMM;
- strong-column weak-beam;
- drift checks;
- modal mass checks;
- final building compliance verdict.

## 15. Acceptance outputs

Required commands:

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
python tools/run_geometry_product_smoke.py --feature-snapshot tests/fixtures/c13_4_p4/geometry_feature_snapshots.json --out local_out/c13_5_p1_product_smoke
python tools/validate_geometry_product_bundle.py --bundle-dir local_out/c13_5_p1_product_smoke
python tools/run_geometry_golden_regression.py --feature-snapshot tests/fixtures/c13_4_p4/geometry_feature_snapshots.json --golden tests/fixtures/c13_4_p8/golden_geometry_product_fingerprint.json --out local_out/c13_5_p1_golden_regression
python tools/run_offline_product_acceptance.py --out local_out/c13_5_p1_offline_acceptance
```

Connector implementation note: this patch was authored through the GitHub connector. Local acceptance commands were not executed in this session, so no PASS is claimed here.
