#!/usr/bin/env python
"""Render the C13.0.1 concrete-scoped beam section product report.

This tool is a reporting/readiness layer only. It consumes artifacts already
produced by the accepted live/fixture product slice and never calls ETABS,
never executes engineering design checks, and never unlocks rebar/flexure/shear
or capacity design scope.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODAL_THRESHOLD = 0.95
WIDTH_LIMIT_MM = 250.0
DEPTH_LIMIT_MM = 300.0
HBW_LIMIT = 3.5


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


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


def _length_to_mm(value: Any) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    # ETABS live runs in this product line normally report section dimensions in
    # metres (for example t2=0.4, t3=0.7).  Existing feature normalization uses
    # the same convention.  Fixtures may already be in mm.
    return round(number * 1000.0, 6) if abs(number) <= 30 else round(number, 6)


def _status_lower_bound(value: float | None, limit: float) -> str:
    if value is None:
        return "NO_DATA"
    return "OK" if value >= limit else "FAIL"


def _status_upper_bound(value: float | None, limit: float) -> str:
    if value is None:
        return "NO_DATA"
    return "OK" if value <= limit else "FAIL"


def _ratio_lower(value: float | None, limit: float) -> float | None:
    if value is None or not limit:
        return None
    return round(value / limit, 6)


def _ratio_upper(value: float | None, limit: float) -> float | None:
    if value is None or not limit:
        return None
    return round(value / limit, 6)


def _source_tables_path(input_dir: Path) -> Path:
    candidates = [
        input_dir / "product_report_source_tables.json",
        input_dir / "_pipeline" / "c8_live_feature_resolver" / "product_report_source_tables.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "product_report_source_tables.json is required. Run C13.0+ product slice or C8 smoke that emits product report source tables."
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


def _evidence(table_payload: Mapping[str, Any], section_row: Mapping[str, Any] | None, *, source_column: str | None, raw_value: Any, normalized_value: Any, unit: str) -> dict[str, Any]:
    source_row = {}
    if section_row is not None:
        _, section_value = _first_present(section_row, ("section", "Section", "SectionName", "Name", "PropName", "DesignSect", "AnalysisSect"))
        source_row = {"section": section_value}
    return {
        "source_table": "frame_section_properties",
        "actual_table_name": table_payload.get("actual_table_name"),
        "source_column": source_column,
        "source_row": source_row,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "unit": unit,
        "evidence_status": "FULL" if normalized_value is not None else "MISSING",
    }


def _check_width(width_mm: float | None, table_payload: Mapping[str, Any], section_row: Mapping[str, Any] | None, raw_col: str | None, raw_value: Any) -> dict[str, Any]:
    status = _status_lower_bound(width_mm, WIDTH_LIMIT_MM)
    return {
        "check_id": "beam_geometry_min_width",
        "value": width_mm,
        "limit": WIDTH_LIMIT_MM,
        "unit": "mm",
        "status": status,
        "ratio": _ratio_lower(width_mm, WIDTH_LIMIT_MM),
        "ratio_type": "actual_over_minimum",
        "evidence": [_evidence(table_payload, section_row, source_column=raw_col, raw_value=raw_value, normalized_value=width_mm, unit="mm")],
    }


def _check_depth(depth_mm: float | None, table_payload: Mapping[str, Any], section_row: Mapping[str, Any] | None, raw_col: str | None, raw_value: Any) -> dict[str, Any]:
    status = _status_lower_bound(depth_mm, DEPTH_LIMIT_MM)
    return {
        "check_id": "beam_geometry_min_depth",
        "value": depth_mm,
        "limit": DEPTH_LIMIT_MM,
        "unit": "mm",
        "status": status,
        "ratio": _ratio_lower(depth_mm, DEPTH_LIMIT_MM),
        "ratio_type": "actual_over_minimum",
        "evidence": [_evidence(table_payload, section_row, source_column=raw_col, raw_value=raw_value, normalized_value=depth_mm, unit="mm")],
    }


def _check_hbw(depth_mm: float | None, width_mm: float | None, table_payload: Mapping[str, Any], section_row: Mapping[str, Any] | None, depth_col: str | None, depth_raw: Any, width_col: str | None, width_raw: Any) -> dict[str, Any]:
    value = round(depth_mm / width_mm, 6) if isinstance(depth_mm, (int, float)) and isinstance(width_mm, (int, float)) and width_mm else None
    return {
        "check_id": "beam_depth_width_ratio",
        "depth_mm": depth_mm,
        "width_mm": width_mm,
        "value": value,
        "limit": HBW_LIMIT,
        "unit": "ratio",
        "status": _status_upper_bound(value, HBW_LIMIT),
        "ratio": _ratio_upper(value, HBW_LIMIT),
        "ratio_type": "value_over_maximum",
        "evidence": [
            _evidence(table_payload, section_row, source_column=depth_col, raw_value=depth_raw, normalized_value=depth_mm, unit="mm"),
            _evidence(table_payload, section_row, source_column=width_col, raw_value=width_raw, normalized_value=width_mm, unit="mm"),
        ],
    }


def _beam_groups(frame_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in frame_rows:
        _, type_value = _first_present(row, ("Type", "FrameType", "ObjectType"))
        if str(type_value or "").strip().casefold() != "beam":
            continue
        _, design = _first_present(row, ("DesignSect", "Design Section", "DesignSection"))
        _, analysis = _first_present(row, ("AnalysisSect", "Analysis Section", "AnalysisSection"))
        section = str(design or analysis or "").strip()
        if not section:
            continue
        groups[section].append(dict(row))
    return dict(sorted(groups.items(), key=lambda item: item[0]))


def _sample_beam(row: Mapping[str, Any]) -> dict[str, Any]:
    out = {}
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
    return sorted({str(_first_present(row, ("Story",))[1]) for row in rows_for_section if _first_present(row, ("Story",))[1] not in (None, "")})


def _sample_labels(rows_for_section: Sequence[Mapping[str, Any]], limit: int = 5) -> list[Any]:
    labels = []
    for row in rows_for_section:
        _, label = _first_present(row, ("Label",))
        if label not in (None, "") and label not in labels:
            labels.append(label)
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


def _unsupported_section_result(section: str, rows_for_section: Sequence[Mapping[str, Any]], reason: str) -> dict[str, Any]:
    return {
        "section_name": section,
        "assigned_beam_count": len(rows_for_section),
        "sample_beams": [_sample_beam(row) for row in rows_for_section[:5]],
        "sample_labels": _sample_labels(rows_for_section),
        "stories": _stories(rows_for_section),
        "status": "OUT_OF_SCOPE",
        "classification": "UNSUPPORTED_OR_NON_CONCRETE_BEAM_SECTION",
        "reason": reason,
        "product_pass_impact": "Not counted as FAIL",
    }


def _section_result(section: str, rows_for_section: Sequence[Mapping[str, Any]], section_rows: Sequence[Mapping[str, Any]], section_table: Mapping[str, Any]) -> dict[str, Any]:
    section_row, width_col, width_raw, width_mm, depth_col, depth_raw, depth_mm = _section_geometry(section, section_rows)
    width_check = _check_width(width_mm, section_table, section_row, width_col, width_raw)
    depth_check = _check_depth(depth_mm, section_table, section_row, depth_col, depth_raw)
    hbw_check = _check_hbw(depth_mm, width_mm, section_table, section_row, depth_col, depth_raw, width_col, width_raw)
    statuses = [width_check["status"], depth_check["status"], hbw_check["status"]]
    return {
        "section_name": section,
        "classification": "CONCRETE_RECTANGULAR_BEAM_CHECKED",
        "assigned_beam_count": len(rows_for_section),
        "sample_beams": [_sample_beam(row) for row in rows_for_section[:5]],
        "stories": _stories(rows_for_section),
        "width_mm": width_mm,
        "depth_mm": depth_mm,
        "checks": [width_check, depth_check, hbw_check],
        "overall_status": "FAIL" if "FAIL" in statuses else ("NO_DATA" if "NO_DATA" in statuses else "OK"),
    }


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
        period = None
        if best_i is not None:
            _, mode = _first_present(modal_rows[best_i], ("Mode", "ModeNum", "StepNum", "Step"))
            _, period = _first_present(modal_rows[best_i], ("Period", "PeriodSec", "T"))
        return {
            "value": best,
            "limit": MODAL_THRESHOLD,
            "unit": "ratio",
            "status": "OK" if isinstance(best, (int, float)) and best >= MODAL_THRESHOLD else ("FAIL" if best is not None else "NO_DATA"),
            "selected_mode": mode,
            "selected_period": period,
            "selected_row_index": best_i,
            "source_rows_considered_count": len(modal_rows),
            "source_table": "modal_participating_mass",
            "source_column": best_col or alias,
        }
    ux = selected("SumUX")
    uy = selected("SumUY")
    return {
        "modal_threshold": MODAL_THRESHOLD,
        "modal_mass_table_rows": len(modal_rows),
        "columns": list(modal_rows[0].keys()) if modal_rows else [],
        "rows": [dict(row) for row in modal_rows],
        "modal_mass_participation_ux": ux,
        "modal_mass_participation_uy": uy,
        "modal_ux_status": ux["status"],
        "modal_uy_status": uy["status"],
    }


def build_product_summary(input_dir: Path, report_dir: Path) -> dict[str, Any]:
    source_path = _source_tables_path(input_dir)
    source = _read_json(source_path)
    manifest_path = input_dir / "product_slice_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    frame_table = _table_payload(source, "frame_assignments")
    section_table = _table_payload(source, "frame_section_properties")
    frame_rows = _rows(source, "frame_assignments")
    section_rows = _rows(source, "frame_section_properties")
    modal_rows = _rows(source, "modal_participating_mass")
    groups = _beam_groups(frame_rows)
    section_results: list[dict[str, Any]] = []
    unsupported_sections: list[dict[str, Any]] = []
    for section, rows_for_section in groups.items():
        section_row, _width_col, _width_raw, width_mm, _depth_col, _depth_raw, depth_mm = _section_geometry(section, section_rows)
        if section_row is None:
            unsupported_sections.append(_unsupported_section_result(
                section,
                rows_for_section,
                "Section not found in Concrete Rectangular section definitions",
            ))
            continue
        if width_mm is None or depth_mm is None:
            unsupported_sections.append(_unsupported_section_result(
                section,
                rows_for_section,
                "Concrete rectangular width/depth could not be resolved",
            ))
            continue
        section_results.append(_section_result(section, rows_for_section, section_rows, section_table))

    modal = _modal_summary(modal_rows)
    beam_check_count = sum(len(item["checks"]) for item in section_results)
    beam_fail_count = sum(1 for item in section_results for check in item["checks"] if check["status"] == "FAIL")
    beam_no_data_count = sum(1 for item in section_results for check in item["checks"] if check["status"] == "NO_DATA")
    modal_fail_count = int(modal["modal_ux_status"] != "OK") + int(modal["modal_uy_status"] != "OK")
    guardrails = {
        "excel_production_path_used": bool(manifest.get("excel_production_path_used", False)),
        "streamlit_ui_used": bool(manifest.get("streamlit_ui_used", False)),
        "legacy_runtime_used": bool(manifest.get("legacy_runtime_used", False)),
        "rebar_flexure_shear_capacity_unlocked": bool(manifest.get("rebar_flexure_shear_capacity_unlocked", False)),
    }
    guardrail_fail_count = sum(1 for value in guardrails.values() if value)
    total_fail_count = beam_fail_count + beam_no_data_count + modal_fail_count + guardrail_fail_count
    input_product_slice_passed = bool(manifest.get("product_slice_passed", True))
    report_product_passed = input_product_slice_passed and total_fail_count == 0 and bool(section_results) and bool(modal_rows)
    concrete_beam_object_count = sum(item["assigned_beam_count"] for item in section_results)
    unsupported_beam_object_count = sum(item["assigned_beam_count"] for item in unsupported_sections)
    summary = {
        "sprint": "C13.0.1_CONCRETE_ASSIGNED_FRAME_SCOPE_FIX_PRODUCT_REPORT_PASS_SEMANTICS",
        "product_slice_passed": input_product_slice_passed,
        "report_product_passed": report_product_passed,
        "input_product_slice_passed": manifest.get("product_slice_passed"),
        "source_tables_path": str(source_path),
        "total_beam_count": sum(len(rows) for rows in groups.values()),
        "assigned_beam_section_type_count": len(groups),
        "concrete_beam_section_type_count": len(section_results),
        "concrete_beam_object_count": concrete_beam_object_count,
        "unsupported_beam_section_type_count": len(unsupported_sections),
        "unsupported_beam_object_count": unsupported_beam_object_count,
        "unsupported_sections": unsupported_sections,
        "beam_geometry_check_count": beam_check_count,
        "beam_geometry_fail_count": beam_fail_count,
        "beam_geometry_no_data_count": beam_no_data_count,
        "beam_section_type_results": section_results,
        "concrete_column_scope_status": "NOT_IMPLEMENTED_IN_C13_0_1",
        "next_sprint_candidate": "C13.1_CONCRETE_COLUMN_GEOMETRY_REPORT",
        "modal_mass_summary": modal,
        "modal_threshold": MODAL_THRESHOLD,
        "modal_ux_status": modal["modal_ux_status"],
        "modal_uy_status": modal["modal_uy_status"],
        "fail_count": total_fail_count,
        "guardrails": guardrails,
        "report_html": str(report_dir / "product_report.html"),
        "report_md": str(report_dir / "product_report.md"),
        "product_summary_json": str(report_dir / "product_summary.json"),
    }
    return summary


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(_fmt(value).replace("\n", " ") for value in row) + " |")
    return "\n".join(out)


def render_markdown(summary: Mapping[str, Any]) -> str:
    modal = summary["modal_mass_summary"]
    section_rows = []
    for item in summary["beam_section_type_results"]:
        checks = {check["check_id"]: check for check in item["checks"]}
        section_rows.append([
            item["section_name"],
            item["assigned_beam_count"],
            ", ".join(item["stories"]),
            item["width_mm"],
            item["depth_mm"],
            checks["beam_geometry_min_width"]["status"],
            checks["beam_geometry_min_depth"]["status"],
            checks["beam_depth_width_ratio"]["status"],
            item["overall_status"],
            "Frame Section Property Definitions - Concrete Rectangular",
        ])
    lines = [
        "# TBDY Minimal Live Product Report — C13.0.1",
        "",
        "Concrete rectangular assigned beam geometry screening + unsupported section classification + full modal mass table.",
        "",
        "## 1. Executive Summary",
        "",
        _md_table(["Metric", "Value"], [
            ["product_slice_passed", summary["product_slice_passed"]],
            ["report_product_passed", summary["report_product_passed"]],
            ["concrete_beam_section_type_count", summary["concrete_beam_section_type_count"]],
            ["concrete_beam_object_count", summary["concrete_beam_object_count"]],
            ["unsupported_beam_section_type_count", summary["unsupported_beam_section_type_count"]],
            ["unsupported_beam_object_count", summary["unsupported_beam_object_count"]],
            ["modal_mass_table_rows", modal.get("modal_mass_table_rows")],
            ["modal_threshold", summary["modal_threshold"]],
            ["modal UX status", summary["modal_ux_status"]],
            ["modal UY status", summary["modal_uy_status"]],
            ["fail_count", summary["fail_count"]],
        ]),
        "",
        "## 2. Concrete Beam Section Geometry Checks",
        "",
        _md_table(["Section", "Assigned beam count", "Stories", "Width mm", "Depth mm", "Width check", "Depth check", "h/bw check", "Overall status", "Evidence"], section_rows),
        "",
        "## 3. Unsupported / Out-of-Scope Beam Sections",
        "",
        _md_table(["Section", "Assigned beam count", "Stories", "Sample labels", "Reason", "Product pass impact"], [
            [item["section_name"], item["assigned_beam_count"], ", ".join(item["stories"]), ", ".join(str(x) for x in item.get("sample_labels", [])), item["reason"], item["product_pass_impact"]]
            for item in summary.get("unsupported_sections", [])
        ]),
        "",
        "## 4. Beam Section Details",
        "",
    ]
    for item in summary["beam_section_type_results"]:
        lines.extend([f"### Section {item['section_name']}", ""])
        lines.append(f"Assigned beam count: {item['assigned_beam_count']}")
        lines.append("")
        lines.append(_md_table(["UniqueName", "Label", "Story", "Length"], [[b.get("UniqueName"), b.get("Label"), b.get("Story"), b.get("Length")] for b in item["sample_beams"]]))
        lines.append("")
        lines.append(_md_table(["Check ID", "Value", "Limit", "Unit", "Status", "Ratio", "Evidence columns"], [[c["check_id"], c.get("value"), c.get("limit"), c.get("unit"), c.get("status"), c.get("ratio"), ", ".join(str(ev.get("source_column")) for ev in c.get("evidence", []))] for c in item["checks"]]))
        lines.append("")
    lines.extend([
        "## 5. Full Modal Mass Table",
        "",
    ])
    modal_columns = modal.get("columns") or []
    modal_rows = modal.get("rows") or []
    lines.append(_md_table([str(c) for c in modal_columns], [[row.get(c) for c in modal_columns] for row in modal_rows]))
    ux = modal["modal_mass_participation_ux"]
    uy = modal["modal_mass_participation_uy"]
    lines.extend([
        "",
        "## 6. Modal Mass Final Verdict",
        "",
        f"Final cumulative UX = {_fmt(ux.get('value'))} >= {MODAL_THRESHOLD} → {ux.get('status')}",
        "",
        f"Final cumulative UY = {_fmt(uy.get('value'))} >= {MODAL_THRESHOLD} → {uy.get('status')}",
        "",
        _md_table(["Direction", "Value", "Limit", "Status", "Selected mode", "Selected row index", "Rows considered", "Source column"], [
            ["UX", ux.get("value"), ux.get("limit"), ux.get("status"), ux.get("selected_mode"), ux.get("selected_row_index"), ux.get("source_rows_considered_count"), ux.get("source_column")],
            ["UY", uy.get("value"), uy.get("limit"), uy.get("status"), uy.get("selected_mode"), uy.get("selected_row_index"), uy.get("source_rows_considered_count"), uy.get("source_column")],
        ]),
        "",
        "## 7. Guardrails",
        "",
        _md_table(["Guardrail", "Value"], [[k, v] for k, v in summary["guardrails"].items()]),
        "",
        "## 8. Boundary Note",
        "",
        "This MVP checks concrete rectangular frame geometry only. Steel/non-concrete/unsupported sections are reported as out-of-scope and are not treated as concrete geometry failures.",
        "",
        "It intentionally does not yet execute rebar, flexure, shear, or capacity-design checks.",
        "",
    ])
    return "\n".join(lines)


def render_html(summary: Mapping[str, Any], markdown: str) -> str:
    # Keep a lightweight self-contained HTML rendering. Tables are already clear
    # in Markdown, so preserve them in a readable preformatted block while the
    # JSON/Markdown artifacts remain machine/user friendly.
    title = "TBDY Minimal Live Product Report — C13.0.1"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 32px auto; padding: 0 20px; line-height: 1.45; }}
    .badge {{ display:inline-block; padding:6px 10px; border-radius: 6px; background:#eee; font-weight:700; }}
    pre {{ white-space: pre-wrap; background:#f7f7f7; padding:16px; border-radius:8px; overflow:auto; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p class=\"badge\">Report product passed: {html.escape(str(summary.get('report_product_passed')))}</p>
  <p>Concrete rectangular beam section types checked: {summary.get('concrete_beam_section_type_count')} · Concrete beam objects checked: {summary.get('concrete_beam_object_count')} · Unsupported beam objects: {summary.get('unsupported_beam_object_count')} · Modal threshold: {summary.get('modal_threshold')}</p>
  <pre>{html.escape(markdown)}</pre>
</body>
</html>
"""


def render_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_product_summary(input_dir, out_dir)
    markdown = render_markdown(summary)
    html_text = render_html(summary, markdown)
    (out_dir / "product_report.md").write_text(markdown, encoding="utf-8")
    (out_dir / "product_report.html").write_text(html_text, encoding="utf-8")
    _write_json(out_dir / "product_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render C13.0 all-beam section/product modal report.")
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
            "unsupported_beam_section_type_count": summary.get("unsupported_beam_section_type_count"),
            "unsupported_beam_object_count": summary.get("unsupported_beam_object_count"),
            "modal_mass_table_rows": (summary.get("modal_mass_summary") or {}).get("modal_mass_table_rows"),
            "modal_threshold": summary.get("modal_threshold"),
            "modal_ux_status": summary.get("modal_ux_status"),
            "modal_uy_status": summary.get("modal_uy_status"),
        }, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"C13.0 product report render failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
