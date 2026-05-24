
from __future__ import annotations

from typing import Any, Dict, List


def aggregate_result(check_id: str, title: str, rows: List[Dict[str, Any]], status: str | None = None):
    if status is None:
        if any(str(r.get("status")).upper() in {"FAIL", "WARNING"} for r in rows):
            status = "WARNING"
        else:
            status = "OK"

    return {
        "check_id": check_id,
        "title": title,
        "status": status,
        "engineering_level": "DATA_QUALITY",
        "confidence": "HIGH",
        "rows": rows,
        "items": rows,
        "details": rows,
        "summary": {
            "total": len(rows),
            "ok": sum(1 for r in rows if str(r.get("status")).upper() == "OK"),
            "warning": sum(1 for r in rows if str(r.get("status")).upper() == "WARNING"),
            "fail": sum(1 for r in rows if str(r.get("status")).upper() == "FAIL"),
            "no_data": sum(1 for r in rows if str(r.get("status")).upper() == "NO_DATA"),
        },
    }
