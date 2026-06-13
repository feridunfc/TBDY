# C11.1.6 Validation Report — FeatureSnapshot Schema Contract

## Scope

C11.1.6 closes the C11.1.5 schema note by adding a standalone FeatureSnapshot schema contract. No legacy cleanup, C12, rebar, flexure, shear, capacity, UI, report app, or product packaging work was performed.

## Contract changes

- Added `tbdy_engine/catalogs/schemas/feature_snapshot.schema.json`.
- Added `tbdy_engine/catalogs/examples/feature_snapshot.example.json`.
- Registered FeatureSnapshot schema in the contract constitution validator and contract loader schema discovery.
- Added current accepted C8.3 resolver fixture: `tests/fixtures/feature_snapshot_c8_3_minimal_valid.json`.
- Added clean-zip bootstrap script: `tools/bootstrap_validation_fixtures.py`.

## Schema count

- Before: 16
- After: 17
- Example count after registration: 10

## FeatureSnapshot schema validation

PASS:

- `test_feature_snapshot_schema_exists`
- `test_current_c8_3_feature_snapshot_validates_against_schema`
- `test_feature_snapshot_schema_allows_current_resolver_evidence_payloads`

Negative rejection proof PASS:

- `test_feature_snapshot_schema_rejects_check_result_semantics`
- `test_feature_snapshot_schema_rejects_ok_fail_verdict_fields_inside_feature`
- `test_feature_snapshot_schema_rejects_status_from_counts`
- `test_feature_snapshot_schema_rejects_checkresult_status_as_feature_status`
- `test_feature_snapshot_schema_rejects_verdict_fields_inside_evidence`

## Contract validator output

```text
Contract Constitution v1.0 C5.6 validation: OK
Catalogs: 12 | Schemas: 17 | Examples: 10
```

## Full validation outputs

```text
python -m compileall -q tbdy_engine tests tools
PASS

python tbdy_engine/tools/validate_contract_constitution.py
Contract Constitution v1.0 C5.6 validation: OK
Catalogs: 12 | Schemas: 17 | Examples: 10

python tools/bootstrap_validation_fixtures.py
PASS; generated C8/C9/C10/C11 validation fixtures from committed fixtures only.
```

Required suite results:

```text
pytest tests/contracts -q
67 / 67 passed via split execution

pytest tests/contracts/negative -q
33 passed in 18.08s

pytest tests/canonical_tables -q
3 passed in 0.21s

pytest tests/providers -q
12 passed in 3.17s

pytest tests/features -q
21 passed in 5.32s

pytest tests/coverage -q
21 passed in 13.70s

pytest tests/audit -q
43 passed in 24.22s

pytest tests/checks -q
34 passed in 0.27s

pytest tests/golden -q
12 passed in 1.85s

pytest tests/resolver_smoke -q
15 passed in 16.39s

pytest tests/live_coverage -q
19 / 19 passed via split execution

pytest tests/live_readiness -q
19 passed in 22.87s

pytest tests/live_check_dry_run -q
25 passed in 7.27s

pytest tests/live_identity_geometry -q
62 / 62 passed via split execution

pytest tests/modal_mass -q
10 passed in 15.01s

pytest tests/c11_1_2 -q
19 passed in 18.18s

pytest tests/c11_1_3 -q
10 passed in 21.26s

pytest tests/c11_1_4 -q
45 passed in 23.33s
```

## Timeout / split proof

The sandbox command wrapper timed out on some long suite invocations even though tests were progressing. These suites were split and every collected test was run:

- `tests/contracts`: 67 collected; all 67 passed via per-file split execution.
- `tests/live_coverage`: 19 collected; first 18 passed in full run before wrapper timeout; final test `test_c9_tool_accepts_c8_probe_fixture_input` passed separately.
- `tests/live_identity_geometry`: 62 collected; all 62 passed via file/test-id chunk split execution.

One accidental no-argument pytest invocation occurred while preparing a split command and collected legacy top-level tests outside the required suite list; it is not part of the required C11.1.6 validation set.

## C11.1.6 boundary / bootstrap result

```json
{
  "live_etabs_called": false,
  "provider_called": false,
  "feature_resolver_called": false,
  "check_result_count": 3,
  "partial_rows_silent_OK": false,
  "rebar_selection_executed": false,
  "beam_flexure_executed": false,
  "beam_shear_executed": false
}
```

Counts match:

```text
check_results_summary.check_result_count = 3
len(check_results.json) = 3
c11_boundary_report.check_result_count = 3
```

## Gates

```yaml
acceptance_gate:
  feature_snapshot_schema_present: true
  current_feature_snapshot_validates: true
  check_result_semantics_rejected_inside_snapshot: true
  contract_validator: OK
  full_tests: PASS
  clean_zip_validation: PASS

go_for_C11_1_6_acceptance: true
go_for_legacy_cleanup: false
go_for_C12: false
go_for_rebar_flexure_shear: false
```
