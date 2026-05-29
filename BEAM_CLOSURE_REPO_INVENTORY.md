# BEAM_CLOSURE_REPO_INVENTORY

Task history:

- `REPO_RESET_FOR_BEAM_RUNTIME_CLOSURE`
- `SPRINT 1 — REPORT AMPUTATION`
- `SPRINT 1B — RUNNER / REPORT INTEGRATION SEAM`
- `SPRINT 2A — CANONICAL IMMUTABLE CHECKRESULT`
- `SPRINT 2B — ADAPTER DUMB-DOWN`
- `SPRINT 3A — ACTIVE BEAM EVALUATION PACKAGE`
- `SPRINT 3B — RUNNER TO PACKAGE SEAM`

Scope remains beam runtime closure preparation only. No real ETABS proof claimed. No ARCH-X touched. No contracts expanded.

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
- `tbdy_engine/design/beams/evaluation_package.py`
  - Sprint 3A active minimal `BeamEvaluationPackage` path.
  - Defines frozen `BeamEvaluationPackage` and `BeamCheckEvaluation`.
  - Defines `BeamDesignModule.run()` returning packages, not `CheckResult`.
  - Produces package-like checks for beam geometry, flexure, and shear from normalized/context-shaped beam metadata.
- `tbdy_engine/design/beams/__init__.py`
  - Exports active beam package API.
- `tbdy_engine/adapters/check_adapter.py`
  - Active CheckAdapter and canonical CheckResult definition path.
  - Sprint 2A converted `CheckResult` to `@dataclass(frozen=True)` with only canonical/allowed fields.
  - Sprint 2B converted `CheckAdapter` to translation-only package-to-CheckResult mapping.
- `tbdy_engine/reports/json_reporter.py`
  - Sprint 1 amputated to `JSONReporter().generate(check_results, output_path="engine_report.json")`.
  - Emits only `summary` and `checks`.
- `tbdy_engine/reports/excel_reporter.py`
  - Sprint 1 amputated to `ExcelReporter().generate(check_results, output_path="engine_report.xlsx")`.
  - Emits only `Summary` and `Checks` sheets.
- `tbdy_engine/reports/facade.py`
  - Sprint 1 amputated to `ReportingFacade(report_dir).generate(check_results)`.
  - Does not read runtime catalog or report contracts.
- `tbdy_engine/runner_v2.py`
  - Sprint 1B updated the runner/report seam to call `ReportingFacade(self.report_dir).generate(checks)`.
  - Sprint 3B preserves package tuple outputs from evaluators and flattens `eval_results["results"]` into `{"packages": [...]}` for `CheckAdapter.adapt_all`.
  - Return `reports` payload contains only `json` and `excel`.
- `tbdy_engine/contracts/checks.yaml`
  - Current check mapping source for beam check ids.
  - Kept active only as a compatibility map until the minimal beam closure path is made explicit.
- `tests/test_runner_v2_beam_package_seam.py`
  - Sprint 3B runner/package seam test.
- `tests/test_beam_evaluation_package_active.py`
  - Sprint 3A active package and dumb adapter compatibility test.
- `tests/test_check_adapter_dumb_mapping.py`
  - Sprint 2B dumb adapter mapping test and source guard.
- `tests/test_checkresult_canonical.py`
  - Sprint 2A canonical immutable CheckResult boundary test.
- `tests/test_reports_checkresult_only.py`
  - Sprint 1 report-only boundary test, updated to canonical fields in Sprint 2A.
- `tests/test_runner_v2_report_integration.py`
  - Sprint 1B runner/report seam test, updated to canonical fields in Sprint 2A.
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
  - Still imports `EngineContractLoader`, `EngineContractValidator`, `DatasetValidator`, `EvaluationDAG`, `RuntimeScheduler`.
  - Still returns `evaluation_errors`, `evaluation_skipped`, `execution_order`, `cache_stats` outside the report payload.
  - Report seam is fixed and package seam is now proven by unit test; scheduler/DAG cleanup remains out of scope.
- `tbdy_engine/contracts/checks.yaml`
  - Contains columns, SCWB, planned/full checks, hierarchy checks, report outputs, source files, experimental flags, runner enabled flags.
  - Beam closure should only require beam geometry/flexure/shear mapping.
- `tbdy_engine/contracts/evaluations.yaml`
  - Still points `BEAM_DESIGN` at legacy module path `tbdy_engine.design.beams.beam_module.BeamDesignModule`.
  - Not changed in Sprint 3B because contracts were forbidden.

## 4. Runtime imports still pointing to archived/drift paths

Confirmed current `runner_v2` drift/platform imports remain frozen:

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

Sprint 3B status: package tuple seam fixed/proven without removing scheduler/DAG.

## 6. Current report entrypoints

Sprint 1/1B/2A/2B/3A/3B status:

- `tbdy_engine/reports/facade.py`
  - `ReportingFacade.generate(check_results)`
- `tbdy_engine/reports/json_reporter.py`
  - `JSONReporter.generate(check_results, output_path="engine_report.json")`
- `tbdy_engine/reports/excel_reporter.py`
  - `ExcelReporter.generate(check_results, output_path="engine_report.xlsx")`

Reports are CheckResult-only and runner calls them with only `checks`.

## 7. Current CheckResult definition path

- `tbdy_engine/adapters/check_adapter.py`

Sprint 2A canonical shape:

```python
@dataclass(frozen=True)
class CheckResult:
    id: str
    component: str
    check_type: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    evidence: Mapping[str, object]
    messages: tuple[str, ...]
    story: str | None = None
    section: str | None = None
    unit: str | None = None
    code_ref: str | None = None
```

Status: canonical/frozen.

## 8. Current BeamEvaluationPackage definition path

- `tbdy_engine/design/beams/evaluation_package.py`

Sprint 3A active package shape:

```python
@dataclass(frozen=True)
class BeamCheckEvaluation:
    check_type: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    unit: str | None = None
    code_ref: str | None = None
    messages: tuple[str, ...] = ()

@dataclass(frozen=True)
class BeamEvaluationPackage:
    component: str
    checks: tuple[BeamCheckEvaluation, ...]
    evidence: Mapping[str, object]
    messages: tuple[str, ...] = ()
    story: str | None = None
    section: str | None = None
```

Status: active/minimal/frozen.

## 9. Current adapter definition path

- `tbdy_engine/adapters/check_adapter.py`
  - `CheckAdapter`
  - `CheckResult`

Sprint 2B status: translation-only package-like input to `CheckResult[]`.

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

Status: active candidate. It still outputs context-shaped material. Sprint 3A adds a package builder that can consume the normalized/context-shaped metadata, but live ETABS proof is not claimed.

## 11. Next sprint recommendation

Sprint 3C: contract/module path alignment or ETABS-to-package producer seam, depending on supervisor order.

Mechanical targets only:

1. Keep active `BeamEvaluationPackage` shape unchanged.
2. Keep canonical `CheckResult` unchanged.
3. Keep adapter dumb.
4. Keep reports CheckResult-only.
5. Do not touch ARCH-X.
6. Do not claim live ETABS proof unless explicitly validated.

Production claim: `BEAM_RUNTIME_CLOSURE = NOT CLAIMED`.
