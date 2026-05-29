from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, Sequence


class ExcelReporter:
    def generate(self, check_results: Sequence[Any], output_path="engine_report.xlsx"):
        try:
            import openpyxl
        except Exception:
            return None

        checks = list(check_results)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Summary"
        ws.append(["Metric", "Value"])
        for metric, value in [
            ("Total Checks", len(checks)),
            ("OK", sum(1 for c in checks if _status(c) == "OK")),
            ("FAIL", sum(1 for c in checks if _status(c) == "FAIL")),
            ("WARNING", sum(1 for c in checks if _status(c) == "WARNING")),
            ("NO_DATA", sum(1 for c in checks if _status(c) == "NO_DATA")),
            ("ERROR", sum(1 for c in checks if _status(c) == "ERROR")),
        ]:
            ws.append([metric, value])

        detail = wb.create_sheet("Checks")
        headers = _headers(checks)
        detail.append(headers)
        for check in checks:
            row = _check_to_dict(check)
            detail.append([_cell_value(row.get(header)) for header in headers])

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)
        return str(path)


def _status(check: Any) -> str:
    if isinstance(check, dict):
        return str(check.get("status", "") or "")
    return str(getattr(check, "status", "") or "")


def _headers(checks: list[Any]) -> list[str]:
    if not checks:
        return ["status"]
    first = checks[0]
    if hasattr(first, "to_dict") and callable(first.to_dict):
        value = first.to_dict()
        if isinstance(value, dict):
            return list(value.keys())
    if is_dataclass(first):
        return [field.name for field in fields(first)]
    if isinstance(first, dict):
        return list(first.keys())
    if hasattr(first, "__dict__"):
        return list(vars(first).keys())
    raise TypeError(f"Unsupported CheckResult object: {type(first).__name__}")


def _check_to_dict(check: Any) -> dict[str, Any]:
    if hasattr(check, "to_dict") and callable(check.to_dict):
        value = check.to_dict()
        if isinstance(value, dict):
            return dict(value)
    if is_dataclass(check):
        return asdict(check)
    if isinstance(check, dict):
        return dict(check)
    if hasattr(check, "__dict__"):
        return dict(vars(check))
    raise TypeError(f"Unsupported CheckResult object: {type(check).__name__}")


def _cell_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return value
