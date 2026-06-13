# C11.1.8 Clean-Core Baseline Usage

## Remote baseline

- Repository: `feridunfc/TBDY`
- Baseline branch: `baseline/c11-1-8-clean-core`
- Baseline tag: `c11.1.8-clean-core`

This baseline is the source of truth for all future work after C11.1.8. Do not start a sprint from an older local ZIP, a stale feature branch, or an unverified local working tree.

## Locked scopes

The following remain locked until explicitly unlocked in a future sprint prompt:

- C12
- rebar
- flexure
- shear
- capacity design
- UI / report app / product packaging

Future work must preserve:

- FeatureSnapshot schema
- ETABS Feature Source Contract
- C11 minimal dry-run emitting exactly 3 OK CheckResults
- clean legacy import audit
- no Excel production path
- no active `archx`, `runtime`, or `runner_v2` path

## Start a future sprint branch

Always reset to the accepted remote baseline first:

```bash
git switch baseline/c11-1-8-clean-core
git pull
python tools/validate_clean_core_baseline.py
git switch -c <next-sprint-branch>
```

Example:

```bash
git switch baseline/c11-1-8-clean-core
git pull
python tools/validate_clean_core_baseline.py
git switch -c c11-1-9-next-sprint
```

## Baseline guard acceptance before work

Before changing code in any future sprint, `python tools/validate_clean_core_baseline.py` must report:

```yaml
compileall_passed: true
contract_validator_ok: true
bootstrap_validation_fixtures_passed: true
legacy_import_audit_clean: true
feature_snapshot_schema_valid: true
etabs_feature_source_contract_valid: true
current_resolved_features_covered_count: 28
current_resolved_features_count: 28
c11_check_result_count: 3
c11_ok_count: 3
c11_fail_count: 0
rebar_flexure_shear_capacity_unlocked: false
baseline_guard_passed: true
```

The guard writes its detailed report to:

```text
local_out/c11_1_9_baseline_guard/baseline_guard_report.json
```

If the guard fails, stop and repair the baseline before starting any feature work.
