# C8.1 Live Identity / Geometry / Unit Normalization Smoke

This smoke is manual/local and opt-in. It reads an already open ETABS model only when `--live-etabs` is explicitly supplied. It never runs checks, never emits CheckResult JSON, never emits OK/FAIL verdicts, never modifies the ETABS model, and never starts a design run.

## Fixture mode used in CI

```bash
python tools/smoke_live_feature_resolver.py \
  --input tests/fixtures/c8_1_live_units_fixture.json \
  --out local_out/c8_1_live_identity_geometry_unit_fix
```

## Optional manual live ETABS mode

```bash
python tools/smoke_live_feature_resolver.py \
  --out local_out/c8_1_live_identity_geometry_unit_fix \
  --live-etabs \
  --target-component 297 \
  --target-label B1 \
  --target-story +14.5 \
  --target-section B40x70
```

If target arguments are omitted, the resolver seeds the target beam from the first valid row in `concrete_beam_design_summary`. The seeded identity is recorded as provenance and then checked against `Frame Assignments - Summary` when available.

## Unit policy

C8.1 records a `UnitContext` before normalizing engineering numeric values. In live ETABS mode, it attempts to read present/database units. In fixture mode, the fixture must declare units. If no unit context is available, engineering numeric features remain PARTIAL with `UNIT_CONTEXT_MISSING` / `UNIT_NORMALIZATION_UNVERIFIED` diagnostics rather than being silently labeled as MPa, mm, or mm2.

C8.1 does not call `SetPresentUnits` and does not mutate ETABS units.

## Required outputs

The smoke writes:

- `feature_snapshot.json`
- `feature_resolution_report.json`
- `evidence_report.json`
- `missing_features_report.json`
- `identity_resolution_report.json`
- `geometry_resolution_report.json`
- `unit_context_report.json`
- `unit_basis_report.json`
- `unit_normalization_report.json`
- `geometry_source_table_debug_report.json`
- `live_failure_delta_report.json`
- `coverage_preview.json`
- `c8_1_boundary_report.json`
- `legacy_alias_crosswalk_report.json`

## Next step gate

Run the manual live C8.1 smoke on the ETABS machine and inspect:

- `beam_width_mm` and `beam_depth_mm` are RESOLVED with FULL evidence from `frame_section_properties` / `t2` / `t3`.
- `modal_sum_ux` and `modal_sum_uy` are RESOLVED.
- `drift_torsion_semantic_lock` is preserved by source columns: `Drift` and `Ratio` remain separate.
- `CheckEngine_executed` is false.
- `CheckResult_emitted` is false.

Only after this manual retry passes should the C9/C10/C11 manual chain be rerun.
