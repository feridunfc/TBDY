# C8 Local FeatureResolver Smoke

This smoke is manual/local only. CI does not require ETABS and does not run live ETABS checks.

Purpose: prove that live ETABS display-table data, or a captured table-header/sample fixture, can be resolved into `FeatureSnapshot` + `FeatureEvidence` data. It does **not** run `CheckEngine`, does **not** create `CheckResult`, and does **not** emit live engineering verdicts.

## Fixture mode

```bash
python tools/smoke_live_feature_resolver.py \
  --input tests/fixtures/c8_table_headers_fixture.json \
  --out local_out/c8_feature_resolver_smoke
```

## Manual live ETABS mode

Run only on a Windows machine with ETABS already open:

```bash
python tools/smoke_live_feature_resolver.py \
  --live-etabs \
  --out local_out/c8_feature_resolver_smoke \
  --max-rows 10
```

The script attaches to an already open ETABS model. It must not start ETABS, modify the model, run design, run checks, or produce `CheckResult` JSON.

## Outputs

- `feature_snapshot.json`
- `feature_resolution_report.json`
- `evidence_report.json`
- `missing_features_report.json`
- `coverage_preview.json`
- `legacy_alias_crosswalk_report.json`

`coverage_preview.json` contains readiness diagnostics only: `RUNNABLE`, `PARTIAL`, or `BLOCKED`. It is not a check result and contains no engineering verdict.
