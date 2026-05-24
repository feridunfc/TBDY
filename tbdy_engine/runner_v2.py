from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Set

from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.contracts.validator import EngineContractValidator
from tbdy_engine.runtime.module_cache import ModuleExecutionCache
from tbdy_engine.runtime.scheduler import RuntimeScheduler
from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.reports.json_reporter import JSONReporter
from tbdy_engine.reports.excel_reporter import ExcelReporter
from tbdy_engine.reports.action_summary import ActionSummaryBuilder


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
        self.cache = ModuleExecutionCache()
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

    def run(self) -> Dict[str, Any]:
        errors = self.validate()
        if errors:
            return {"status": "CONTRACT_ERROR", "errors": errors}

        scheduler = RuntimeScheduler(
            ctx=self.ctx,
            evaluations_config=self.configs["evaluations"],
            cache=self.cache,
            enabled_evaluation_ids=self.enabled_evaluation_ids(),
        )
        eval_results = scheduler.run_all()
        checks = self.check_adapter.adapt_all(eval_results)

        json_reporter = JSONReporter(write_history=True)
        excel_reporter = ExcelReporter(write_history=True)
        json_path = json_reporter.generate(checks, eval_results, runtime_catalog=self.runtime_catalog, output_path=str(self.report_dir / "engine_report.json"))
        excel_path = excel_reporter.generate(checks, eval_results, output_path=str(self.report_dir / "engine_report.xlsx"))
        actions = ActionSummaryBuilder().build(checks)

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
                "json": json_path,
                "json_snapshot": json_reporter.last_snapshot_path,
                "excel": excel_path,
                "excel_snapshot": excel_reporter.last_snapshot_path,
                "action_summary": actions,
            },
            "evaluation_errors": eval_results.get("errors", {}),
            "evaluation_skipped": eval_results.get("skipped", {}),
            "execution_order": eval_results.get("execution_order", []),
            "cache_stats": eval_results.get("cache_stats", {}),
        }


def run_engine_v2(ctx, contracts_dir=None, report_dir=None, include_legacy=False):
    return TBDYEngineV2(ctx=ctx, contracts_dir=contracts_dir, report_dir=report_dir, include_legacy=include_legacy).run()
