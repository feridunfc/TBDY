# BEAM_CLOSURE_REPO_INVENTORY

Task history:

- `REPO_RESET_FOR_BEAM_RUNTIME_CLOSURE`
- `SPRINT 1 — REPORT AMPUTATION`

Scope remains beam runtime closure preparation only. No beam checks implemented. No ARCH-X touched. No contracts expanded.

## 1. Active files kept

Identified active/minimal beam closure candidates:

- `tbdy_engine/etabs/table_access.py`
  - Active ETABS table access boundary.
  - Reads one requested ETABS table through existing ETABS connection/table reader.
- `tbdy_engine/etabs/connection.py`
  - Active ETABS COM connection dependency used by table access.
- `tbdy_engine/etabs/table_reader.py`
  - Active low-level table DataFrame reader dependency used by table access.
- `tbdy_engine/etabs/normalizers/beam_design.py`
  - Active beam table normalizer candidate.
  - Contains beam design summary, flexure envelope, and shear envelope normalization.
- `tbdy_engine/adapters/check_adapter.py`
  - Current CheckAdapter and CheckResult definition path.
  - Kept active for now, but suspicious because CheckResult is mutable and carries legacy/runtime/report fields.
- `tbdy_engine/reports/json_reporter.py`
  - Sprint 1 amputated to `JSONReporter().generate(check_results, output_path="engine_report.json")`.
  - Emits only `summary` and `checks`.
- `tbdy_engine/reports/excel_reporter.py`
  - Sprint 1 amputated to `ExcelReporter().generate(check_results, output_path="engine_report.xlsx")`.
  - Emits only `Summary` and `Checks` sheets.
- `tbdy_engine/reports/facade.py`
  - Sprint 1 amputated to `ReportingFacade(report_dir).generate(check_results)`.
  - Does not read runtime catalog or report contracts.
- `tbdy_engine/contracts/checks.yaml`
  - Current check mapping source for beam check ids.
  - Kept active only as a compatibility map until the minimal beam closure path is made explicit.
- `tbdy_engine/runner_v2.py`
  - Current runner entrypoint/composition root candidate.
  - Still suspicious and expected to require integration after Sprint 1 because it still calls the old report API.
- `tests/test_reports_checkresult_only.py`
  - Sprint 1 report-only boundary test.
- `tests/test_etabs_beam_normalizer.py`
  - Minimal beam normalizer test candidate, identified from merged PR metadata.
- `tests/test_runner_v2_live_etabs_beams.py`
  - Opt-in live ETABS beam path test candidate, identified from merged PR metadata.

## 2. Archived files moved/quarantined

Physical source files were not moved in the repo reset preparation. Branch-equivalent quarantine markers exist:

- `_active/README.md`
- `_archive/README.md`

Paths/concepts to treat as archived/inactive for `BEAM_RUNTIME_CLOSURE`:

- `tbdy_engine/archx/**`
- `tbdy_engine/archx/runner.py`
- `tbdy_engine/archx/cli.py`
- `tbdy_engine/archx/demo.py`
- `tbdy_engine/archx/serialization.py`
- `tbdy_engine/archx/report_markdown.py`
- `tbdy_engine/archx/report_cli.py`
- `tbdy_engine/archx/workbench_bundle.py`
- `tbdy_engine/archx/providers/**`
- ARCH-X CheckResult/EvaluationPackage models
- workbench bundle code
- ARCH-X JSON artifact serializer
- ARCH-X markdown report path
- demo snapshot runner paths
- coverage analytics
- distribution analytics
- cache analytics exports
- execution history persistence
- report contract metadata
- generated contract artifacts
- backup contracts
- audit persistence
- generic governance/runtime platform layers

Archive meaning: not imported by active runtime, not used by `runner_v2`, not used by reports, and not used by minimal beam/report tests.

## 3. Files still suspicious

- `tbdy_engine/runner_v2.py`
  - Imports `EngineContractLoader`, `EngineContractValidator`, `DatasetValidator`, `EvaluationDAG`, `RuntimeScheduler`.
  - Returns `evaluation_errors`, `evaluation_skipped`, `execution_order`, `cache_stats`.
  - Still calls `ReportingFacade.generate(checks, eval_results, runtime_catalog=...)` and will need a later integration sprint.
- `tbdy_engine/adapters/check_adapter.py`
  - `CheckResult` is not frozen.
  - Contains fields outside the target minimal shape: `evaluation`, `check_name`, `evaluation_level`, `source`, `experimental`, `runner_enabled`, `legacy_contract_id`, `legacy_canonical_check_name`, `combo_family`, `governing_combo`.
- `tbdy_engine/contracts/checks.yaml`
  - Contains columns, SCWB, planned/full checks, hierarchy checks, report outputs, source files, experimental flags, runner enabled flags.
  - Beam closure should only require beam geometry/flexure/shear mapping.

## 4. Runtime imports still pointing to archived/drift paths

Confirmed current `runner_v2` drift/platform imports:

- `tbdy_engine.contracts.loader.EngineContractLoader`
- `tbdy_engine.contracts.validator.EngineContractValidator`
- `tbdy_engine.runtime.dataset_validator.DatasetValidator`
- `tbdy_engine.runtime.evaluation_dag.EvaluationDAG`
- `tbdy_engine.runtime.scheduler.RuntimeScheduler`
- `tbdy_engine.reports.facade.ReportingFacade`

Confirmed ARCH-X imports are self-contained under `tbdy_engine/archx/**`; they must not be imported by the active beam closure runtime.

## 5. Current runner entrypoints

- `tbdy_engine/runner_v2.py`
  - `TBDYEngineV2.run()`
  - `run_engine_v2(ctx, contracts_dir=None, report_dir=None, include_legacy=False)`

Current issue: this is still a Genesis Runtime Bridge / scheduler/DAG composition root, not the minimal boring beam runtime composition root. It also still expects the old report facade API.

## 6. Current report entrypoints

Sprint 1 status:

- `tbdy_engine/reports/facade.py`
  - `ReportingFacade.generate(check_results)`
- `tbdy_engine/reports/json_reporter.py`
  - `JSONReporter.generate(check_results, output_path="engine_report.json")`
- `tbdy_engine/reports/excel_reporter.py`
  - `ExcelReporter.generate(check_results, output_path="engine_report.xlsx")`

Reports are now prepared as CheckResult-only. Runner integration is not updated in this sprint by instruction.

## 7. Current CheckResult definition path

- `tbdy_engine/adapters/check_adapter.py`

Current shape is mutable and still not canonical for the final target. Do not fully refactor until the CheckResult sprint.

## 8. Current BeamEvaluationPackage definition path

No active `BeamEvaluationPackage` definition was found in the minimal runtime path.

Related but archived/drift path exists:

- `tbdy_engine/archx/evaluation.py`
  - Defines generic `EvaluationPackage`, `EvaluationOutput`, `EvaluationStep`, `EvaluationEvidence`.

Status: `BeamEvaluationPackage` is missing from active beam runtime and must be created or carved out in a later sprint without importing ARCH-X.

## 9. Current adapter definition path

- `tbdy_engine/adapters/check_adapter.py`
  - `CheckAdapter`
  - `CheckResult`

Status: active but not dumb/minimal yet.

## 10. Current ETABS beam normalizer path

- `tbdy_engine/etabs/normalizers/beam_design.py`

Identified functions:

- `normalize_beam_design_summary(df, *, source_table)`
- `normalize_beam_flexure_envelope(df, *, source_table)`
- `normalize_beam_shear_envelope(df, *, source_table)`
- `build_beam_context_from_tables(tables)`
- `group_beam_flexure_rows(rows)`
- `group_beam_shear_rows(rows)`
- `to_context_namespace(context)`

Status: active candidate. It still outputs context-shaped material rather than `BeamEvaluationPackage`.

## 11. Next sprint recommendation

Sprint 2: Runner/report integration seam.

Mechanical target only:

1. Update the current runner call site so it passes only `CheckResult[]` into `ReportingFacade.generate(check_results)`.
2. Do not reintroduce `eval_results`, `runtime_catalog`, report contracts, coverage, distributions, cache stats, history, or execution order into reports.
3. Keep scheduler/DAG frozen unless the supervisor explicitly authorizes removal.
4. Do not implement beam checks until the report boundary stays green.

Production claim: `BEAM_RUNTIME_CLOSURE = NOT CLAIMED`.
