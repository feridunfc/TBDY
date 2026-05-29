# BEAM_CLOSURE_REPO_INVENTORY

Task history:

- `REPO_RESET_FOR_BEAM_RUNTIME_CLOSURE`
- `SPRINT 1 — REPORT AMPUTATION`
- `SPRINT 1B — RUNNER / REPORT INTEGRATION SEAM`
- `SPRINT 2A — CANONICAL IMMUTABLE CHECKRESULT`

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
  - Active CheckAdapter and canonical CheckResult definition path.
  - Sprint 2A converted `CheckResult` to `@dataclass(frozen=True)` with only canonical/allowed fields.
  - Adapter inference remains intentionally not dumbed down until Sprint 2B.
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
  - Return `reports` payload now contains only `json` and `excel`.
- `tbdy_engine/contracts/checks.yaml`
  - Current check mapping source for beam check ids.
  - Kept active only as a compatibility map until the minimal beam closure path is made explicit.
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
  - Report seam is fixed; scheduler/DAG cleanup remains out of scope.
- `tbdy_engine/adapters/check_adapter.py`
  - `CheckResult` is canonical/frozen.
  - Adapter itself is still not dumb; it still indexes runtime catalog, extracts fields, infers source/evaluation level internally, and maps legacy evaluation payloads into canonical fields.
- `tbdy_engine/contracts/checks.yaml`
  - Contains columns, SCWB, planned/full checks, hierarchy checks, report outputs, source files, experimental flags, runner enabled flags.
  - Beam closure should only require beam geometry/flexure/shear mapping.

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

Sprint 1B status: report seam fixed. This is still a Genesis Runtime Bridge / scheduler/DAG composition root, not the final minimal boring beam runtime composition root.

## 6. Current report entrypoints

Sprint 1/1B/2A status:

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

Sprint 2B: Dumb CheckAdapter mapping.

Mechanical target only:

1. Keep canonical `CheckResult` unchanged.
2. Remove adapter inference and make it translation-only.
3. Do not import ARCH-X.
4. Do not change report boundary; reports must remain CheckResult-only.
5. Do not implement beam checks until adapter mapping is predictable.

Production claim: `BEAM_RUNTIME_CLOSURE = NOT CLAIMED`.
