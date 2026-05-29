from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from tbdy_engine.reports.excel_reporter import ExcelReporter
from tbdy_engine.reports.json_reporter import JSONReporter


@dataclass(frozen=True)
class ReportingResult:
    json_report: str
    excel_report: str | None


class ReportingFacade:
    def __init__(self, report_dir: str | Path):
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, check_results: Sequence[Any]) -> ReportingResult:
        json_reporter = JSONReporter()
        excel_reporter = ExcelReporter()

        json_path = json_reporter.generate(
            check_results,
            output_path=str(self.report_dir / "engine_report.json"),
        )
        excel_path = excel_reporter.generate(
            check_results,
            output_path=str(self.report_dir / "engine_report.xlsx"),
        )

        return ReportingResult(
            json_report=json_path,
            excel_report=excel_path,
        )
