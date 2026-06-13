# C10 Minimal Live Readiness Slice

C10 is a readiness-only smoke. It consumes a C8 `feature_snapshot.json` and an explicit design-context JSON, then rebuilds coverage readiness. It does not execute CheckEngine, emit CheckResult payloads, or produce engineering OK/FAIL verdicts.

Fixture mode:

```bash
python tools/build_minimal_live_readiness_slice.py \
  --feature-snapshot local_out/c8_feature_resolver_smoke/feature_snapshot.json \
  --design-context tests/fixtures/c10_design_context_fixture.json \
  --out local_out/c10_minimal_live_readiness
```

C9-output mode:

```bash
python tools/build_minimal_live_readiness_slice.py \
  --feature-snapshot local_out/c8_feature_resolver_smoke/feature_snapshot.json \
  --design-context tests/fixtures/c10_design_context_fixture.json \
  --coverage-input local_out/c9_live_coverage_matrix/coverage_matrix.json \
  --out local_out/c10_minimal_live_readiness
```

Optional manual live chain:

```bash
python tools/smoke_live_feature_resolver.py --out local_out/c8_feature_resolver_smoke --live-etabs
python tools/build_minimal_live_readiness_slice.py \
  --feature-snapshot local_out/c8_feature_resolver_smoke/feature_snapshot.json \
  --design-context local_inputs/design_context.json \
  --out local_out/c10_minimal_live_readiness
```

Manual design context example:

```json
{
  "ductility_class": "HIGH",
  "source": "manual_project_design_basis",
  "notes": "Provided manually for C10 readiness smoke only"
}
```

C10 never infers ductility class from ETABS table names or combo names. The value must be explicit and its provenance is written to `design_context_report.json`.

C10 deliberately unlocks only a minimal safe readiness slice. Rebar, flexure, shear, capacity-design, and force-demand rows remain non-runnable.
