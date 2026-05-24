# CURRENT_STATE.md

## Mode

AUDIT MODE

## Project

TBDY_ENGINE v3.0  
YAML-Driven DAG-Based Production Structural Evaluation Engine

## Audited Artifact

- Uploaded archive: `baseline_after_actual_combo_source_injection_v1_diagnostic.zip`
- Extracted audit root: `/mnt/data/audit_repo_norm`
- Audit date: 2026-05-24

## Repository State Evidence

### Repository Tree Summary

Present:

- `tbdy_engine/contracts/`
- `tbdy_engine/runtime/`
- `tbdy_engine/adapters/`
- `tbdy_engine/reports/`
- `tbdy_engine/runner_v2.py`
- `tbdy_engine/runner.py`
- `tools/`
- `tests/`
- `reports_out/`

### Git / Branch Status

Not available from uploaded diagnostic archive. The archive does not contain `.git`, so branch name, dirty state, and commit history cannot be verified.

### Contract Inventory

Observed contract counts:

- datasets: 7
- evaluations: 6
- checks: 23
- combo families: 5
- reports: 3

Contract validation result:

- errors: 0
- warnings: 45

The warnings are mostly legacy contract/checklist/combo usage items that do not map to runtime parent checks.

## Current Runtime State

`runner_v2.py` exists and follows the intended high-level path:

`runner_v2 -> RuntimeScheduler -> EvaluationDAG -> CheckAdapter -> JSONReporter / ExcelReporter`

However, production runtime is not yet singular because:

- `tbdy_engine/__init__.py` exports `run` from legacy `runner.py`.
- tests still reference legacy `tbdy_engine.runner`.
- `tools/run_genesis_final_v1.py` provides an additional final-report pipeline outside `runner_v2`.
- `tools/run_final_engine_report_v1.py` consumes existing `reports_out/engine_report.json` and mutates/enriches reporting outside `reports.yaml`.

## DAG State

Observed enabled evaluation IDs:

- `COLUMN_DESIGN`
- `BEAM_DESIGN`
- `SCWB_CHECK`

Observed DAG:

```text
COLUMN_DESIGN: []
BEAM_DESIGN: []
SCWB_CHECK: [COLUMN_DESIGN, BEAM_DESIGN]
```

Observed topological order:

```text
COLUMN_DESIGN -> BEAM_DESIGN -> SCWB_CHECK
```

No circular dependency observed in the current enabled DAG.

## Tests

Observed command:

```bash
PYTHONPATH=/mnt/data/audit_repo_norm pytest -q tests
```

Observed result:

```text
48 passed in 4.72s
```

Additional command:

```bash
PYTHONPATH=/mnt/data/audit_repo_norm python -m compileall -q tbdy_engine
```

Observed result:

```text
compileall_ok
```

Coverage was not provided or measured in the archive. The required `coverage >=95%` gate is therefore not satisfied.

## Last Successful Run Evidence

The archive contains `reports_out/genesis_final_summary.txt` showing:

- `ok: True`
- total checks: 4791
- source_empty: 0
- not_evaluated: 0

However, that run is a Genesis final pipeline run, not a strict v3 single-path production run. It uses report post-processing tools after `engine_report.json` generation.

## Known Failing Tests

None observed in the included test suite. But absence of failing tests does not mean production readiness because required v3 release gates are incomplete.

## Immutable Engineering Core Status

The archive contains files under immutable areas:

- `tbdy_engine/design/columns/*`
- `tbdy_engine/design/beams/*`
- `tbdy_engine/design/walls/*`
- `tbdy_engine/design/core/*`
- `tbdy_engine/engine/forces.py`
- `tbdy_engine/engine/topology.py`
- `tbdy_engine/etabs/*`

Because no git history was available, this audit cannot prove whether these files were modified relative to the protected baseline.

## Production Readiness

NOT READY
