from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, Set

from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.contracts.validator import EngineContractValidator
from tbdy_engine.runtime.dataset_validator import DatasetValidator
from tbdy_engine.runtime.evaluation_dag import EvaluationDAG
from tbdy_engine.runtime.scheduler import EvaluationCallable, RuntimeScheduler, SchedulerResult
from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.reports.facade import ReportingFacade


def _model_to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    return dict(vars(obj)) if hasattr(obj, "__dict__") else {}


def _list_value(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


class TBDYEngineV2:
    """
    Genesis Runtime Bridge v1.1.
    Receives an already-built ModelContext and runs enabled evaluations from RuntimeCatalog.
    """

    def __init__(self, ctx: Any, contracts_dir: str | Path | None = None, report_dir: str | Path | None = None, include_legacy: bool = False) -> None:
        self.ctx = ctx
        self.contracts_dir = Path(contracts_dir or Path(__file__).parent / "contracts")
        self.report_dir = Path(report_dir or Path.cwd() / "reports_out")
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.include_legacy = include_legacy

        self.loader = EngineContractLoader(self.contracts_dir)
        self.bundle = self.loader.load(include_legacy=include_legacy)
        self.runtime_catalog = self.loader.build_runtime_catalog(include_legacy=include_legacy)
        self.configs = self.bundle.as_runtime_configs()
        self.check_adapter = CheckAdapter(self.runtime_catalog)

    def validate(self) -> list[str]:
        return EngineContractValidator(self.runtime_catalog).validate()

    def enabled_evaluation_ids(self) -> Set[str]:
        catalog = _model_to_dict(self.runtime_catalog)
        enabled = set()
        for _, check in (catalog.get("checks", {}) or {}).items():
            if not check.get("runner_enabled", True):
                continue
            ev = check.get("evaluation")
            if ev:
                enabled.add(ev)
        return enabled

    def _planned_check_ids(self) -> list[str]:
        checks = getattr(self.runtime_catalog, "checks", {}) or {}
        return sorted(
            check_id
            for check_id, check in checks.items()
            if getattr(check, "runner_enabled", True)
        )

    def _build_dry_run_report_contract(self) -> dict[str, object]:
        reports = getattr(self.runtime_catalog, "reports", {}) or {}
        report = reports.get("full_engine_report") if isinstance(reports, dict) else None
        if report is None:
            return {"report_id": "full_engine_report", "missing": True}
        return {
            "report_id": getattr(report, "report_id", "full_engine_report"),
            "formats": _list_value(getattr(report, "formats", [])),
            "sections": _list_value(getattr(report, "sections", [])),
            "include_fields": _list_value(getattr(report, "include_fields", [])),
            "metrics": _list_value(getattr(report, "metrics", [])),
        }

    def _runtime_warnings(self) -> list[str]:
        warnings: list[str] = []
        catalog_warnings = getattr(self.runtime_catalog, "warnings", [])
        for warning in _list_value(catalog_warnings):
            warnings.append(str(warning))
        return warnings

    def dry_run(self) -> dict[str, object]:
        contract_errors = self.validate()
        dataset_result = DatasetValidator.from_catalog(self.runtime_catalog).validate(self.ctx)
        dataset_validation = dataset_result.to_dict()
        dag = EvaluationDAG.from_catalog(self.runtime_catalog, enabled_only=True)
        enabled_evaluations = sorted(self.enabled_evaluation_ids())
        enabled_evaluation_set = set(enabled_evaluations)
        evaluation_order = [
            evaluation
            for evaluation in dag.topological_order(enabled_only=True)
            if evaluation in enabled_evaluation_set
        ]
        report_contract = self._build_dry_run_report_contract()
        warnings = self._runtime_warnings()

        for error in contract_errors:
            warnings.append(f"Contract validation: {error}")
        if report_contract.get("missing") is True:
            warnings.append("Report contract 'full_engine_report' is missing.")

        return {
            "ok": not contract_errors and dataset_result.ok,
            "dataset_validation": dataset_validation,
            "evaluation_order": evaluation_order,
            "enabled_evaluations": enabled_evaluations,
            "planned_checks": self._planned_check_ids(),
            "report_contract": report_contract,
            "warnings": [str(warning) for warning in warnings],
        }

    def _build_evaluators(self, catalog: object) -> dict[str, EvaluationCallable]:
        catalog_dict = _model_to_dict(catalog)
        catalog_evaluations = catalog_dict.get("evaluations", {}) or {}
        config_evaluations = (self.configs.get("evaluations", {}) or {}).get("evaluations", {}) or {}
        enabled_evaluations = self.enabled_evaluation_ids()
        evaluators: dict[str, EvaluationCallable] = {}

        for evaluation_name in sorted(enabled_evaluations):
            evaluation_config = _model_to_dict(catalog_evaluations.get(evaluation_name))
            if not evaluation_config:
                evaluation_config = _model_to_dict(config_evaluations.get(evaluation_name))
            if not evaluation_config.get("module"):
                continue
            evaluators[evaluation_name] = self._make_evaluator(evaluation_name, evaluation_config)

        return evaluators

    def _make_evaluator(self, evaluation_name: str, evaluation_config: Mapping[str, object]) -> EvaluationCallable:
        def evaluate(context: object) -> Mapping[str, object]:
            module_path = str(evaluation_config.get("module", "") or "")
            if not module_path:
                raise RuntimeError(f"No module configured for evaluation '{evaluation_name}'.")
            method_name = str(evaluation_config.get("method", "run") or "run")
            module_name, class_name = module_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            instance = cls(context)
            result = getattr(instance, method_name)()
            return _model_to_dict(result)

        return evaluate

    def _run_scheduler(self) -> SchedulerResult:
        dag = EvaluationDAG.from_catalog(self.runtime_catalog, enabled_only=True)
        evaluators = self._build_evaluators(self.runtime_catalog)
        scheduler = RuntimeScheduler(dag=dag, evaluators=evaluators)
        return scheduler.run(self.ctx)

    def run(self) -> Dict[str, Any]:
        errors = self.validate()
        if errors:
            return {"status": "CONTRACT_ERROR", "errors": errors}

        scheduler_result = self._run_scheduler()
        eval_results = scheduler_result.to_eval_results()
        checks = self.check_adapter.adapt_all(eval_results)

        reporting = ReportingFacade(self.report_dir).generate(
            checks,
            eval_results,
            runtime_catalog=self.runtime_catalog,
        )

        return {
            "status": "OK" if not eval_results.get("errors") else "PARTIAL",
            "summary": {
                "total_checks": len(checks),
                "ok": sum(1 for c in checks if c.status == "OK"),
                "fail": sum(1 for c in checks if c.status == "FAIL"),
                "warning": sum(1 for c in checks if c.status == "WARNING"),
                "no_data": sum(1 for c in checks if c.status == "NO_DATA"),
                "error": sum(1 for c in checks if c.status == "ERROR"),
            },
            "reports": {
                "json": reporting.json_report,
                "json_snapshot": reporting.json_snapshot,
                "excel": reporting.excel_report,
                "excel_snapshot": reporting.excel_snapshot,
                "action_summary": reporting.action_summary,
            },
            "evaluation_errors": eval_results.get("errors", {}),
            "evaluation_skipped": eval_results.get("skipped", {}),
            "execution_order": eval_results.get("execution_order", []),
            "cache_stats": eval_results.get("cache_stats", {}),
        }


def run_engine_v2(ctx, contracts_dir=None, report_dir=None, include_legacy=False):
    return TBDYEngineV2(ctx=ctx, contracts_dir=contracts_dir, report_dir=report_dir, include_legacy=include_legacy).run()
