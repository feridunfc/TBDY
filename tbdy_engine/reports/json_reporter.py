from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Sequence


class JSONReporter:
    def generate(self, check_results: Sequence[Any], output_path="engine_report.json") -> str:
        payload = self.build_payload(check_results)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
        return str(path)

    def build_payload(self, check_results: Sequence[Any]) -> Dict[str, Any]:
        checks = list(check_results)
        return {
            "summary": _summary(checks),
            "checks": [_check_to_dict(c) for c in checks],
        }


def _summary(checks: list[Any]) -> Dict[str, Any]:
    ids = [_field(c, "id") for c in checks if _field(c, "id")]
    counts = Counter(ids)
    return {
        "total_checks": len(checks),
        "ok": sum(1 for c in checks if _status(c) == "OK"),
        "fail": sum(1 for c in checks if _status(c) == "FAIL"),
        "warning": sum(1 for c in checks if _status(c) == "WARNING"),
        "no_data": sum(1 for c in checks if _status(c) == "NO_DATA"),
        "error": sum(1 for c in checks if _status(c) == "ERROR"),
        "unique_components": len({_field(c, "component") for c in checks if _field(c, "component")}),
        "duplicate_check_ids": sum(count - 1 for count in counts.values() if count > 1),
        "beam_shear_checks": sum(1 for c in checks if _field(c, "check_type") == "beam_shear"),
        "beam_flexure_checks": sum(1 for c in checks if _field(c, "check_type") == "beam_flexure"),
        "beam_geometry_checks": sum(1 for c in checks if _field(c, "check_type") == "beam_geometry"),
    }


def _status(check: Any) -> str:
    return str(_field(check, "status") or "")


def _field(check: Any, name: str) -> Any:
    if isinstance(check, dict):
        return check.get(name)
    return getattr(check, name, None)


def _check_to_dict(check: Any) -> Dict[str, Any]:
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
