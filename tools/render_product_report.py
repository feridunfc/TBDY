#!/usr/bin/env python
"""Render the C13.1 concrete frame geometry product report.

This tool is a reporting/readiness layer only. It consumes artifacts already
produced by the accepted live/fixture product slice and never calls ETABS,
never executes engineering design checks, and never unlocks rebar/flexure/shear,
force envelopes, axial interaction, or capacity design scope.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODAL_THRESHOLD = 0.95
WIDTH_LIMIT_MM = 250.0
BEAM_DEPTH_LIMIT_MM = 300.0
BEAM_HBW_LIMIT = 3.5
COLUMN_MIN_DIMENSION_MM = 300.0
COLUMN_MIN_AREA_MM2 = 75000.0
COLUMN_ASPECT_RATIO_LIMIT = 0.4
CONCRETE_RECTANGULAR_TABLE_NAME = "Frame Section Property Definitions - Concrete Rectangular"

TABLE_TITLES = {
    "executive_summary_rows": "executive_summary",
    "concrete_beam_section_geometry_checks": "concrete_beam_section_geometry_checks",
    "unsupported_beam_sections": "unsupported_beam_sections",
    "concrete_column_section_geometry_checks": "concrete_column_section_geometry_checks",
    "unsupported_column_sections": "unsupported_column_sections",
    "beam_section_detail_rows": "beam_section_detail",
    "column_section_detail_rows": "column_section_detail",
    "modal_mass_full_table_rows": "modal_mass_full_table",
    "modal_mass_final_verdict_rows": "modal_mass_final_verdict",
    "guardrail_rows": "guardrails",
    "boundary_note_rows": "boundary_notes",
}

TABLE_COLUMNS = {
    "executive_summary_rows": ["metric", "value"],
    "concrete_beam_section_geometry_checks": [
        "section", "assigned_beam_count", "stories", "width_mm", "depth_mm",
        "width_check_status", "width_value_mm", "width_limit_mm",
        "depth_check_status", "depth_value_mm", "depth_limit_mm",
        "h_over_bw_value", "h_over_bw_limit", "h_over_bw_status",
        "overall_status", "evidence_table",
    ],
    "unsupported_beam_sections": [
        "section", "assigned_beam_count", "stories", "sample_labels", "reason", "product_pass_impact",
    ],
    "concrete_column_section_geometry_checks": [
        "section", "assigned_column_count", "stories", "width_mm", "depth_mm",
        "min_dimension_value_mm", "min_dimension_limit_mm", "min_dimension_status",
        "area_value_mm2", "area_limit_mm2", "area_status",
        "aspect_ratio_value", "aspect_ratio_limit", "aspect_ratio_status",
        "overall_status", "evidence_table",
    ],
    "unsupported_column_sections": [
        "section", "assigned_column_count", "stories", "sample_labels", "reason", "product_pass_impact",
    ],
    "beam_section_detail_rows": [
        "element_type", "section", "check_id", "check_title", "value", "limit", "unit",
        "comparison", "status", "ratio", "evidence_table", "evidence_columns", "raw_values", "normalized_values",
    ],
    "column_section_detail_rows": [
        "element_type", "section", "check_id", "check_title", "value", "limit", "unit",
        "comparison", "status", "ratio", "evidence_table", "evidence_columns", "raw_values", "normalized_values",
    ],
    "modal_mass_final_verdict_rows": [
        "direction", "value", "limit", "comparison", "status", "selected_mode",
        "selected_row_index", "rows_considered", "source_column",
    ],
    "guardrail_rows": ["guardrail", "value"],
    "boundary_note_rows": ["item", "statement"],
}

MODAL_PREFERRED_COLUMNS = [
    "Case", "OutputCase", "Mode", "Period", "UX", "UY", "UZ", "RX", "RY", "RZ",
    "SumUX", "SumUY", "SumUZ", "SumRX", "SumRY", "SumRZ",
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _first_present(row: Mapping[str, Any] | None, aliases: Sequence[str]) -> tuple[str | None, Any]:
    if not row:
        return None, None
    direct = {str(k): k for k in row.keys()}
    folded = {str(k).replace(" ", "").replace("_", "").casefold(): k for k in row.keys()}
    for alias in aliases:
        if alias in direct:
            key = direct[alias]
            value = row.get(key)
            if value not in (None, ""):
                return str(key), value
        key = folded.get(alias.replace(" ", "").replace("_", "").casefold())
        if key is not None:
            value = row.get(key)
            if value not in (None, ""):
                return str(key), value
    return None, None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _length_to_mm(value: Any) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    return _round(number * 1000.0 if abs(number) <= 30 else number)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, list):
        return ", ".join(_fmt(item) for item in value)
    return str(value)


def _status_min(value: float | None, limit: float) -> str:
    if value is None:
        return "NO_DATA"
    return "OK" if value >= limit else "FAIL"


def _status_max(value: float | None, limit: float) -> str:
    if value is None:
        return "NO_DATA"
    return "OK" if value <= limit else "FAIL"


def _ratio(value: float | None, limit: float) -> float | None:
    if value is None or not limit:
        return None
    return _round(value / limit)


def _comparison(value: float | None, operator: str, limit: float) -> str:
    return f"{_fmt(value)} {operator} {_fmt(limit)}"


def _source_tables_path(input_dir: Path) -> Path:
    candidates = [
        input_dir / "product_report_source_tables.json",
        input_dir / "_pipeline" / "c8_live_feature_resolver" / "product_report_source_tables.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "product_report_source_tables.json is required. Run the C13 product slice or C8 smoke that emits product report source tables."
    )


def _table_payload(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    tables = source.get("tables") if isinstance(source, Mapping) else None
    if isinstance(tables, Mapping):
        item = tables.get(key)
        if isinstance(item, Mapping):
            return item
    return {"rows": [], "columns": [], "actual_table_name": None, "row_count": 0}


def _rows(source: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    item = _table_payload(source, key)
    rows = item.get("rows") or item.get("parsed_rows") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _find_section_row(section_rows: Sequence[Mapping[str, Any]], section_name: str) -> Mapping[str, Any] | None:
    aliases = ("section", "Section", "SectionName", "Name", "PropName", "FrameSection", "DesignSect", "AnalysisSect")
    wanted = str(section_name).strip().casefold()
    for row in section_rows:
        _, value = _first_present(row, aliases)
        if str(value or "").strip().casefold() == wanted:
            return row
    return None


def _frame_groups(frame_rows: Sequence[Mapping[str, Any]], element_type: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    wanted = element_type.casefold()
    for row in frame_rows:
        _, type_value = _first_present(row, ("Type", "FrameType", "ObjectType"))
        if str(type_value or "").strip().casefold() != wanted:
            continue
        _, design = _first_present(row, ("DesignSect", "Design Section", "DesignSection"))
        _, analysis = _first_present(row, ("AnalysisSect", "Analysis Section", "AnalysisSection"))
        section = str(design or analysis or "").strip()
        if section:
            groups[section].append(dict(row))
    return dict(sorted(groups.items(), key=lambda item: item[0]))


def _sample_frame(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, aliases in {
        "UniqueName": ("UniqueName", "Name"),
        "Label": ("Label",),
        "Story": ("Story",),
        "Length": ("Length",),
    }.items():
        _, value = _first_present(row, aliases)
        out[key] = value
    return out


def _stories(rows_for_section: Sequence[Mapping[str, Any]]) -> list[str]:
    stories: set[str] = set()
    for row in rows_for_section:
        _, story = _first_present(row, ("Story",))
        if story not in (None, ""):
            stories.add(str(story))
    return sorted(stories)


def _sample_labels(rows_for_section: Sequence[Mapping[str, Any]], limit: int = 5) -> list[str]:
    labels: list[str] = []
    for row in rows_for_section:
        _, label = _first_present(row, ("Label",))
        if label not in (None, "") and str(label) not in labels:
            labels.append(str(label))
        if len(labels) >= limit:
            break
    return labels


def _section_geometry(section: str, section_rows: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any] | None, str | None, Any, float | None, str | None, Any, float | None]:
    section_row = _find_section_row(section_rows, section)
    width_col, width_raw = _first_present(section_row, ("t2", "T2", "Width", "width", "b", "B"))
    depth_col, depth_raw = _first_present(section_row, ("t3", "T3", "Depth", "depth", "h", "H"))
    width_mm = _length_to_mm(width_raw)
    depth_mm = _length_to_mm(depth_raw)
    return section_row, width_col, width_raw, width_mm, depth_col, depth_raw, depth_mm


def _actual_section_table_name(section_table: Mapping[str, Any]) -> str:
    return str(section_table.get("actual_table_name") or CONCRETE_RECTANGULAR_TABLE_NAME)


def _unsupported_result(element: str, section: str, rows_for_section: Sequence[Mapping[str, Any]], reason: str) -> dict[str, Any]:
    count_key = "assigned_beam_count" if element == "Beam" else "assigned_column_count"
    classification = f"UNSUPPORTED_OR_NON_CONCRETE_{element.upper()}_SECTION"
    return {
        "section_name": section,
        "section": section,
        count_key: len(rows_for_section),
        "sample_beams" if element == "Beam" else "sample_columns": [_sample_frame(row) for row in rows_for_section[:5]],
        "sample_labels": _sample_labels(rows_for_section),
        "stories": _stories(rows_for_section),
        "status": "OUT_OF_SCOPE",
        "classification": classification,
        "reason": reason,
        "product_pass_impact": "Not counted as FAIL",
    }


def _evidence_columns(check: Mapping[str, Any]) -> str:
    cols = [str(ev.get("source_column")) for ev in check.get("evidence", []) if ev.get("source_column") not in (None, "")]
    return ",".join(cols) if cols else "-"


def _raw_values(check: Mapping[str, Any]) -> str:
    values = [ev.get("raw_value") for ev in check.get("evidence", []) if ev.get("raw_value") not in (None, "")]
    return ",".join(_fmt(v) for v in values) if values else "-"


def _normalized_values(check: Mapping[str, Any]) -> str:
    values = [ev.get("normalized_value") for ev in check.get("evidence", []) if ev.get("normalized_value") not in (None, "")]
    return ",".join(_fmt(v) for v in values) if values else "-"


def _evidence(table_name: str, source_column: str | None, raw_value: Any, normalized_value: Any, unit: str) -> dict[str, Any]:
    return {
        "source_table": "frame_section_properties",
        "actual_table_name": table_name,
        "source_column": source_column,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "unit": unit,
        "evidence_status": "FULL" if normalized_value is not None else "MISSING",
    }


def _beam_checks(width_mm: float, depth_mm: float, table_name: str, width_col: str | None, width_raw: Any, depth_col: str | None, depth_raw: Any) -> list[dict[str, Any]]:
    hbw = _round(depth_mm / width_mm) if width_mm else None
    return [
        {
            "check_id": "beam_geometry_min_width",
            "check_title": "Minimum width",
            "value": width_mm,
            "limit": WIDTH_LIMIT_MM,
            "unit": "mm",
            "comparison": _comparison(width_mm, ">=", WIDTH_LIMIT_MM),
            "status": _status_min(width_mm, WIDTH_LIMIT_MM),
            "ratio": _ratio(width_mm, WIDTH_LIMIT_MM),
            "evidence": [_evidence(table_name, width_col, width_raw, width_mm, "mm")],
        },
        {
            "check_id": "beam_geometry_min_depth",
            "check_title": "Minimum depth",
            "value": depth_mm,
            "limit": BEAM_DEPTH_LIMIT_MM,
            "unit": "mm",
            "comparison": _comparison(depth_mm, ">=", BEAM_DEPTH_LIMIT_MM),
            "status": _status_min(depth_mm, BEAM_DEPTH_LIMIT_MM),
            "ratio": _ratio(depth_mm, BEAM_DEPTH_LIMIT_MM),
            "evidence": [_evidence(table_name, depth_col, depth_raw, depth_mm, "mm")],
        },
        {
            "check_id": "beam_depth_width_ratio",
            "check_title": "Depth/width ratio",
            "value": hbw,
            "limit": BEAM_HBW_LIMIT,
            "unit": "ratio",
            "comparison": _comparison(hbw, "<=", BEAM_HBW_LIMIT),
            "status": _status_max(hbw, BEAM_HBW_LIMIT),
            "ratio": _ratio(hbw, BEAM_HBW_LIMIT),
            "depth_mm": depth_mm,
            "width_mm": width_mm,
            "evidence": [
                _evidence(table_name, depth_col, depth_raw, depth_mm, "mm"),
                _evidence(table_name, width_col, width_raw, width_mm, "mm"),
            ],
        },
    ]


def _column_checks(width_mm: float, depth_mm: float, table_name: str, width_col: str | None, width_raw: Any, depth_col: str | None, depth_raw: Any) -> list[dict[str, Any]]:
    min_dim = min(width_mm, depth_mm)
    area = _round(width_mm * depth_mm)
    aspect = _round(min_dim / max(width_mm, depth_mm)) if max(width_mm, depth_mm) else None
    base_evidence = [
        _evidence(table_name, width_col, width_raw, width_mm, "mm"),
        _evidence(table_name, depth_col, depth_raw, depth_mm, "mm"),
    ]
    return [
        {
            "check_id": "column_geometry_min_dimension",
            "check_title": "Minimum dimension",
            "value": min_dim,
            "limit": COLUMN_MIN_DIMENSION_MM,
            "unit": "mm",
            "comparison": _comparison(min_dim, ">=", COLUMN_MIN_DIMENSION_MM),
            "status": _status_min(min_dim, COLUMN_MIN_DIMENSION_MM),
            "ratio": _ratio(min_dim, COLUMN_MIN_DIMENSION_MM),
            "evidence": base_evidence,
        },
        {
            "check_id": "column_geometry_min_area",
            "check_title": "Minimum area",
            "value": area,
            "limit": COLUMN_MIN_AREA_MM2,
            "unit": "mm2",
            "comparison": _comparison(area, ">=", COLUMN_MIN_AREA_MM2),
            "status": _status_min(area, COLUMN_MIN_AREA_MM2),
            "ratio": _ratio(area, COLUMN_MIN_AREA_MM2),
            "evidence": base_evidence,
        },
        {
            "check_id": "column_geometry_aspect_ratio",
            "check_title": "Aspect ratio",
            "value": aspect,
            "limit": COLUMN_ASPECT_RATIO_LIMIT,
            "unit": "ratio",
            "comparison": _comparison(aspect, ">=", COLUMN_ASPECT_RATIO_LIMIT),
            "status": _status_min(aspect, COLUMN_ASPECT_RATIO_LIMIT),
            "ratio": _ratio(aspect, COLUMN_ASPECT_RATIO_LIMIT),
            "evidence": base_evidence,
        },
    ]


def _checked_section_result(element: str, section: str, rows_for_section: Sequence[Mapping[str, Any]], section_rows: Sequence[Mapping[str, Any]], section_table: Mapping[str, Any]) -> dict[str, Any]:
    _section_row, width_col, width_raw, width_mm, depth_col, depth_raw, depth_mm = _section_geometry(section, section_rows)
    if width_mm is None or depth_mm is None:
        raise ValueError("checked section requires concrete rectangular width/depth")
    table_name = _actual_section_table_name(section_table)
    checks = _beam_checks(width_mm, depth_mm, table_name, width_col, width_raw, depth_col, depth_raw) if element == "Beam" else _column_checks(width_mm, depth_mm, table_name, width_col, width_raw, depth_col, depth_raw)
    statuses = [check["status"] for check in checks]
    count_key = "assigned_beam_count" if element == "Beam" else "assigned_column_count"
    return {
        "section_name": section,
        "section": section,
        "classification": f"CONCRETE_RECTANGULAR_{element.upper()}_CHECKED",
        count_key: len(rows_for_section),
        "sample_beams" if element == "Beam" else "sample_columns": [_sample_frame(row) for row in rows_for_section[:5]],
        "stories": _stories(rows_for_section),
        "width_mm": width_mm,
        "depth_mm": depth_mm,
        "checks": checks,
        "overall_status": "FAIL" if "FAIL" in statuses else ("NO_DATA" if "NO_DATA" in statuses else "OK"),
        "evidence_table": table_name,
    }


def _classify_sections(element: str, groups: Mapping[str, Sequence[Mapping[str, Any]]], section_rows: Sequence[Mapping[str, Any]], section_table: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checked: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    for section, rows_for_section in groups.items():
        section_row, _width_col, _width_raw, width_mm, _depth_col, _depth_raw, depth_mm = _section_geometry(section, section_rows)
        if section_row is None:
            unsupported.append(_unsupported_result(
                element,
                section,
                rows_for_section,
                "Section not found in Concrete Rectangular section definitions",
            ))
            continue
        if width_mm is None or depth_mm is None:
            unsupported.append(_unsupported_result(
                element,
                section,
                rows_for_section,
                "Concrete rectangular width/depth could not be resolved",
            ))
            continue
        checked.append(_checked_section_result(element, section, rows_for_section, section_rows, section_table))
    return checked, unsupported


def _modal_summary(modal_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def selected(alias: str) -> dict[str, Any]:
        best = None
        best_i = None
        best_col = None
        for i, row in enumerate(modal_rows):
            col, value = _first_present(row, (alias, alias.replace("Sum", "Sum "), alias.lower(), alias.upper()))
            number = _to_float(value)
            if number is None:
                continue
            if best is None or number >= best:
                best = number
                best_i = i
                best_col = col
        mode = None
        if best_i is not None:
            _, mode = _first_present(modal_rows[best_i], ("Mode", "ModeNum", "StepNum", "Step"))
        return {
            "value": best,
            "limit": MODAL_THRESHOLD,
            "unit": "ratio",
            "comparison": _comparison(best, ">=", MODAL_THRESHOLD),
            "status": "OK" if isinstance(best, (int, float)) and best >= MODAL_THRESHOLD else ("FAIL" if best is not None else "NO_DATA"),
            "selected_mode": mode,
            "selected_row_index": best_i,
            "source_rows_considered_count": len(modal_rows),
            "source_table": "modal_participating_mass",
            "source_column": best_col or alias,
        }

    columns: list[str] = []
    for preferred in MODAL_PREFERRED_COLUMNS:
        for row in modal_rows:
            col, _ = _first_present(row, (preferred, preferred.lower(), preferred.upper()))
            if col and col not in columns:
                columns.append(col)
                break
    for row in modal_rows:
        for key in row.keys():
            if key not in columns:
                columns.append(str(key))
    ux = selected("SumUX")
    uy = selected("SumUY")
    return {
        "modal_threshold": MODAL_THRESHOLD,
        "modal_mass_table_rows": len(modal_rows),
        "columns": columns,
        "rows": [dict(row) for row in modal_rows],
        "modal_mass_participation_ux": ux,
        "modal_mass_participation_uy": uy,
        "modal_ux_status": ux["status"],
        "modal_uy_status": uy["status"],
    }


def _geometry_table_row(element: str, item: Mapping[str, Any]) -> dict[str, Any]:
    checks = {check["check_id"]: check for check in item["checks"]}
    if element == "Beam":
        width = checks["beam_geometry_min_width"]
        depth = checks["beam_geometry_min_depth"]
        hbw = checks["beam_depth_width_ratio"]
        return {
            "section": item["section_name"],
            "assigned_beam_count": item["assigned_beam_count"],
            "stories": ", ".join(item["stories"]),
            "width_mm": item["width_mm"],
            "depth_mm": item["depth_mm"],
            "width_check_status": width["status"],
            "width_value_mm": width["value"],
            "width_limit_mm": width["limit"],
            "depth_check_status": depth["status"],
            "depth_value_mm": depth["value"],
            "depth_limit_mm": depth["limit"],
            "h_over_bw_value": hbw["value"],
            "h_over_bw_limit": hbw["limit"],
            "h_over_bw_status": hbw["status"],
            "overall_status": item["overall_status"],
            "evidence_table": item["evidence_table"],
        }
    min_dim = checks["column_geometry_min_dimension"]
    area = checks["column_geometry_min_area"]
    aspect = checks["column_geometry_aspect_ratio"]
    return {
        "section": item["section_name"],
        "assigned_column_count": item["assigned_column_count"],
        "stories": ", ".join(item["stories"]),
        "width_mm": item["width_mm"],
        "depth_mm": item["depth_mm"],
        "min_dimension_value_mm": min_dim["value"],
        "min_dimension_limit_mm": min_dim["limit"],
        "min_dimension_status": min_dim["status"],
        "area_value_mm2": area["value"],
        "area_limit_mm2": area["limit"],
        "area_status": area["status"],
        "aspect_ratio_value": aspect["value"],
        "aspect_ratio_limit": aspect["limit"],
        "aspect_ratio_status": aspect["status"],
        "overall_status": item["overall_status"],
        "evidence_table": item["evidence_table"],
    }


def _unsupported_table_row(element: str, item: Mapping[str, Any]) -> dict[str, Any]:
    count_key = "assigned_beam_count" if element == "Beam" else "assigned_column_count"
    return {
        "section": item["section_name"],
        count_key: item[count_key],
        "stories": ", ".join(item["stories"]),
        "sample_labels": ", ".join(str(x) for x in item.get("sample_labels", [])),
        "reason": item["reason"],
        "product_pass_impact": item["product_pass_impact"],
    }


def _detail_rows(element: str, results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        for check in item["checks"]:
            rows.append({
                "element_type": element,
                "section": item["section_name"],
                "check_id": check["check_id"],
                "check_title": check["check_title"],
                "value": check["value"],
                "limit": check["limit"],
                "unit": check["unit"],
                "comparison": check["comparison"],
                "status": check["status"],
                "ratio": check["ratio"],
                "evidence_table": item["evidence_table"],
                "evidence_columns": _evidence_columns(check),
                "raw_values": _raw_values(check),
                "normalized_values": _normalized_values(check),
            })
    return rows


def _modal_full_rows(modal: Mapping[str, Any]) -> list[dict[str, Any]]:
    columns = [str(c) for c in modal.get("columns", [])]
    return [{column: row.get(column) for column in columns} for row in modal.get("rows", [])]


def _modal_verdict_rows(modal: Mapping[str, Any]) -> list[dict[str, Any]]:
    ux = modal["modal_mass_participation_ux"]
    uy = modal["modal_mass_participation_uy"]
    return [
        {
            "direction": "UX",
            "value": ux.get("value"),
            "limit": ux.get("limit"),
            "comparison": ux.get("comparison"),
            "status": ux.get("status"),
            "selected_mode": ux.get("selected_mode"),
            "selected_row_index": ux.get("selected_row_index"),
            "rows_considered": ux.get("source_rows_considered_count"),
            "source_column": ux.get("source_column"),
        },
        {
            "direction": "UY",
            "value": uy.get("value"),
            "limit": uy.get("limit"),
            "comparison": uy.get("comparison"),
            "status": uy.get("status"),
            "selected_mode": uy.get("selected_mode"),
            "selected_row_index": uy.get("selected_row_index"),
            "rows_considered": uy.get("source_rows_considered_count"),
            "source_column": uy.get("source_column"),
        },
    ]


def _guardrail_rows(guardrails: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"guardrail": key, "value": value} for key, value in guardrails.items()]


def _boundary_note_rows() -> list[dict[str, str]]:
    return [
        {"item": "scope", "statement": "This MVP checks concrete rectangular assigned beam and column geometry only."},
        {"item": "unsupported_sections", "statement": "Steel/non-concrete/unsupported sections are reported as out-of-scope and are not treated as concrete geometry failures."},
        {"item": "excluded_engineering_checks", "statement": "Rebar, flexure, shear, force envelopes, and capacity design are intentionally excluded."},
    ]


def _executive_rows(summary_values: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = [
        "product_slice_passed",
        "report_product_passed",
        "concrete_beam_section_type_count",
        "concrete_beam_object_count",
        "unsupported_beam_section_type_count",
        "unsupported_beam_object_count",
        "concrete_column_section_type_count",
        "concrete_column_object_count",
        "unsupported_column_section_type_count",
        "unsupported_column_object_count",
        "beam_fail_count",
        "column_fail_count",
        "modal_mass_table_rows",
        "modal_threshold",
        "modal_ux_status",
        "modal_uy_status",
        "total_fail_count",
    ]
    return [{"metric": metric, "value": summary_values.get(metric)} for metric in metrics]


def build_product_summary(input_dir: Path, report_dir: Path) -> dict[str, Any]:
    source_path = _source_tables_path(input_dir)
    source = _read_json(source_path)
    manifest_path = input_dir / "product_slice_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}

    section_table = _table_payload(source, "frame_section_properties")
    frame_rows = _rows(source, "frame_assignments")
    section_rows = _rows(source, "frame_section_properties")
    modal_rows = _rows(source, "modal_participating_mass")

    beam_groups = _frame_groups(frame_rows, "Beam")
    column_groups = _frame_groups(frame_rows, "Column")
    beam_results, unsupported_beams = _classify_sections("Beam", beam_groups, section_rows, section_table)
    column_results, unsupported_columns = _classify_sections("Column", column_groups, section_rows, section_table)
    modal = _modal_summary(modal_rows)

    beam_fail_count = sum(1 for item in beam_results for check in item["checks"] if check["status"] == "FAIL")
    column_fail_count = sum(1 for item in column_results for check in item["checks"] if check["status"] == "FAIL")
    modal_fail_count = int(modal["modal_ux_status"] != "OK") + int(modal["modal_uy_status"] != "OK")
    guardrails = {
        "excel_production_path_used": bool(manifest.get("excel_production_path_used", False)),
        "streamlit_ui_used": bool(manifest.get("streamlit_ui_used", False)),
        "legacy_runtime_used": bool(manifest.get("legacy_runtime_used", False)),
        "rebar_flexure_shear_capacity_unlocked": bool(manifest.get("rebar_flexure_shear_capacity_unlocked", False)),
    }
    guardrail_fail_count = sum(1 for value in guardrails.values() if value)
    total_fail_count = beam_fail_count + column_fail_count + modal_fail_count + guardrail_fail_count
    input_product_slice_passed = bool(manifest.get("product_slice_passed", True))
    report_product_passed = input_product_slice_passed and total_fail_count == 0 and bool(beam_results) and bool(column_results) and bool(modal_rows)

    concrete_beam_object_count = sum(item["assigned_beam_count"] for item in beam_results)
    concrete_column_object_count = sum(item["assigned_column_count"] for item in column_results)
    unsupported_beam_object_count = sum(item["assigned_beam_count"] for item in unsupported_beams)
    unsupported_column_object_count = sum(item["assigned_column_count"] for item in unsupported_columns)

    concrete_beam_section_geometry_checks = [_geometry_table_row("Beam", item) for item in beam_results]
    concrete_column_section_geometry_checks = [_geometry_table_row("Column", item) for item in column_results]
    unsupported_beam_sections = [_unsupported_table_row("Beam", item) for item in unsupported_beams]
    unsupported_column_sections = [_unsupported_table_row("Column", item) for item in unsupported_columns]
    beam_section_detail_rows = _detail_rows("Beam", beam_results)
    column_section_detail_rows = _detail_rows("Column", column_results)
    modal_mass_full_table_rows = _modal_full_rows(modal)
    modal_mass_final_verdict_rows = _modal_verdict_rows(modal)
    guardrail_rows = _guardrail_rows(guardrails)
    boundary_note_rows = _boundary_note_rows()

    values = {
        "product_slice_passed": input_product_slice_passed,
        "report_product_passed": report_product_passed,
        "concrete_beam_section_type_count": len(beam_results),
        "concrete_beam_object_count": concrete_beam_object_count,
        "unsupported_beam_section_type_count": len(unsupported_beams),
        "unsupported_beam_object_count": unsupported_beam_object_count,
        "concrete_column_section_type_count": len(column_results),
        "concrete_column_object_count": concrete_column_object_count,
        "unsupported_column_section_type_count": len(unsupported_columns),
        "unsupported_column_object_count": unsupported_column_object_count,
        "beam_fail_count": beam_fail_count,
        "column_fail_count": column_fail_count,
        "modal_mass_table_rows": modal["modal_mass_table_rows"],
        "modal_threshold": MODAL_THRESHOLD,
        "modal_ux_status": modal["modal_ux_status"],
        "modal_uy_status": modal["modal_uy_status"],
        "total_fail_count": total_fail_count,
    }
    executive_summary_rows = _executive_rows(values)

    summary = {
        "sprint": "C13.1_CONCRETE_COLUMN_GEOMETRY_TABULAR_PRODUCT_REPORT",
        "product_slice_passed": input_product_slice_passed,
        "report_product_passed": report_product_passed,
        "input_product_slice_passed": manifest.get("product_slice_passed"),
        "source_tables_path": str(source_path),
        "total_beam_count": sum(len(rows) for rows in beam_groups.values()),
        "assigned_beam_section_type_count": len(beam_groups),
        "total_column_count": sum(len(rows) for rows in column_groups.values()),
        "assigned_column_section_type_count": len(column_groups),
        "concrete_beam_section_type_count": len(beam_results),
        "concrete_beam_object_count": concrete_beam_object_count,
        "unsupported_beam_section_type_count": len(unsupported_beams),
        "unsupported_beam_object_count": unsupported_beam_object_count,
        "concrete_column_section_type_count": len(column_results),
        "concrete_column_object_count": concrete_column_object_count,
        "unsupported_column_section_type_count": len(unsupported_columns),
        "unsupported_column_object_count": unsupported_column_object_count,
        "unsupported_sections": unsupported_beams + unsupported_columns,
        "unsupported_beam_sections": unsupported_beam_sections,
        "unsupported_column_sections": unsupported_column_sections,
        "beam_geometry_check_count": len(beam_section_detail_rows),
        "column_geometry_check_count": len(column_section_detail_rows),
        "beam_fail_count": beam_fail_count,
        "column_fail_count": column_fail_count,
        "beam_geometry_fail_count": beam_fail_count,
        "column_geometry_fail_count": column_fail_count,
        "beam_section_type_results": beam_results,
        "column_section_type_results": column_results,
        "modal_mass_summary": modal,
        "modal_mass_table_rows": len(modal_mass_full_table_rows),
        "modal_threshold": MODAL_THRESHOLD,
        "modal_ux_status": modal["modal_ux_status"],
        "modal_uy_status": modal["modal_uy_status"],
        "fail_count": total_fail_count,
        "total_fail_count": total_fail_count,
        "guardrails": guardrails,
        "report_html": str(report_dir / "product_report.html"),
        "report_md": str(report_dir / "product_report.md"),
        "product_summary_json": str(report_dir / "product_summary.json"),
        # Strict C13.1 table contract arrays:
        "executive_summary_rows": executive_summary_rows,
        "concrete_beam_section_geometry_checks": concrete_beam_section_geometry_checks,
        "unsupported_beam_sections": unsupported_beam_sections,
        "concrete_column_section_geometry_checks": concrete_column_section_geometry_checks,
        "unsupported_column_sections": unsupported_column_sections,
        "beam_section_detail_rows": beam_section_detail_rows,
        "column_section_detail_rows": column_section_detail_rows,
        "modal_mass_full_table_rows": modal_mass_full_table_rows,
        "modal_mass_final_verdict_rows": modal_mass_final_verdict_rows,
        "guardrail_rows": guardrail_rows,
        "boundary_note_rows": boundary_note_rows,
    }
    return summary


def _table_columns_for(summary: Mapping[str, Any], key: str) -> list[str]:
    if key == "modal_mass_full_table_rows":
        modal_columns = [str(column) for column in (summary.get("modal_mass_summary") or {}).get("columns", [])]
        return modal_columns or list((summary.get(key) or [{}])[0].keys())
    return TABLE_COLUMNS[key]


def _md_table(headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(_fmt(row.get(header)).replace("\n", " ") for header in headers) + " |")
    return "\n".join(out)


def render_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# TBDY Minimal Live Product Report — C13.1",
        "",
        "Concrete rectangular assigned beam and column geometry screening + unsupported section classification + full modal mass table.",
        "",
    ]
    ordered = [
        ("1. Executive Summary", "executive_summary_rows"),
        ("2. Concrete Beam Section Geometry Checks", "concrete_beam_section_geometry_checks"),
        ("3. Unsupported / Out-of-Scope Beam Sections", "unsupported_beam_sections"),
        ("4. Concrete Column Section Geometry Checks", "concrete_column_section_geometry_checks"),
        ("5. Unsupported / Out-of-Scope Column Sections", "unsupported_column_sections"),
        ("6. Beam Section Detail", "beam_section_detail_rows"),
        ("7. Column Section Detail", "column_section_detail_rows"),
        ("8. Modal Mass Full Table", "modal_mass_full_table_rows"),
        ("9. Modal Mass Final Verdict", "modal_mass_final_verdict_rows"),
        ("10. Guardrails", "guardrail_rows"),
        ("11. Boundary Notes", "boundary_note_rows"),
    ]
    for title, key in ordered:
        lines.extend([
            f"## {title}",
            "",
            f"Table name: `{TABLE_TITLES[key]}`",
            "",
            _md_table(_table_columns_for(summary, key), summary.get(key, [])),
            "",
        ])
    return "\n".join(lines)


def _html_table(caption: str, headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body_lines = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(_fmt(row.get(header)))}</td>" for header in headers)
        body_lines.append(f"<tr>{cells}</tr>")
    body = "\n".join(body_lines)
    return f"<table><caption>{html.escape(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(summary: Mapping[str, Any]) -> str:
    title = "TBDY Minimal Live Product Report — C13.1"
    ordered = [
        ("1. Executive Summary", "executive_summary_rows"),
        ("2. Concrete Beam Section Geometry Checks", "concrete_beam_section_geometry_checks"),
        ("3. Unsupported / Out-of-Scope Beam Sections", "unsupported_beam_sections"),
        ("4. Concrete Column Section Geometry Checks", "concrete_column_section_geometry_checks"),
        ("5. Unsupported / Out-of-Scope Column Sections", "unsupported_column_sections"),
        ("6. Beam Section Detail", "beam_section_detail_rows"),
        ("7. Column Section Detail", "column_section_detail_rows"),
        ("8. Modal Mass Full Table", "modal_mass_full_table_rows"),
        ("9. Modal Mass Final Verdict", "modal_mass_final_verdict_rows"),
        ("10. Guardrails", "guardrail_rows"),
        ("11. Boundary Notes", "boundary_note_rows"),
    ]
    sections = []
    for title_text, key in ordered:
        sections.append(f"<section><h2>{html.escape(title_text)}</h2><p><strong>Table name:</strong> <code>{html.escape(TABLE_TITLES[key])}</code></p>{_html_table(TABLE_TITLES[key], _table_columns_for(summary, key), summary.get(key, []))}</section>")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 1400px; margin: 32px auto; padding: 0 20px; line-height: 1.45; }}
    table {{ border-collapse: collapse; margin: 12px 0 28px; width: 100%; font-size: 13px; }}
    caption {{ text-align: left; font-weight: 700; margin-bottom: 6px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
    th {{ background: #f3f3f3; position: sticky; top: 0; }}
    code {{ background: #f7f7f7; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  {''.join(sections)}
</body>
</html>
"""


def render_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_product_summary(input_dir, out_dir)
    markdown = render_markdown(summary)
    html_text = render_html(summary)
    (out_dir / "product_report.md").write_text(markdown, encoding="utf-8")
    (out_dir / "product_report.html").write_text(html_text, encoding="utf-8")
    _write_json(out_dir / "product_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render C13.1 concrete frame geometry/product modal report.")
    parser.add_argument("--input", required=True, help="Input product slice directory")
    parser.add_argument("--out", required=True, help="Output report directory")
    args = parser.parse_args(argv)
    try:
        summary = render_product_report(Path(args.input), Path(args.out))
        print(f"Wrote product report outputs to {args.out}")
        print(json.dumps({
            "product_slice_passed": summary.get("product_slice_passed"),
            "report_product_passed": summary.get("report_product_passed"),
            "concrete_beam_section_type_count": summary.get("concrete_beam_section_type_count"),
            "concrete_beam_object_count": summary.get("concrete_beam_object_count"),
            "concrete_column_section_type_count": summary.get("concrete_column_section_type_count"),
            "concrete_column_object_count": summary.get("concrete_column_object_count"),
            "unsupported_beam_section_type_count": summary.get("unsupported_beam_section_type_count"),
            "unsupported_beam_object_count": summary.get("unsupported_beam_object_count"),
            "unsupported_column_section_type_count": summary.get("unsupported_column_section_type_count"),
            "unsupported_column_object_count": summary.get("unsupported_column_object_count"),
            "modal_mass_table_rows": summary.get("modal_mass_table_rows") or (summary.get("modal_mass_summary") or {}).get("modal_mass_table_rows"),
            "modal_threshold": summary.get("modal_threshold"),
            "modal_ux_status": summary.get("modal_ux_status"),
            "modal_uy_status": summary.get("modal_uy_status"),
        }, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"C13.1 product report render failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
