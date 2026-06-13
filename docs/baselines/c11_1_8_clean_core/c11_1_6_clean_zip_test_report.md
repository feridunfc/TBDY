# C11.1.6 Clean Zip Test Report

Clean-zip validation uses Option B: `tools/bootstrap_validation_fixtures.py`.

The bootstrap script uses committed fixtures only and does not call live ETABS. It materializes:

- `local_out/c8_feature_resolver_smoke/feature_snapshot.json`
- `local_out/c9_live_coverage_matrix/coverage_matrix.json`
- `local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json`
- `local_out/c10_minimal_live_readiness/coverage_matrix.json`
- `local_out/c11_minimal_check_dry_run/c11_boundary_report.json`

Required commands from a clean unzip:

```text
python -m compileall -q tbdy_engine tests tools
python tbdy_engine/tools/validate_contract_constitution.py
python tools/bootstrap_validation_fixtures.py
pytest tests/live_check_dry_run -q
```

Observed clean-zip result:

```text
compileall: PASS
contract validator: OK, Catalogs: 12 | Schemas: 17 | Examples: 10
bootstrap_validation_fixtures.py: PASS
pytest tests/live_check_dry_run -q: 25 passed
```

The full required suite set was also run in the working tree before packaging; timeout-sensitive suites were split as documented in `c11_1_6_validation_report.md`.

Result: `clean_zip_validation: PASS`.
