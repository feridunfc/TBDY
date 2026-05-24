# RELEASE_GATE.md

## TBDY_ENGINE v3.0 Release Gate

Release status: NOT READY

## Mandatory Gates

- [x] contracts validate with 0 errors
- [x] enabled DAG produces topological order
- [x] no circular dependency observed in current enabled DAG
- [ ] deterministic execution proven by golden suite
- [ ] cache correctness proven by tests
- [ ] reports generate exclusively from `reports.yaml`
- [ ] golden tests pass on v3-only production path
- [ ] coverage >=95%

## Architecture Exit Criteria

- [ ] single runtime
- [x] single enabled DAG observed in `runtime/dag.py`
- [x] single runtime cache object observed in `runner_v2.py`
- [ ] single reporting path
- [ ] golden suite passes

## Audit Scores

### ARCHITECTURE SCORE

6 / 10

Reason: target folders and runner_v2 path exist, but package export, tools pipeline, and reporting path still allow drift.

### DRIFT SCORE

7 / 10

Reason: legacy runner remains exported; legacy checks/registry still referenced by tests; final report tooling is a parallel reporting pipeline.

### PRODUCTION SCORE

5 / 10

Reason: tests pass and contracts validate, but release gates are incomplete.

### TECH DEBT

High.

Primary debt:

- legacy runtime still reachable
- report logic duplicated across reporters and tools
- production defaults include legacy enrichment
- no coverage gate evidence
- 45 unresolved legacy mapping warnings

## Blockers

1. `tbdy_engine/__init__.py` exports legacy `run` from `runner.py`.
2. `tests/test_sprint3_runner_full.py` imports and validates legacy runner behavior.
3. `tools/run_genesis_final_v1.py` creates a separate final pipeline after `engine_report.json`.
4. `tools/run_final_engine_report_v1.py` hardcodes final pipeline steps and report metadata.
5. `JSONReporter` and `ExcelReporter` hardcode report schemas/fields instead of consuming `reports.yaml` as source of truth.
6. `runner_v2.py` defaults to `include_legacy=True`.
7. 45 legacy mapping warnings remain.
8. Coverage >=95% is not demonstrated.

## Patch Plan

Smallest safe delta, no immutable core edits:

1. Patch package entry point so production import exposes v3 runtime explicitly.
2. Add production mode where `include_legacy=False` is the default.
3. Quarantine legacy tests under explicit marker.
4. Bind reporters to `reports.yaml`.
5. Move final report enrichment under the single v3 reporting path or mark tools as diagnostic-only.
6. Add DAG/cache/golden/coverage release commands.

Do not rewrite engineering modules.

## Final Release Authority

REJECT

Current status:

NOT READY
