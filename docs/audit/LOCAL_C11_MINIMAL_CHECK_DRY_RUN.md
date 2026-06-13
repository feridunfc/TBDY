# C11 Minimal Geometry / Global Check Dry Run

C11 is a fixture/manual-artifact dry run of the contract-safe MinimalCheckEngine. It does **not** call live ETABS, providers, feature resolvers, old runners, old beam modules, Excel production paths, Streamlit, PDF, runtime, or archx.

## Local fixture command

```bash
python tools/run_c11_minimal_check_dry_run.py \
  --feature-snapshot local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json \
  --coverage-matrix local_out/c10_minimal_live_readiness/coverage_matrix.json \
  --out local_out/c11_minimal_check_dry_run
```

## What C11 executes

Only these C10 RUNNABLE readiness rows are executed:

1. `beam_geometry_min_width`
2. `beam_depth_width_ratio`
3. `modal_mass_participation`

All BLOCKED rows and PARTIAL rows are skipped. Rebar, flexure, shear, capacity-design, force-demand, and selected/governing rebar rows remain locked.

## Outputs

```text
local_out/c11_minimal_check_dry_run/check_results.json
local_out/c11_minimal_check_dry_run/check_results_summary.json
local_out/c11_minimal_check_dry_run/skipped_coverage_rows_report.json
local_out/c11_minimal_check_dry_run/c11_boundary_report.json
local_out/c11_minimal_check_dry_run/manual_etabs_next_machine_instructions.md
```

## Later manual ETABS machine sequence

On the ETABS machine, a future operator may run the already-existing manual chain:

1. Run C8 feature resolver smoke in manual live mode.
2. Build C9 coverage matrix from that live C8 output.
3. Build C10 readiness slice from live C8/C9 outputs plus explicit `design_context.json`.
4. Only if the same three rows are RUNNABLE, run C11 dry-run against those artifacts.
5. Still do **not** run rebar, flexure, shear, force-demand, or full live ETABS-backed checks unless a later sprint explicitly unlocks them.

C11 itself does not run ETABS and does not mutate the ETABS model.
