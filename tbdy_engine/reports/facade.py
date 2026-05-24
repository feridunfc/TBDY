from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from tbdy_engine.reports.action_summary import ActionSummaryBuilder
from tbdy_engine.reports.excel_reporter import ExcelReporter
from tbdy_engine.reports.json_reporter import JSONReporter
from tbdy_engine.reports.report_plan import ReportPlan, ReportPlanner


@dataclass(frozen=True)
class ReportingResult:
    json_report: str
    json_snapshot: str | None
    excel_report: str | None
    excel_snapshot: str | None
    action_summary: list[dict[str, Any]]


class ReportingFacade:
    def __init__(self, report_dir: str | Path):
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        checks: Sequence[Any],
        eval_results: dict[str, Any],
        *,
        runtime_catalog: Any,
    ) -> ReportingResult:
        report_plan = self._build_report_plan(runtime_catalog)
        self._validate_report_plan(report_plan)
        full_engine_report = report_plan.get("full_engine_report")

        json_reporter = JSONReporter(write_history=True)
        excel_reporter = ExcelReporter(write_history=True)

        json_path = json_reporter.generate(
            checks,
            eval_results,
            runtime_catalog=runtime_catalog,
            output_path=str(self.report_dir / "engine_report.json"),
            planned_report=full_engine_report,
        )
        excel_path = excel_reporter.generate(
            checks,
            eval_results,
            output_path=str(self.report_dir / "engine_report.xlsx"),
        )
        actions = ActionSummaryBuilder().build(checks)

        return ReportingResult(
            json_report=json_path,
            json_snapshot=json_reporter.last_snapshot_path,
            excel_report=excel_path,
            excel_snapshot=excel_reporter.last_snapshot_path,
            action_summary=actions,
        )

    def _build_report_plan(self, runtime_catalog: Any) -> ReportPlan:
        reports = getattr(runtime_catalog, "reports", None)
        if reports is None and isinstance(runtime_catalog, dict):
            reports = runtime_catalog.get("reports")
        if reports is None:
            raise ValueError("Runtime catalog does not provide reports contract data")
        return ReportPlanner(reports).plan()

    def _validate_report_plan(self, report_plan: ReportPlan) -> None:
        reports = report_plan.reports
        if "full_engine_report" not in reports:
            raise ValueError("reports.yaml must define full_engine_report")
        if "action_summary" not in reports:
            raise ValueError("reports.yaml must define action_summary")

        full_engine_report = report_plan.get("full_engine_report")
        if "json" not in full_engine_report.formats:
            raise ValueError("full_engine_report must declare json format")
        if "excel" not in full_engine_report.formats:
            raise ValueError("full_engine_report must declare excel format")
