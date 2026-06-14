# C12.0 Minimal Live Product Slice

C12.0 adds a single orchestration command for the accepted minimal vertical slice:

1. C8 live/fixture FeatureResolver smoke
2. C9 CoverageMatrix build
3. C10 minimal readiness slice with explicit design context
4. C11 minimal CheckEngine dry-run
5. Product slice manifest and acceptance summary

It does **not** add new engineering calculations. It does not unlock rebar, flexure,
shear, capacity design, UI, report app, product packaging, Excel production input,
or legacy runtime paths.

## Source baseline

```bash
git switch baseline/c11-1-8-clean-core
git pull
python tools/validate_clean_core_baseline.py
git switch -c <next-sprint-branch>
```

Baseline source of truth:

- repo: `feridunfc/TBDY`
- branch: `baseline/c11-1-8-clean-core`
- tag: `c11.1.8-clean-core`

## Live command

```bash
python tools/run_live_minimal_product_slice.py \
  --out local_out/c12_0_live_product_slice \
  --live-etabs \
  --target-component 297 \
  --target-label B1 \
  --target-story "+14.5" \
  --target-section B40x70 \
  --preferred-output-case Crack_SeisY_UpSoil \
  --design-context local_inputs/design_context.json
```

Live mode requires an already open ETABS model. It runs accepted live feature
resolution and then only the accepted minimal C11 dry-run checks.

## Fixture command

```bash
python tools/run_live_minimal_product_slice.py \
  --out local_out/c12_0_fixture_product_slice \
  --fixture-mode \
  --design-context tests/fixtures/c10_design_context_fixture.json
```

Fixture mode uses committed validation fixtures only and never calls live ETABS.

## Outputs

Under `--out` the command writes:

- `product_slice_manifest.json`
- `acceptance_summary.json`
- `feature_snapshot.json`
- `coverage_matrix.json`
- `feature_snapshot_with_context.json`
- `check_results.json`
- `c11_boundary_report.json`
- `baseline_guard_report.json`
- `command_log.json`

## Acceptance gate

The C12.0 product slice passes only when:

- baseline guard passes
- FeatureSnapshot schema remains valid
- ETABS Feature Source Contract remains valid
- legacy import audit is clean
- current resolved features remain covered 28/28
- C11 dry-run emits exactly three CheckResults
- C11 dry-run status is 3 OK, 0 FAIL
- no rebar/flexure/shear/capacity unlock occurs
- no Excel production path is used
- no Streamlit/UI path is used
- no legacy runtime path is used

## Locked scopes

Still locked until explicitly unlocked:

- C12.1+
- rebar
- flexure
- shear
- capacity design
- UI/report/product packaging
- Excel production path
- old archx/runtime/runner_v2/report paths
