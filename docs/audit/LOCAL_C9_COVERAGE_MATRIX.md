# C9 Live Coverage Matrix Readiness Smoke

C9 builds coverage/readiness outputs from a C8 FeatureSnapshot. It is a diagnostic layer only.
It does not execute CheckEngine, does not emit CheckResult JSON, and does not produce engineering verdicts.

## Fixture mode from C8 FeatureSnapshot

```bash
python tools/build_live_coverage_matrix.py \
  --feature-snapshot local_out/c8_feature_resolver_smoke/feature_snapshot.json \
  --out local_out/c9_live_coverage_matrix
```

## Fixture mode directly from C8 table header probe fixture

```bash
python tools/build_live_coverage_matrix.py \
  --c8-probe-input tests/fixtures/c8_table_headers_fixture.json \
  --out local_out/c9_live_coverage_matrix
```

## Optional local/live chain

Run C8 manually on a Windows machine with ETABS already open, then run C9 from the resulting FeatureSnapshot:

```bash
python tools/smoke_live_feature_resolver.py --out local_out/c8_feature_resolver_smoke --live-etabs
python tools/build_live_coverage_matrix.py \
  --feature-snapshot local_out/c8_feature_resolver_smoke/feature_snapshot.json \
  --out local_out/c9_live_coverage_matrix
```

CI does not require ETABS. Coverage status means readiness only: RUNNABLE/BLOCKED/PARTIAL is not an engineering verdict.
