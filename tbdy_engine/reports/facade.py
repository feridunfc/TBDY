from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from tbdy_engine.reports.action_summary import ActionSummaryBuilder
from tbdy_engine.reports.excel_reporter import ExcelReporter
from tbdy_engine.reports.json_reporter import JSONReporter


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
        json_reporter = JSONReporter(write_history=True)
        excel_reporter = ExcelReporter(write_history=True)

        json_path = json_reporter.generate(
            checks,
            eval_results,
            runtime_catalog=runtime_catalog,
            output_path=str(self.report_dir / "engine_report.json"),
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
