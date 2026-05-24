from __future__ import annotations
from pathlib import Path
from typing import Any

def write_column_excel(column_result: Any, path: str | Path) -> Path:
    try:
        from openpyxl import Workbook
    except Exception as exc:
        raise RuntimeError("openpyxl gerekli: pip install openpyxl") from exc
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Column_Design"
    headers = ["member_id", "check_id", "status", "message", "ratio"]
    ws.append(headers)
    for row in column_result.report_tables.get("column_check_summary", []):
        ws.append([row.get(h) for h in headers])
    ws2 = wb.create_sheet("Summary")
    ws2.append(["key", "value"])
    for k, v in column_result.summary.items():
        ws2.append([k, v])
    wb.save(p)
    return p
