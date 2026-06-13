# C11.1.5 Validation Report

## Scope
C11.1.5 Constitution reporting + display-selection hardening only.
No C12, no legacy cleanup, no rebar/flexure/shear/capacity/UI/report-app/product packaging unlock.

## Changed files
- `tbdy_engine/checks/dry_run.py`
- `tbdy_engine/features/resolver/live_smoke.py`
- `tbdy_engine/providers/etabs_display_table_fetcher.py`
- `tools/probe_live_story_base_tables.py`
- `tests/c11_1_4/test_c11_1_4_full_resolver_rows.py`
- `tests/live_check_dry_run/test_c11_minimal_check_dry_run.py`

## Compile and contract constitution validation

```text
python -m compileall -q tbdy_engine tests tools
PASS
```

```text
python tbdy_engine/tools/validate_contract_constitution.py
Contract Constitution v1.0 C5.6 validation: OK
Catalogs: 12 | Schemas: 16 | Examples: 9
```

## Required pytest validation

```text
pytest tests/contracts -q
59 passed in 22.27s
```

```text
pytest tests/contracts/negative -q
33 passed in 17.79s
```

```text
pytest tests/canonical_tables -q
3 passed in 0.15s
```

```text
pytest tests/providers -q
12 passed in 3.02s
```

```text
pytest tests/features -q
21 passed in 5.27s
```

```text
pytest tests/coverage -q
21 passed in 14.92s
```

```text
pytest tests/audit -q
43 passed in 24.39s
```

```text
pytest tests/checks -q
34 passed in 0.29s
```

```text
pytest tests/golden -q
12 passed in 1.89s
```

```text
pytest tests/resolver_smoke -q
15 passed in 15.83s
```

```text
pytest tests/live_readiness -q
19 passed in 24.55s
```

```text
pytest tests/live_check_dry_run -q
22 passed in 2.22s
```

```text
pytest tests/modal_mass -q
10 passed in 16.74s
```

```text
pytest tests/c11_1_2 -q
19 passed in 18.97s
```

```text
pytest tests/c11_1_3 -q
10 passed in 21.80s
```

```text
pytest tests/c11_1_4 -q
45 passed in 22.67s
```

## Split suites due sandbox wrapper timeout

The following suites timed out only when run as one large command under the sandbox wrapper. They were split and every collected test passed.

### `tests/live_coverage`

Collected: 19 tests.

```text
pytest tests/live_coverage -q -k 'not deterministic and not tool_accepts'
17 passed, 2 deselected in 15.00s
```

```text
pytest tests/live_coverage/test_c9_live_coverage_matrix.py::test_c9_output_deterministic -q
1 passed in 11.07s
```

```text
pytest tests/live_coverage/test_c9_live_coverage_matrix.py::test_c9_tool_accepts_c8_probe_fixture_input -q
1 passed in 6.68s
```

Total: 19 / 19 passed.

### `tests/live_identity_geometry`

Collected: 62 tests.

Split execution proof:

```text
tests/live_identity_geometry/test_c8_1_identity_geometry_unit_fix.py chunks:
8 passed in 10.41s
8 passed in 8.44s
4 passed in 13.33s
2 passed in 4.58s
2 passed in 7.95s
8 passed in 22.38s
1 passed in 3.57s
```

```text
pytest tests/live_identity_geometry/test_c8_1_json_safe_serialization.py -q
9 passed in 7.80s
```

```text
tests/live_identity_geometry/test_c8_3_live_model_geometry_retrieval.py chunks:
6 passed in 7.49s
3 passed in 5.03s
3 passed in 11.89s
6 passed in 18.32s
2 passed in 7.65s
```

Total: 62 / 62 passed.

## C11.1.5 boundary dry-run acceptance

Command:

```text
python tools/run_c11_minimal_check_dry_run.py --feature-snapshot local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json --coverage-matrix local_out/c10_minimal_live_readiness/coverage_matrix.json --out local_out/c11_minimal_check_dry_run
```

Output:

```text
Wrote C11 minimal check dry-run outputs to local_out/c11_minimal_check_dry_run
```

Boundary subset:

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

Count match:

```text
check_results_summary.check_result_count = 3
len(check_results.json) = 3
c11_boundary_report.check_result_count = 3
```

## Contract/catalog/schema report
See `c11_1_5_contract_catalog_schema_report.json`.

Summary:

```text
feature_catalog_integrity: PASS
check_catalog_integrity: PASS
schema_integrity: PASS
boundary_constitution_integrity: PASS
c11_1_5_boundary_reporting_acceptance: PASS
display_selection_hardening_acceptance: PASS
```

## Display selection hardening result

- Uses list-only combo call path: `SetLoadCombinationsSelectedForDisplay([preferred_output_case])`.
- Uses list-only case call only as fallback if combo selection fails.
- Runtime does not use int overloads.
- Combo success skips case mutation by default.
- Story/base fetch happens after display selection.
- Default preferred output case remains `Crack_SeisY_UpSoil`.
- `--preferred-output-case` CLI is supported in smoke and probe scripts.

## Gate status

```text
go_for_C11_1_5_acceptance: true
go_for_legacy_cleanup: false
go_for_C12: false
go_for_rebar_flexure_shear: false
```
