# C13.5-P7 Live ETABS Geometry Product Orchestration

Status: IMPLEMENTED_ON_BRANCH_NOT_LOCALLY_VERIFIED

Branch:

```text
sprint/c13-5-p7-live-etabs-geometry-product-orchestration
```

## Goal

Provide one explicit live command that composes the existing pipeline:

```text
Attach to running ETABS
→ existing live geometry provider
→ existing live geometry FeatureSnapshot probe
→ exact generated FeatureSnapshot path
→ existing geometry product smoke
→ CheckResult/report/bundle artifacts
```

P7 is orchestration only. It does not duplicate probe, adapter, check, report, or product-smoke implementations.

## Production entry points

```text
tbdy_engine/product/live_geometry_product.py
tools/run_live_geometry_product.py
```

Required live command:

```powershell
python tools/run_live_geometry_product.py `
  --live-etabs `
  --out local_out/c13_5_p7_live_geometry_product
```

The CLI refuses execution without `--live-etabs` and does not create an output directory in that case.

## Output structure

```text
<out>/
  live_probe/
    feature_snapshot.json
    live_geometry_probe_summary.json
    live_geometry_probe_diagnostics.json
    live_geometry_probe_manifest.json

  product/
    artifacts/check_results.json
    artifacts/adapter_diagnostics.json
    artifacts/run_summary.json
    artifacts/run_manifest.json
    reports/geometry_report.md
    product_smoke_summary.json
    product_smoke_manifest.json

  live_geometry_product_summary.json
  live_geometry_product_manifest.json
```

The product stage receives the exact `live_probe/feature_snapshot.json` path. The orchestrator does not copy, normalize, or rewrite the FeatureSnapshot.

## Status contract

### FAIL

P7 returns `FAIL` when provider/attach creation fails, the probe fails, the FeatureSnapshot file is absent, snapshot count is zero, product smoke raises, product status is not `OK`, or required product artifacts are missing.

The product stage is not invoked when the probe fails or produces zero snapshots.

### PARTIAL

P7 returns `PARTIAL` only when the live probe is `PARTIAL`, at least one snapshot exists, and the existing product smoke completes with all required artifacts.

### OK

P7 returns `OK` only when the live probe is `OK`, snapshots exist, product smoke is `OK`, and all required product artifacts exist.

## Dependency injection boundary

Offline tests inject only three narrow seams:

```text
provider_factory
probe_runner
product_runner
```

There is no service container or generic orchestration framework. Offline tests do not connect to ETABS.

## Preserved evidence

The top-level summary reads and preserves live probe facts without inventing values:

- live probe status
- snapshot count
- probe diagnostic count
- resolved geometry row count
- feature status counts
- runtime length-unit source
- target report unit
- product CheckResult count
- product adapter diagnostic count
- relative probe/product/FeatureSnapshot paths

Unavailable evidence is represented as `null`.

## Guardrails

P7 does not add or modify:

- ETABS table discovery or registry scanning
- table-name guessing or source hunting
- `SetPresentUnits`
- a hard-coded runtime source unit
- section-name parsing
- `B40x70` dimension inference
- dimension guessing
- engineering formulas or thresholds
- check catalog or feature catalog content
- beam flexure or shear
- reinforcement adequacy
- capacity design
- strong-column weak-beam
- column PMM
- drift or modal mass checks
- Streamlit
- Excel production input

`tbdy_engine/features/live_etabs_geometry_probe.py` is not modified by P7.

## Verification ownership

Local compile, pytest, offline acceptance, and live ETABS smoke were not run in the implementation environment. The user owns local verification using the sprint acceptance commands.
