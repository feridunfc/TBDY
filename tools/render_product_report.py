#!/usr/bin/env python
"""Render C13.1 product output with canonical beam/column CheckResults.

B1 ownership boundary
---------------------
Beam/column engineering decisions are already complete before this module runs.
For migrated member checks this reporter only serializes canonical CheckResult
fields.  It does not convert member lengths, infer units, evaluate applicability,
calculate h/b, apply member limits, or create member PASS/FAIL verdicts.

Existing modal and product guardrail reporting remains intentionally unchanged
in engineering ownership: modal reporting is a separate legacy product concern,
and manifest guardrail flags are surfaced rather than reinterpreted.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

MODAL_THRESHOLD = 0.95
MEMBER_FORMAL_CHECK_IDS = frozenset({
    "column_geometry_min_dimension",
    "beam_geometry_min_width",
    "beam_geometry_min_depth",
    "beam_depth_width_ratio",
})
RETIRED_LEGACY_CHECK_IDS = (
    "column_geometry_min_area",
    "column_geometry_aspect_ratio",
)

TABLE_TITLES = {
    "executive_summary_rows": "executive_summary",
    "concrete_beam_section_geometry_checks": "canonical_beam_check_results_by_section",
    "unsupported_beam_sections": "unassessed_beam_sections",
    "concrete_column_section_geometry_checks": "canonical_column_check_results_by_section",
    "unsupported_column_sections": "unassessed_column_sections",
    "beam_section_detail_rows": "canonical_beam_check_results",
    "column_section_detail_rows": "canonical_column_check_results",
    "modal_mass_full_table_rows": "modal_mass_full_table",
    "modal_mass_final_verdict_rows": "modal_mass_final_verdict",
    "guardrail_rows": "guardrails",
    "boundary_note_rows": "boundary_notes",
}

_CANONICAL_DETAIL_COLUMNS = [
    "element_type", "component", "story", "section", "check_id", "check_title",
    "value", "limit", "unit", "status", "ratio", "ratio_type", "pass_rule",
    "code_ref", "evidence", "messages",
]
_BEAM_SECTION_COLUMNS = [
    "section", "assigned_beam_count", "stories", "canonical_result_count",
    "check_ids", "canonical_statuses", "evidence_table",
]
_COLUMN_SECTION_COLUMNS = [
    "section", "assigned_column_count", "stories", "canonical_result_count",
    "check_ids", "canonical_statuses", "evidence_table",
]
TABLE_COLUMNS = {
    "executive_summary_rows": ["metric", "value"],
    "concrete_beam_section_geometry_checks": list(_BEAM_SECTION_COLUMNS),
    "unsupported_beam_sections": [
        "section", "assigned_beam_count", "stories", "sample_labels", "reason", "product_pass_impact",
    ],
    "concrete_column_section_geometry_checks": list(_COLUMN_SECTION_COLUMNS),
    "unsupported_column_sections": [
        "section", "assigned_column_count", "stories", "sample_labels", "reason", "product_pass_impact",
    ],
    "beam_section_detail_rows": list(_CANONICAL_DETAIL_COLUMNS),
    "column_section_detail_rows": list(_CANONICAL_DETAIL_COLUMNS),
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
_CHECK_TITLES = {
    "column_geometry_min_dimension": "Rectangular column minimum section dimension",
    "beam_geometry_min_width": "Beam web minimum width",
    "beam_geometry_min_depth": "Beam minimum height 300 mm sub-condition",
    "beam_depth_width_ratio": "Beam height/web-width maximum ratio",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_fmt(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True)
    return str(value)


def _first_present(row: Mapping[str, Any] | None, aliases: Sequence[str]) -> tuple[str | None, Any]:
    if not row:
        return None, None
    direct = {str(key): key for key in row}
    folded = {str(key).replace(" ", "").replace("_", "").casefold(): key for key in row}
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
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def _source_tables_path(input_dir: Path) -> Path:
    candidates = [
        input_dir / "product_report_source_tables.json",
        input_dir / "_pipeline" / "c8_live_feature_resolver" / "product_report_source_tables.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("product_report_source_tables.json is required for scope/modal reporting")


def _table_payload(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    tables = source.get("tables") if isinstance(source, Mapping) else None
    item = tables.get(key) if isinstance(tables, Mapping) else None
    return item if isinstance(item, Mapping) else {
        "rows": [], "columns": [], "actual_table_name": None, "row_count": 0,
    }


def _rows(source: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    item = _table_payload(source, key)
    rows = item.get("rows") or item.get("parsed_rows") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _modal_rows(source: Mapping[str, Any]) -> tuple[list[dict[str, Any]], Mapping[str, Any]]:
    # Preserve the historical C13.1 key first; accept later aliases without
    # changing modal decision ownership.
    for key in ("modal_participating_mass", "modal_mass_ratios", "modal_participating_mass_ratios"):
        rows = _rows(source, key)
        if rows:
            return rows, _table_payload(source, key)
    return [], _table_payload(source, "modal_participating_mass")


def _canonical_member_results_path(input_dir: Path) -> Path | None:
    candidates = [
        input_dir / "canonical_member_check_results.json",
        input_dir / "check_results.json",
        input_dir / "_pipeline" / "canonical_member" / "check_results.json",
        input_dir / "_pipeline" / "geometry_vertical_slice" / "check_results.json",
    ]
    return next((path for path in candidates if path.is_file()), None)


def _result_rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("check_results", "results", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, Mapping)]
    return []


def _load_canonical_member_results(input_dir: Path) -> tuple[list[dict[str, Any]], Path | None]:
    path = _canonical_member_results_path(input_dir)
    if path is None:
        return [], None
    selected: list[dict[str, Any]] = []
    for row in _result_rows(_read_json(path)):
        check_id = str(row.get("check_id") or "")
        component_type = str(row.get("component_type") or "").strip().casefold()
        if check_id not in MEMBER_FORMAL_CHECK_IDS or component_type not in {"beam", "column"}:
            continue
        for required in ("component", "check_id", "component_type", "status"):
            if row.get(required) in (None, ""):
                raise ValueError(f"Canonical member CheckResult is missing required field {required}: {row!r}")
        selected.append(dict(row))
    selected.sort(key=lambda row: (
        str(row.get("component_type")), str(row.get("component")), str(row.get("check_id"))
    ))
    return selected, path


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
    return dict(sorted(groups.items()))


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


def _canonical_detail_rows(results: Sequence[Mapping[str, Any]], component_type: str) -> list[dict[str, Any]]:
    wanted = component_type.casefold()
    rows: list[dict[str, Any]] = []
    for result in results:
        if str(result.get("component_type") or "").casefold() != wanted:
            continue
        check_id = str(result.get("check_id") or "")
        # Strict projection: no engineering calculation or status transformation.
        rows.append({
            "element_type": component_type.title(),
            "component": result.get("component"),
            "story": result.get("story"),
            "section": result.get("section"),
            "check_id": check_id,
            "check_title": _CHECK_TITLES.get(check_id, check_id),
            "value": result.get("value"),
            "limit": result.get("limit"),
            "unit": result.get("unit"),
            "status": result.get("status"),
            "ratio": result.get("ratio"),
            "ratio_type": result.get("ratio_type"),
            "pass_rule": result.get("pass_rule"),
            "code_ref": result.get("code_ref"),
            "evidence": result.get("evidence"),
            "messages": result.get("messages"),
        })
    return rows


def _section_rows(
    details: Sequence[Mapping[str, Any]],
    assignment_groups: Mapping[str, Sequence[Mapping[str, Any]]],
    evidence_table: str | None,
    *,
    element_type: str,
) -> list[dict[str, Any]]:
    by_section: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in details:
        by_section[str(row.get("section") or "")].append(row)
    count_key = "assigned_beam_count" if element_type == "Beam" else "assigned_column_count"
    rows: list[dict[str, Any]] = []
    for section in sorted(by_section):
        canonical = by_section[section]
        assigned = assignment_groups.get(section, ())
        rows.append({
            "section": section,
            count_key: len(assigned),
            "stories": _stories(assigned),
            "canonical_result_count": len(canonical),
            "check_ids": [row.get("check_id") for row in canonical],
            "canonical_statuses": [row.get("status") for row in canonical],
            "evidence_table": evidence_table,
        })
    return rows


def _unassessed_sections(
    assignment_groups: Mapping[str, Sequence[Mapping[str, Any]]],
    details: Sequence[Mapping[str, Any]],
    *,
    element_type: str,
) -> list[dict[str, Any]]:
    assessed_sections = {str(row.get("section") or "") for row in details}
    count_key = "assigned_beam_count" if element_type == "Beam" else "assigned_column_count"
    rows: list[dict[str, Any]] = []
    for section, assigned in assignment_groups.items():
        if section in assessed_sections:
            continue
        rows.append({
            "section": section,
            count_key: len(assigned),
            "stories": _stories(assigned),
            "sample_labels": _sample_labels(assigned),
            "reason": "No canonical member CheckResult artifact was supplied for this assigned section.",
            "product_pass_impact": "Reporter emits no member PASS/FAIL for this section.",
        })
    return rows


def _modal_summary(modal_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    # This is the pre-B1 modal product behavior, intentionally retained.
    def selected(alias: str) -> dict[str, Any]:
        best = None
        best_i = None
        best_col = None
        for index, row in enumerate(modal_rows):
            column, raw = _first_present(row, (alias, alias.replace("Sum", "Sum "), alias.lower(), alias.upper()))
            number = _to_float(raw)
            if number is None:
                continue
            if best is None or number >= best:
                best = number
                best_i = index
                best_col = column
        mode = None
        if best_i is not None:
            _, mode = _first_present(modal_rows[best_i], ("Mode", "ModeNum", "StepNum", "Step"))
        return {
            "value": best,
            "limit": MODAL_THRESHOLD,
            "unit": "ratio",
            "comparison": None if best is None else f"{best:g} >= {MODAL_THRESHOLD:g}",
            "status": "OK" if isinstance(best, (int, float)) and best >= MODAL_THRESHOLD else (
                "FAIL" if best is not None else "NO_DATA"
            ),
            "selected_mode": mode,
            "selected_row_index": best_i,
            "source_rows_considered_count": len(modal_rows),
            "source_table": "modal_participating_mass",
            "source_column": best_col or alias,
        }

    columns: list[str] = []
    for preferred in MODAL_PREFERRED_COLUMNS:
        for row in modal_rows:
            column, _ = _first_present(row, (preferred, preferred.lower(), preferred.upper()))
            if column and column not in columns:
                columns.append(column)
                break
    for row in modal_rows:
        for key in row:
            if str(key) not in columns:
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


def _modal_full_rows(modal: Mapping[str, Any]) -> list[dict[str, Any]]:
    columns = [str(column) for column in modal.get("columns", [])]
    return [{column: row.get(column) for column in columns} for row in modal.get("rows", [])]


def _modal_verdict_rows(modal: Mapping[str, Any]) -> list[dict[str, Any]]:
    ux = modal["modal_mass_participation_ux"]
    uy = modal["modal_mass_participation_uy"]
    return [
        {
            "direction": "UX", "value": ux.get("value"), "limit": ux.get("limit"),
            "comparison": ux.get("comparison"), "status": ux.get("status"),
            "selected_mode": ux.get("selected_mode"), "selected_row_index": ux.get("selected_row_index"),
            "rows_considered": ux.get("source_rows_considered_count"), "source_column": ux.get("source_column"),
        },
        {
            "direction": "UY", "value": uy.get("value"), "limit": uy.get("limit"),
            "comparison": uy.get("comparison"), "status": uy.get("status"),
            "selected_mode": uy.get("selected_mode"), "selected_row_index": uy.get("selected_row_index"),
            "rows_considered": uy.get("source_rows_considered_count"), "source_column": uy.get("source_column"),
        },
    ]


def _table_columns_for(summary: Mapping[str, Any], key: str) -> list[str]:
    if key == "modal_mass_full_table_rows":
        columns = list((summary.get("modal_mass_summary") or {}).get("columns") or [])
        if columns:
            return [str(item) for item in columns]
        rows = summary.get(key) or []
        return list(rows[0]) if rows else []
    return list(TABLE_COLUMNS.get(key, []))


def build_product_summary(input_dir: Path, out_dir: Path | None = None) -> dict[str, Any]:
    input_dir = Path(input_dir)
    source_path = _source_tables_path(input_dir)
    source = _read_json(source_path)
    if not isinstance(source, Mapping):
        raise ValueError("product_report_source_tables.json must contain a JSON object")
    manifest_path = input_dir / "product_slice_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    if not isinstance(manifest, Mapping):
        manifest = {}

    frame_rows = _rows(source, "frame_assignments")
    modal_rows, _modal_table = _modal_rows(source)
    beam_groups = _frame_groups(frame_rows, "Beam")
    column_groups = _frame_groups(frame_rows, "Column")

    canonical_results, canonical_path = _load_canonical_member_results(input_dir)
    beam_details = _canonical_detail_rows(canonical_results, "beam")
    column_details = _canonical_detail_rows(canonical_results, "column")
    evidence_name = None if canonical_path is None else canonical_path.name
    beam_sections = _section_rows(beam_details, beam_groups, evidence_name, element_type="Beam")
    column_sections = _section_rows(column_details, column_groups, evidence_name, element_type="Column")
    unassessed_beams = _unassessed_sections(beam_groups, beam_details, element_type="Beam")
    unassessed_columns = _unassessed_sections(column_groups, column_details, element_type="Column")

    modal = _modal_summary(modal_rows)
    modal_full_rows = _modal_full_rows(modal)
    modal_verdict_rows = _modal_verdict_rows(modal)

    beam_fail_count = sum(1 for row in beam_details if row.get("status") == "FAIL")
    column_fail_count = sum(1 for row in column_details if row.get("status") == "FAIL")
    member_blocked_count = sum(
        1 for row in (*beam_details, *column_details)
        if row.get("status") in {"BLOCKED", "NO_DATA"}
    )
    modal_fail_count = int(modal["modal_ux_status"] != "OK") + int(modal["modal_uy_status"] != "OK")

    guardrails = {
        "excel_production_path_used": bool(manifest.get("excel_production_path_used", False)),
        "streamlit_ui_used": bool(manifest.get("streamlit_ui_used", False)),
        "legacy_runtime_used": bool(manifest.get("legacy_runtime_used", False)),
        "rebar_flexure_shear_capacity_unlocked": bool(manifest.get("rebar_flexure_shear_capacity_unlocked", False)),
        "member_engineering_calculation_in_reporter": False,
        "member_limit_authority_in_reporter": False,
        "member_unit_inference_in_reporter": False,
        "retired_legacy_member_criteria_formalized": False,
    }
    guardrail_fail_count = sum(
        1 for key in (
            "excel_production_path_used", "streamlit_ui_used", "legacy_runtime_used",
            "rebar_flexure_shear_capacity_unlocked",
        )
        if guardrails[key]
    )
    total_fail_count = beam_fail_count + column_fail_count + modal_fail_count + guardrail_fail_count

    boundary_notes = {
        "member_result_authority": "Beam/column formal fields are serialized from canonical CheckResult only.",
        "missing_canonical_member_results": "Assigned member sections without canonical CheckResult receive no reporter PASS/FAIL.",
        "retired_legacy_check_ids": list(RETIRED_LEGACY_CHECK_IDS),
        "beam_depth_scope": "beam_geometry_min_depth represents only the 300-mm sub-condition, not complete §7.4.1.1(b) compliance.",
        "full_tbdy_compliance_status": "NOT_EVALUATED",
    }

    concrete_beam_object_count = sum(int(row["assigned_beam_count"]) for row in beam_sections)
    concrete_column_object_count = sum(int(row["assigned_column_count"]) for row in column_sections)
    unsupported_beam_object_count = sum(int(row["assigned_beam_count"]) for row in unassessed_beams)
    unsupported_column_object_count = sum(int(row["assigned_column_count"]) for row in unassessed_columns)
    input_product_slice_passed = manifest.get("product_slice_passed")

    values = {
        "product_slice_passed": input_product_slice_passed,
        "report_product_passed": None,
        "input_product_slice_passed": input_product_slice_passed,
        "member_check_result_source": evidence_name,
        "canonical_member_result_count": len(beam_details) + len(column_details),
        "canonical_member_blocked_or_no_data_count": member_blocked_count,
        "concrete_beam_section_type_count": len(beam_sections),
        "concrete_beam_object_count": concrete_beam_object_count,
        "unsupported_beam_section_type_count": len(unassessed_beams),
        "unsupported_beam_object_count": unsupported_beam_object_count,
        "concrete_column_section_type_count": len(column_sections),
        "concrete_column_object_count": concrete_column_object_count,
        "unsupported_column_section_type_count": len(unassessed_columns),
        "unsupported_column_object_count": unsupported_column_object_count,
        "beam_fail_count": beam_fail_count,
        "column_fail_count": column_fail_count,
        "modal_mass_table_rows": modal["modal_mass_table_rows"],
        "modal_threshold": MODAL_THRESHOLD,
        "modal_ux_status": modal["modal_ux_status"],
        "modal_uy_status": modal["modal_uy_status"],
        "total_fail_count": total_fail_count,
        "full_tbdy_compliance_status": "NOT_EVALUATED",
    }

    summary: dict[str, Any] = {
        **values,
        "sprint": "B1_BEAM_COLUMN_CANONICALIZATION",
        "source_tables_path": str(source_path),
        "member_check_results_path": None if canonical_path is None else str(canonical_path),
        "total_beam_count": sum(len(rows) for rows in beam_groups.values()),
        "assigned_beam_section_type_count": len(beam_groups),
        "total_column_count": sum(len(rows) for rows in column_groups.values()),
        "assigned_column_section_type_count": len(column_groups),
        "retired_legacy_check_ids": list(RETIRED_LEGACY_CHECK_IDS),
        "beam_geometry_check_count": len(beam_details),
        "column_geometry_check_count": len(column_details),
        "beam_geometry_fail_count": beam_fail_count,
        "column_geometry_fail_count": column_fail_count,
        "fail_count": total_fail_count,
        "executive_summary_rows": [{"metric": key, "value": value} for key, value in values.items()],
        "concrete_beam_section_geometry_checks": beam_sections,
        "unsupported_beam_sections": unassessed_beams,
        "concrete_column_section_geometry_checks": column_sections,
        "unsupported_column_sections": unassessed_columns,
        "beam_section_detail_rows": beam_details,
        "column_section_detail_rows": column_details,
        "beam_section_type_results": beam_sections,
        "column_section_type_results": column_sections,
        "unsupported_sections": [*unassessed_beams, *unassessed_columns],
        "modal_mass_summary": modal,
        "modal_mass_full_table_rows": modal_full_rows,
        "modal_mass_final_verdict_rows": modal_verdict_rows,
        "guardrails": guardrails,
        "guardrail_rows": [{"guardrail": key, "value": value} for key, value in guardrails.items()],
        "boundary_notes": boundary_notes,
        "boundary_note_rows": [{"item": key, "statement": value} for key, value in boundary_notes.items()],
    }
    if out_dir is not None:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
    return summary


def _md_table(headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if not headers:
        return "_No rows._"
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(_fmt(row.get(header)).replace("\n", " ") for header in headers) + " |")
    return "\n".join(output)


def render_markdown(summary: Mapping[str, Any]) -> str:
    ordered = [
        ("1. Executive Summary", "executive_summary_rows"),
        ("2. Canonical Beam CheckResults by Section", "concrete_beam_section_geometry_checks"),
        ("3. Beam Sections Without Canonical Results", "unsupported_beam_sections"),
        ("4. Canonical Column CheckResults by Section", "concrete_column_section_geometry_checks"),
        ("5. Column Sections Without Canonical Results", "unsupported_column_sections"),
        ("6. Beam Canonical CheckResult Detail", "beam_section_detail_rows"),
        ("7. Column Canonical CheckResult Detail", "column_section_detail_rows"),
        ("8. Modal Mass Full Table", "modal_mass_full_table_rows"),
        ("9. Modal Mass Final Verdict", "modal_mass_final_verdict_rows"),
        ("10. Guardrails", "guardrail_rows"),
        ("11. Boundary Notes", "boundary_note_rows"),
    ]
    lines = [
        "# TBDY Minimal Live Product Report — B1", "",
        "Beam/column engineering decisions below are serialized from canonical CheckResult artifacts.", "",
    ]
    for title, key in ordered:
        lines.extend([
            f"## {title}", "", f"Table name: `{TABLE_TITLES[key]}`", "",
            _md_table(_table_columns_for(summary, key), summary.get(key, [])), "",
        ])
    return "\n".join(lines)


def _html_table(caption: str, headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if not headers:
        return f"<p><strong>{html.escape(caption)}:</strong> no rows.</p>"
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(_fmt(row.get(header)))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return f"<table><caption>{html.escape(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(summary: Mapping[str, Any]) -> str:
    title = "TBDY Minimal Live Product Report — B1"
    ordered = [
        ("1. Executive Summary", "executive_summary_rows"),
        ("2. Canonical Beam CheckResults by Section", "concrete_beam_section_geometry_checks"),
        ("3. Beam Sections Without Canonical Results", "unsupported_beam_sections"),
        ("4. Canonical Column CheckResults by Section", "concrete_column_section_geometry_checks"),
        ("5. Column Sections Without Canonical Results", "unsupported_column_sections"),
        ("6. Beam Canonical CheckResult Detail", "beam_section_detail_rows"),
        ("7. Column Canonical CheckResult Detail", "column_section_detail_rows"),
        ("8. Modal Mass Full Table", "modal_mass_full_table_rows"),
        ("9. Modal Mass Final Verdict", "modal_mass_final_verdict_rows"),
        ("10. Guardrails", "guardrail_rows"),
        ("11. Boundary Notes", "boundary_note_rows"),
    ]
    sections = "".join(
        f"<section><h2>{html.escape(label)}</h2>{_html_table(TABLE_TITLES[key], _table_columns_for(summary, key), summary.get(key, []))}</section>"
        for label, key in ordered
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><title>{html.escape(title)}</title>
<style>body{{font-family:Arial,sans-serif;max-width:1400px;margin:32px auto;padding:0 20px;line-height:1.45}}table{{border-collapse:collapse;margin:12px 0 28px;width:100%;font-size:13px}}th,td{{border:1px solid #ddd;padding:6px 8px;vertical-align:top}}th{{background:#f3f3f3}}</style>
</head><body><h1>{html.escape(title)}</h1><p>Beam/column engineering decisions are serialized from canonical CheckResult artifacts.</p>{sections}</body></html>"""


def render_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_product_summary(input_dir, out_dir)
    (out_dir / "product_report.md").write_text(render_markdown(summary), encoding="utf-8")
    (out_dir / "product_report.html").write_text(render_html(summary), encoding="utf-8")
    _write_json(out_dir / "product_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render C13.1/B1 product report from canonical member results plus scope/modal evidence.")
    parser.add_argument("--input", required=True, help="Input product slice directory")
    parser.add_argument("--out", required=True, help="Output report directory")
    args = parser.parse_args(argv)
    try:
        summary = render_product_report(Path(args.input), Path(args.out))
        print(f"Wrote product report outputs to {args.out}")
        print(json.dumps({
            "canonical_member_result_count": summary.get("canonical_member_result_count"),
            "concrete_beam_section_type_count": summary.get("concrete_beam_section_type_count"),
            "concrete_column_section_type_count": summary.get("concrete_column_section_type_count"),
            "modal_mass_table_rows": summary.get("modal_mass_table_rows"),
            "modal_ux_status": summary.get("modal_ux_status"),
            "modal_uy_status": summary.get("modal_uy_status"),
        }, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"C13.1 product report render failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
