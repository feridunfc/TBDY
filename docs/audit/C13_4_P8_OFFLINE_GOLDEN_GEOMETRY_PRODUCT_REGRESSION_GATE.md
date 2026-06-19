# C13.4-P8 Offline Golden Geometry Product Regression Gate

## 1. Sprint purpose

C13.4-P8 adds an offline golden regression gate for the geometry-only product slice. The gate runs the existing C13.4-P6 product smoke command, validates the generated bundle with the existing C13.4-P7 bundle validator, computes a path-normalized semantic fingerprint, and compares it against a committed golden baseline.

The purpose is to detect accidental product drift without ETABS.

## 2. Why this sprint is offline

P8 must run on a machine without ETABS. It does not fetch live model data, does not read Excel production input, and does not execute lower-level engineering checks directly.

P8 calls only:

- `run_geometry_product_smoke(...)`
- `validate_geometry_product_bundle(...)`

P8 does not call the lower FeatureSnapshot adapter, check engine, P4 runner, or P5 renderer directly.

## 3. Why golden fingerprint is path-normalized

P6 bundle outputs contain local paths such as:

- feature snapshot path;
- output directory;
- artifact directory;
- report path;
- summary path;
- manifest path.

Those paths differ across machines and temp directories. Comparing raw JSON or Markdown bytes would make the regression gate noisy and environment-dependent.

P8 therefore fingerprints product semantics only:

- P6 summary counts and status;
- P7 validation status and counts;
- CheckResult semantic rows;
- report title and table names;
- manifest guardrails.

Absolute paths and `local_out` paths are excluded from the fingerprint.

## 4. P6 reuse statement

P8 calls the existing product smoke API:

```python
run_geometry_product_smoke(
    feature_snapshot_path=feature_snapshot_path,
    output_dir=output_dir / "product_smoke",
)
```

P8 does not generate the product bundle manually.

## 5. P7 reuse statement

P8 calls the existing bundle validator API:

```python
validate_geometry_product_bundle(
    bundle_dir=output_dir / "product_smoke",
    validation_output_path=output_dir / "product_smoke" / "geometry_product_bundle_validation.json",
)
```

If P7 validation does not return `OK`, P8 fails.

## 6. Golden fingerprint contract

The committed golden fixture is:

```text
tests/fixtures/c13_4_p8/golden_geometry_product_fingerprint.json
```

It contains:

- `fingerprint_version: C13.4-P8.v1`
- `scope: GEOMETRY_ONLY_GOLDEN_REGRESSION`
- P6 product summary semantics;
- P7 validation semantics;
- sorted CheckResult semantic rows;
- report title;
- report table names;
- guardrails.

It does not contain paths, timestamps, full Markdown, or machine-specific data.

## 7. Actual fingerprint extraction rules

P8 reads the generated bundle:

```text
<out>/product_smoke/
```

Inputs used for fingerprint extraction:

```text
product_smoke_summary.json
product_smoke_manifest.json
geometry_product_bundle_validation.json
artifacts/check_results.json
reports/geometry_report.md
```

Extracted fields:

- P6:
  - `status`
  - `scope`
  - `p4.check_result_count`
  - `p4.adapter_diagnostic_count`
  - `p4.check_result_status_counts`
- P7:
  - `status`
  - `scope`
  - required file count
  - report table count
  - error count
- CheckResult rows:
  - `check_id`
  - `component_type`
  - `status`
  - `unit`
  - `value`
  - `limit`
- report:
  - title
  - table names in order
- guardrails:
  - manifest guardrails mapping

Check rows are sorted by:

1. component type;
2. check id;
3. status;
4. value;
5. limit.

## 8. Regression report contract

P8 writes:

```text
<out>/geometry_golden_regression_report.json
```

Required groups:

- `status`
- `scope`
- `feature_snapshot_path`
- `output_dir`
- `bundle_dir`
- `golden_fingerprint_path`
- `validation_path`
- `actual_fingerprint`
- `expected_fingerprint`
- `differences`
- `errors`
- `counts`

`status` is `OK` only if:

- P7 validation status is `OK`;
- actual fingerprint equals expected fingerprint;
- error count is zero;
- difference count is zero.

## 9. Difference reporting policy

P8 performs deterministic object comparison. If expected and actual fingerprints differ, P8 reports:

```text
Golden fingerprint mismatch
```

and stable top-level differences such as:

```text
Mismatch at key: checks
Mismatch at key: report
```

This is intentionally simple and stable for P8.

## 10. Determinism policy

P8 output is deterministic:

- fixed product bundle subdirectory name: `product_smoke`;
- fixed default report name: `geometry_golden_regression_report.json`;
- no timestamps;
- no random IDs;
- no raw full Markdown fingerprinting;
- no absolute paths inside the fingerprint;
- JSON outputs use `indent=2`, `sort_keys=True`, `ensure_ascii=False`, and final newline.

## 11. Legacy boundary statement

The P8 module is:

```text
tbdy_engine/product/golden_regression.py
```

It must not import:

- `tbdy_engine.design`
- `tbdy_engine.adapters.check_adapter`
- `tbdy_engine.engine.topology`
- `tbdy_engine.runtime`
- `tbdy_engine.runner_v2`
- `tbdy_engine.archx`

It must also not import or call:

- `MinimalCheckEngine`
- `build_geometry_check_inputs_from_feature_snapshot`
- direct P4 runner API
- direct P5 renderer API

The existing legacy boundary audit scans:

```text
tbdy_engine/product/*.py
```

P8 tests also inspect module and CLI source text for forbidden imports and lower-pipeline names.

## 12. Explicitly excluded engineering scope

P8 excludes:

- ETABS live fetching;
- Excel production input;
- Streamlit UI;
- direct FeatureResolver execution;
- direct P3 adapter execution;
- direct MinimalCheckEngine execution;
- direct CheckEngine execution;
- direct P4 runner execution;
- direct P5 report renderer execution;
- beam flexure;
- beam shear;
- rebar adequacy;
- capacity design;
- governing combo selection;
- force envelope selection;
- SCWB;
- column PMM;
- drift compliance;
- modal mass checks;
- column area checks;
- column aspect ratio checks;
- final building compliance verdict.

## 13. Acceptance outputs

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
python tools/run_geometry_golden_regression.py --feature-snapshot tests/fixtures/c13_4_p4/geometry_feature_snapshots.json --golden tests/fixtures/c13_4_p8/golden_geometry_product_fingerprint.json --out local_out/c13_4_p8_golden_regression
```

Connector implementation note: this patch was authored through the GitHub connector. Local acceptance commands were not executed in this session, so no PASS is claimed here.

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
| `pytest -q tests/c13_4_p5` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p6` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p7` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p8` | NOT_RUN_IN_CONNECTOR_SESSION |
| P8 golden regression CLI | NOT_RUN_IN_CONNECTOR_SESSION |
