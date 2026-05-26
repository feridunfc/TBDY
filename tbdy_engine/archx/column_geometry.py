from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    CanonicalSnapshot,
    CheckResult,
    Column,
    Evidence,
    FormulaTrace,
    Section,
    SubCheckResult,
    WorkbenchCell,
)


COLUMN_GEOMETRY_RECIPE: dict[str, Any] = {
    "check_id": "column_geometry",
    "check_family": "column_design",
    "element_type": "COLUMN",
    "title": "Kolon Geometri Kontrolü",
    "tbdy_ref": "TBDY 2018 §7.3.1",
    "category": "GEOMETRY",
    "severity": "LOW",
    "report_section": "columns",
    "required_inputs": [
        "column.element_id",
        "column.label",
        "column.story_id",
        "column.section_id",
        "section.width_mm",
        "section.depth_mm",
    ],
    "steps": [
        {
            "step_id": "column_min_edge",
            "input": "section.min_edge_mm",
            "operation": "greater_equal",
            "limit": 300.0,
            "unit": "mm",
            "lhs_label": "min(b, h)",
        },
        {
            "step_id": "column_min_area",
            "input": "section.area_mm2",
            "operation": "greater_equal",
            "limit": 90000.0,
            "unit": "mm2",
            "lhs_label": "A_c",
        },
        {
            "step_id": "column_aspect_ratio",
            "input": "section.aspect_ratio",
            "operation": "less_equal",
            "limit": 4.0,
            "unit": "",
            "lhs_label": "max(b, h) / min(b, h)",
        },
    ],
}


@dataclass(frozen=True)
class _ResolvedInputs:
    column: Column
    section: Section
    source_values: dict[str, object]


@dataclass(frozen=True)
class _InputResolution:
    resolved: _ResolvedInputs | None
    missing_inputs: list[str]


def evaluate_column_geometry(snapshot: CanonicalSnapshot, column_id: str) -> CheckResult:
    resolution = _resolve_inputs(snapshot, column_id)
    if resolution.resolved is None:
        return _no_data_result(column_id, resolution.missing_inputs)

    sub_checks = [_run_step(step, resolution.resolved) for step in COLUMN_GEOMETRY_RECIPE["steps"]]
    status = "FAIL" if any(sub.status == "FAIL" for sub in sub_checks) else "OK"
    ratio = min(sub.ratio for sub in sub_checks)
    message = (
        "Kolon geometri minimum şartları sağlanıyor."
        if status == "OK"
        else "Kolon geometri minimum şartları sağlanmıyor."
    )
    action = "No action required" if status == "OK" else "Kolon kesit boyutlarını kontrol edin."
    return CheckResult(
        check_id=COLUMN_GEOMETRY_RECIPE["check_id"],
        check_family=COLUMN_GEOMETRY_RECIPE["check_family"],
        element_type=COLUMN_GEOMETRY_RECIPE["element_type"],
        element_label=resolution.resolved.column.label,
        story=resolution.resolved.column.story_id,
        status=status,
        ratio=ratio,
        value=None,
        limit=None,
        unit="mm",
        evaluation_level="DESIGN_LEVEL",
        tbdy_ref=COLUMN_GEOMETRY_RECIPE["tbdy_ref"],
        message=message,
        action=action,
        category=COLUMN_GEOMETRY_RECIPE["category"],
        severity=COLUMN_GEOMETRY_RECIPE["severity"],
        report_section=COLUMN_GEOMETRY_RECIPE["report_section"],
        evidence=_canonical_evidence(resolution.resolved.source_values),
        sub_checks=sub_checks,
    )


def build_column_workbench_cell(check_result: CheckResult) -> WorkbenchCell:
    return WorkbenchCell(
        cell_id=f"{check_result.check_id}:{check_result.element_label}:{check_result.story}",
        title=COLUMN_GEOMETRY_RECIPE["title"],
        check_id=check_result.check_id,
        element_label=check_result.element_label,
        story=check_result.story,
        status=check_result.status,
        evaluation_level=check_result.evaluation_level,
        input_panel=check_result.evidence.source_values,
        formula_panel=[sub.formula_trace for sub in check_result.sub_checks],
        result_panel={
            "status": check_result.status,
            "ratio": check_result.ratio,
            "message": check_result.message,
            "action": check_result.action,
        },
        evidence_panel=check_result.evidence,
        code_ref={"tbdy_ref": check_result.tbdy_ref},
    )


def _resolve_inputs(snapshot: CanonicalSnapshot, column_id: str) -> _InputResolution:
    column = snapshot.columns.get(column_id)
    if column is None:
        return _InputResolution(resolved=None, missing_inputs=["column"])

    section = snapshot.sections.get(column.section_id)
    if section is None:
        return _InputResolution(resolved=None, missing_inputs=["section"])

    missing: list[str] = []
    if section.width_mm is None:
        missing.append("section.width_mm")
    if section.depth_mm is None:
        missing.append("section.depth_mm")
    if missing:
        return _InputResolution(resolved=None, missing_inputs=missing)

    width = float(section.width_mm)
    depth = float(section.depth_mm)
    source_values = {
        "column.element_id": column.element_id,
        "column.label": column.label,
        "column.story_id": column.story_id,
        "column.section_id": column.section_id,
        "section.section_id": section.section_id,
        "section.width_mm": section.width_mm,
        "section.depth_mm": section.depth_mm,
        "section.min_edge_mm": min(width, depth),
        "section.area_mm2": width * depth,
        "section.aspect_ratio": max(width, depth) / min(width, depth),
    }
    return _InputResolution(
        resolved=_ResolvedInputs(column=column, section=section, source_values=source_values),
        missing_inputs=[],
    )


def _run_step(step: dict[str, Any], inputs: _ResolvedInputs) -> SubCheckResult:
    value = _step_value(step["input"], inputs)
    limit = float(step["limit"])
    operation = str(step["operation"])
    if operation == "greater_equal":
        result = value >= limit
        ratio = value / limit
        operator = ">="
    elif operation == "less_equal":
        result = value <= limit
        ratio = limit / value
        operator = "<="
    else:
        raise ValueError(f"Unsupported operation: {operation}")
    status = "OK" if result else "FAIL"
    trace = FormulaTrace(
        display_expression=f"{step['lhs_label']} {operator} {limit:g} {step['unit']}".strip(),
        lhs_label=str(step["lhs_label"]),
        lhs_value=value,
        operator=operator,
        rhs_value=limit,
        result=result,
    )
    return SubCheckResult(
        step_id=str(step["step_id"]),
        status=status,
        value=value,
        limit=limit,
        unit=str(step["unit"]),
        ratio=ratio,
        message="OK" if status == "OK" else "Minimum limit sağlanmıyor.",
        formula_trace=trace,
        evidence=_canonical_evidence(inputs.source_values),
    )


def _step_value(input_name: str, inputs: _ResolvedInputs) -> float:
    values = inputs.source_values
    if input_name in values:
        return float(values[input_name])
    raise ValueError(f"Unsupported input: {input_name}")


def _canonical_evidence(source_values: dict[str, object]) -> Evidence:
    return Evidence(
        evidence_type="canonical_model",
        confidence="HIGH",
        source_fields=list(source_values.keys()),
        source_values=source_values,
        unit_conversion_status="not_required",
        combo_family_status="not_applicable",
        notes=[],
        missing_inputs=[],
    )


def _no_data_result(column_id: str, missing_inputs: list[str]) -> CheckResult:
    source_values = {"requested_column_id": column_id}
    evidence = Evidence(
        evidence_type="missing_required_input",
        confidence="LOW",
        source_fields=list(source_values.keys()),
        source_values=source_values,
        unit_conversion_status="not_required",
        combo_family_status="not_applicable",
        notes=[],
        missing_inputs=missing_inputs,
    )
    return CheckResult(
        check_id=COLUMN_GEOMETRY_RECIPE["check_id"],
        check_family=COLUMN_GEOMETRY_RECIPE["check_family"],
        element_type=COLUMN_GEOMETRY_RECIPE["element_type"],
        element_label=column_id,
        story="",
        status="NO_DATA",
        ratio=None,
        value=None,
        limit=None,
        unit="mm",
        evaluation_level="NO_DATA",
        tbdy_ref=COLUMN_GEOMETRY_RECIPE["tbdy_ref"],
        message="Kolon geometri kontrolü için gerekli veri eksik.",
        action="Eksik canonical inputları sağlayın.",
        category=COLUMN_GEOMETRY_RECIPE["category"],
        severity=COLUMN_GEOMETRY_RECIPE["severity"],
        report_section=COLUMN_GEOMETRY_RECIPE["report_section"],
        evidence=evidence,
        sub_checks=[],
    )
