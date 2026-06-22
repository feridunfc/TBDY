"""Small deterministic utility helpers for C14.1-P1."""
from __future__ import annotations
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
import json
import math
import re
import shutil
_STATUS_PRIORITY = {"FAIL": 5, "BLOCKED": 4, "NO_DATA": 3, "OUT_OF_SCOPE": 2, "OK": 1}
_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
def _detail_row(element: str, section: str, material: object, result: Mapping[str, object]) -> dict[str, object]:
    evidence = result.get("evidence") if isinstance(result.get("evidence"), Sequence) else []
    return {
        "element_type": element, "section": section, "material": material,
        "check_id": result.get("check_id"), "check_title": str(result.get("check_id", "")).replace("_", " ").title(),
        "value": result.get("value"), "limit": result.get("limit"), "unit": result.get("unit"),
        "comparison": result.get("pass_rule"), "status": result.get("result_status") or result.get("status"),
        "ratio": result.get("ratio"), "ratio_type": result.get("ratio_type"),
        "evaluation_level": result.get("evaluation_level"), "tbdy_ref": result.get("code_ref"),
        "evidence_table": sorted(_evidence_tables([result])),
        "evidence_columns": sorted(_evidence_columns(evidence)),
        "raw_values": _evidence_values(evidence, "raw_value"),
        "normalized_values": _evidence_values(evidence, "normalized_value"),
    }
def _diagnostic_summary(diagnostics: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for item in diagnostics:
        grouped[(str(item.get("status", "")), str(item.get("code", "")), str(item.get("component_type") or item.get("affected_element_type") or ""))].append(item)
    return [{
        "status": key[0], "code": key[1], "count": len(items), "affected_element_type": key[2] or None,
        "sample_component_ids": sorted({_text(item.get("component_id")) for item in items if _text(item.get("component_id"))})[:5],
        "sample_sections": sorted({_text(item.get("section")) for item in items if _text(item.get("section"))})[:5],
    } for key, items in sorted(grouped.items())]
def _section_overall(rows: Sequence[Mapping[str, object]]) -> str:
    statuses = [str(row.get("status")) for row in rows if row.get("check_id") != "minimum_compliance_scope"]
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if "NO_DATA" in statuses:
        return "NO_DATA"
    return "OK" if statuses and all(status in {"OK", "WARNING"} for status in statuses) else "NO_DATA"
def _adapter_diagnostic_dict(item: object) -> dict[str, object]:
    return {
        "status": getattr(item, "status", "BLOCKED"), "code": "GEOMETRY_CHECK_INPUT_ADAPTER",
        "check_id": getattr(item, "check_id", None), "component_id": getattr(item, "component_id", None),
        "component_type": getattr(item, "component_type", None), "message": getattr(item, "reason", ""),
        "missing_features": list(getattr(item, "missing_features", ())), "invalid_features": list(getattr(item, "invalid_features", ())),
    }
def _product_diagnostic(status: str, code: str, component_id: str, component_type: str, section: str | None, message: str) -> dict[str, object]:
    return {"status": status, "code": code, "component_id": component_id, "component_type": component_type, "section": section, "message": message}
def _feature_value(snapshot: Mapping[str, object], name: str) -> object:
    features = snapshot.get("features") if isinstance(snapshot.get("features"), Mapping) else {}
    feature = features.get(name) if isinstance(features.get(name), Mapping) else {}
    return feature.get("value")
def _feature_evidence(snapshot: Mapping[str, object], name: str) -> tuple[object, ...]:
    features = snapshot.get("features") if isinstance(snapshot.get("features"), Mapping) else {}
    feature = features.get(name) if isinstance(features.get(name), Mapping) else {}
    evidence = feature.get("evidence")
    return tuple(evidence) if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes, bytearray)) else ()
def _identity(snapshot: Mapping[str, object], key: str) -> object:
    identity = snapshot.get("identity") if isinstance(snapshot.get("identity"), Mapping) else {}
    return identity.get(key)
def _section(snapshot: Mapping[str, object]) -> str | None:
    value = _identity(snapshot, "section") or _identity(snapshot, "section_name")
    return _text(value) or None
def _evidence_tables(records: Sequence[Mapping[str, object]]) -> set[str]:
    tables: set[str] = set()
    for record in records:
        evidence = record.get("evidence")
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
            continue
        for item in evidence:
            if isinstance(item, Mapping):
                table = item.get("source_table") or item.get("actual_table_name")
                if table:
                    tables.add(str(table))
                for nested in item.get("source_tables", ()) if isinstance(item.get("source_tables"), Sequence) else ():
                    tables.add(str(nested))
    return tables
def _evidence_columns(evidence: Sequence[object]) -> set[str]:
    return {str(item.get("source_column")) for item in evidence if isinstance(item, Mapping) and item.get("source_column")}
def _evidence_values(evidence: Sequence[object], key: str) -> list[object]:
    return [item.get(key) for item in evidence if isinstance(item, Mapping) and key in item]
def _index_rows(rows: Sequence[Mapping[str, object]], key: str) -> dict[object, tuple[Mapping[str, object], ...]]:
    grouped: dict[object, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[row.get(key)].append(row)
    return {value: tuple(items) for value, items in grouped.items()}
def _rows(source: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = source.get(key, ())
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
def _worst_status(statuses: Sequence[str] | Any) -> str:
    values = list(statuses)
    return max(values, key=lambda value: _STATUS_PRIORITY.get(value, 0)) if values else "NO_DATA"
def _ratio(numerator: object, denominator: object) -> float | None:
    return float(numerator) / float(denominator) if _finite(numerator) and _finite(denominator) and float(denominator) != 0 else None
def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str) and _NUMERIC_RE.fullmatch(value):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    return None
def _finite(value: object) -> bool:
    return _number(value) is not None
def _text(value: object) -> str:
    return "" if value is None else str(value).strip()
def _snapshot_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (str(row.get("component_type", "")), str(_identity(row, "story") or ""), str(_section(row) or ""), str(row.get("component_id", "")))
def _check_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (str(row.get("component_type", "")), str(row.get("section") or ""), str(row.get("component", "")), str(row.get("check_id", "")))
def _diagnostic_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (str(row.get("code", "")), str(row.get("component_type", "")), str(row.get("component_id", "")))
def _prepare_owned_outputs(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in ("report", "artifacts"):
        path = root / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
__all__ = [name for name in globals() if name.startswith("_")]
