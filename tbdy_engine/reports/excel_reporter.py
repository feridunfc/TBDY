from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


class ExcelReporter:
    def __init__(self, write_history: bool = True) -> None:
        self.write_history = write_history
        self.last_snapshot_path: str | None = None

    def generate(self, checks, eval_results, output_path="engine_report.xlsx", planned_report=None):
        try:
            import openpyxl
        except Exception:
            return None

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Summary"
        ws.append(["Metric", "Value"])
        for metric, value in [
            ("Total Checks", len(checks)),
            ("OK", sum(1 for c in checks if c.status == "OK")),
            ("FAIL", sum(1 for c in checks if c.status == "FAIL")),
            ("WARNING", sum(1 for c in checks if c.status == "WARNING")),
            ("NO_DATA", sum(1 for c in checks if c.status == "NO_DATA")),
            ("ERROR", sum(1 for c in checks if c.status == "ERROR")),
        ]:
            ws.append([metric, value])

        detail = wb.create_sheet("Details")
        detail.append([
            "check_id", "element_label", "story", "status", "ratio", "value", "limit", "unit",
            "message", "action", "tbdy_ref", "evaluation_level", "source", "severity", "category",
            "report_section", "legacy_contract_id", "evidence"
        ])
        for c in checks:
            detail.append([
                c.check_id, c.element_label, c.story, c.status, c.ratio, c.value, c.limit, c.unit,
                c.message, c.action, c.tbdy_ref, c.evaluation_level, c.source, c.severity, c.category,
                c.report_section, c.legacy_contract_id, self._evidence_value(c),
            ])

        skipped = wb.create_sheet("Eval_Skipped")
        skipped.append(["evaluation", "reason"])
        for k, v in (eval_results.get("skipped") or {}).items():
            skipped.append([k, v])

        errors = wb.create_sheet("Eval_Errors")
        errors.append(["evaluation", "error"])
        for k, v in (eval_results.get("errors") or {}).items():
            errors.append([k, v])

        if planned_report is not None:
            self._add_report_contract_sheet(wb, planned_report)

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)

        self.last_snapshot_path = None
        if self.write_history:
            history_dir = path.parent / "history"
            history_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot = history_dir / f"{timestamp}_{path.name}"
            shutil.copy2(path, snapshot)
            self.last_snapshot_path = str(snapshot)

        return str(path)

    def _evidence_value(self, check) -> str:
        evidence = getattr(check, "evidence", None)
        if evidence in (None, ""):
            return ""
        return json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)

    def _add_report_contract_sheet(self, workbook, planned_report) -> None:
        sheet = workbook.create_sheet("Report_Contract")
        sheet.append(["Field", "Value"])
        for field_name in ["report_id", "formats", "sections", "include_fields", "metrics"]:
            sheet.append([field_name, self._contract_value(planned_report, field_name)])

    def _contract_value(self, planned_report, field_name: str) -> str:
        value = getattr(planned_report, field_name, "")
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return ",".join(str(item) for item in value)
        return str(value)
