# BEAM_CLOSURE_REPO_INVENTORY

Task: `REPO_RESET_FOR_BEAM_RUNTIME_CLOSURE`

Scope: repository preparation only. No beam checks implemented. No runtime behavior changed.

Source instruction: preserve old repo, create a reduced active working area, quarantine drift/platform paths, and prepare the next sprint for report amputation.

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
  - Current JSON reporter entrypoint.
  - Kept active for next sprint report amputation.
- `tbdy_engine/reports/excel_reporter.py`
  - Current Excel reporter entrypoint.
  - Kept active for next sprint report amputation.
- `tbdy_engine/reports/facade.py`
  - Current ReportingFacade entrypoint.
  - Kept active for next sprint report amputation.
- `tbdy_engine/contracts/checks.yaml`
  - Current check mapping source for beam check ids.
  - Kept active only as a compatibility map until the minimal beam closure path is made explicit.
- `tbdy_engine/runner_v2.py`
  - Current runner entrypoint/composition root candidate.
  - Suspicious: currently imports contracts, dataset validator, EvaluationDAG, RuntimeScheduler, runtime catalog, and passes eval_results/runtime_catalog into reports.
- `tests/test_etabs_beam_normalizer.py`
  - Minimal beam normalizer test candidate, identified from merged PR metadata.
- `tests/test_runner_v2_live_etabs_beams.py`
  - Opt-in live ETABS beam path test candidate, identified from merged PR metadata.

## 2. Archived files moved/quarantined

Physical source files were not moved in this preparation commit. Instead, branch-equivalent quarantine markers were created:

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

Archive meaning for next sprint: not imported by active runtime, not used by `runner_v2`, not used by reports, and not used by minimal beam/report tests.

## 3. Files still suspicious

- `tbdy_engine/runner_v2.py`
  - Imports `EngineContractLoader`, `EngineContractValidator`, `DatasetValidator`, `EvaluationDAG`, `RuntimeScheduler`.
  - Returns `evaluation_errors`, `evaluation_skipped`, `execution_order`, `cache_stats`.
  - Calls `ReportingFacade.generate(checks, eval_results, runtime_catalog=...)`.
- `tbdy_engine/reports/json_reporter.py`
  - Accepts `eval_results` and `runtime_catalog`.
  - Emits `runtime_bridge`, `report_contract`, `evaluation_errors`, `evaluation_skipped`, `execution_order`, `cache_stats`, `coverage`, `distributions`.
  - Writes history snapshots.
- `tbdy_engine/reports/excel_reporter.py`
  - Accepts `eval_results` and `planned_report`.
  - Emits `Eval_Skipped`, `Eval_Errors`, and `Report_Contract` sheets.
  - Writes history snapshots.
- `tbdy_engine/reports/facade.py`
  - Requires `runtime_catalog` and report planner/contract data.
  - Imports `ActionSummaryBuilder`, `ReportPlan`, `ReportPlanner`.
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

Current issue: this is still a Genesis Runtime Bridge / scheduler/DAG composition root, not the minimal boring beam runtime composition root.

## 6. Current report entrypoints

- `tbdy_engine/reports/facade.py`
  - `ReportingFacade.generate(checks, eval_results, *, runtime_catalog)`
- `tbdy_engine/reports/json_reporter.py`
  - `JSONReporter.generate(checks, eval_results, runtime_catalog=None, output_path="engine_report.json", planned_report=None)`
- `tbdy_engine/reports/excel_reporter.py`
  - `ExcelReporter.generate(checks, eval_results, output_path="engine_report.xlsx", planned_report=None)`

Current issue: reporters are not CheckResult-only.

## 7. Current CheckResult definition path

- `tbdy_engine/adapters/check_adapter.py`

Current shape is mutable:

```python
@dataclass
class CheckResult:
    check_id: str
    check_name: str
    evaluation: str
    status: str
    ratio: float = 0.0
    value: float = 0.0
    limit: float = 0.0
    unit: str = ""
    message: str = ""
    tbdy_ref: str = "N/A"
    evaluation_level: str = "NOT_EVALUATED"
    action: str = ""
    source: str = ""
    element_label: str = ""
    story: str = ""
    severity: str = "MEDIUM"
    category: str = "UNCATEGORIZED"
    report_section: str = ""
    experimental: bool = False
    runner_enabled: bool = True
    legacy_contract_id: str = ""
    legacy_canonical_check_name: str = ""
    governing_combo: str | None = None
    combo_family: str | None = None
    evidence: Any | None = None
```

Status: not canonical for target. Do not fully refactor in repo reset; prepare next sprint.

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

Sprint 1: Report Amputation.

Mechanical target only:

1. Change `ReportingFacade.generate(...)` to accept only `check_results`.
2. Change `JSONReporter.generate(...)` / `build_payload(...)` to accept only `check_results`.
3. Remove JSON payload fields:
   - `runtime_bridge`
   - `report_contract`
   - `evaluation_errors`
   - `evaluation_skipped`
   - `execution_order`
   - `cache_stats`
   - `coverage`
   - `distributions`
4. Change `ExcelReporter.generate(...)` to accept only `check_results`.
5. Remove Excel sheets:
   - `Eval_Skipped`
   - `Eval_Errors`
   - `Report_Contract`
6. Keep output filenames:
   - `engine_report.json`
   - `engine_report.xlsx`
7. Do not implement beam checks in Sprint 1.
8. Do not redesign `CheckResult` yet unless required for report-only boundary.

Production claim: `BEAM_RUNTIME_CLOSURE = NOT CLAIMED`.
