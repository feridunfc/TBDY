from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evaluation import EvaluationEvidence, EvaluationOutput, EvaluationPackage, EvaluationStep
from .models import CanonicalSnapshot, CheckResult, Column, Evidence, FormulaTrace, Section, SubCheckResult, WorkbenchCell


COLUMN_GEOMETRY_RECIPE: dict[str, Any] = {
    "check_id": "column_geometry",
    "check_family": "column_design",
    "element_type": "COLUMN",
    "title": "Kolon Geometri Kontrolü",
    "tbdy_ref": "TBDY 2018 §7.3.1",
    "category": "GEOMETRY",
    "severity": "LOW",
    "report_section": "columns",
    "steps": [
        {"step_id": "column_min_edge", "input": "section.min_edge_mm", "limit": 300.0, "unit": "mm", "lhs_label": "min(b, h)"},
        {"step_id": "column_min_area", "input": "section.area_mm2", "limit": 75000.0, "unit": "mm2", "lhs_label": "A_c"},
        {"step_id": "column_aspect_ratio", "input": "section.aspect_ratio_min_over_max", "limit": 0.4, "unit": "ratio", "lhs_label": "min(b, h) / max(b, h)"},
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
    source_values: dict[str, object]


def evaluate_column_geometry_package(snapshot: CanonicalSnapshot, column_id: str) -> EvaluationPackage:
    resolution = _resolve_inputs(snapshot, column_id)
    if resolution.resolved is None:
        return _no_data_package(column_id, resolution.missing_inputs, resolution.source_values)

    steps = [_run_evaluation_step(step, resolution.resolved) for step in COLUMN_GEOMETRY_RECIPE["steps"]]
    status = "FAIL" if any(step.status == "FAIL" for step in steps) else "OK"
    ratio = min(step.ratio for step in steps if step.ratio is not None)
    evidence = _evaluation_evidence(resolution.resolved.source_values)
    output = EvaluationOutput(
        output_id=f"column_geometry:{resolution.resolved.column.label}:{resolution.resolved.column.story_id}",
        element_type="COLUMN",
        element_label=resolution.resolved.column.label,
        story=resolution.resolved.column.story_id,
        measurements=_measurements(resolution.resolved, steps),
        status=status,
        governing_ratio=ratio,
        evidence=evidence,
        steps=steps,
    )
    return EvaluationPackage(
        evaluation_id="column_geometry",
        evaluation_type="COLUMN_GEOMETRY",
        check_family="column_design",
        category="GEOMETRY",
        source="canonical_model",
        status=status,
        outputs=[output],
        summary={"total_outputs": 1, "by_status": {status: 1}},
        evidence=evidence,
        diagnostics=[],
    )


def column_geometry_package_to_check_results(package: EvaluationPackage) -> list[CheckResult]:
    return [_output_to_check_result(package, output) for output in package.outputs]


def evaluate_column_geometry(snapshot: CanonicalSnapshot, column_id: str) -> CheckResult:
    package = evaluate_column_geometry_package(snapshot, column_id)
    return column_geometry_package_to_check_results(package)[0]


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
        result_panel={"status": check_result.status, "ratio": check_result.ratio, "message": check_result.message, "action": check_result.action},
        evidence_panel=check_result.evidence,
        code_ref={"tbdy_ref": COLUMN_GEOMETRY_RECIPE["tbdy_ref"]},
    )


def _resolve_inputs(snapshot: CanonicalSnapshot, column_id: str) -> _InputResolution:
    column = snapshot.columns.get(column_id)
    if column is None:
        return _InputResolution(None, ["column"], {"requested_column_id": column_id})
    source_values: dict[str, object] = {
        "column.element_id": column.element_id,
        "column.label": column.label,
        "column.story_id": column.story_id,
        "column.section_id": column.section_id,
    }
    section = snapshot.sections.get(column.section_id)
    if section is None:
        return _InputResolution(None, ["section"], source_values)
    source_values.update({"section.section_id": section.section_id, "section.width_mm": section.width_mm, "section.depth_mm": section.depth_mm})
    missing: list[str] = []
    if section.width_mm is None:
        missing.append("section.width_mm")
    if section.depth_mm is None:
        missing.append("section.depth_mm")
    if missing:
        return _InputResolution(None, missing, source_values)
    width = float(section.width_mm)
    depth = float(section.depth_mm)
    min_edge = min(width, depth)
    max_edge = max(width, depth)
    source_values.update({"section.min_edge_mm": min_edge, "section.area_mm2": width * depth, "section.aspect_ratio_min_over_max": min_edge / max_edge})
    return _InputResolution(_ResolvedInputs(column, section, source_values), [], source_values)


def _run_evaluation_step(step: dict[str, Any], inputs: _ResolvedInputs) -> EvaluationStep:
    value = _step_value(step["input"], inputs)
    limit = float(step["limit"])
    result = value >= limit
    status = "OK" if result else "FAIL"
    trace = FormulaTrace(f"{step['lhs_label']} >= {limit:g} {step['unit']}".strip(), str(step["lhs_label"]), value, ">=", limit, result)
    return EvaluationStep(str(step["step_id"]), status, value, limit, str(step["unit"]), value / limit, "OK" if status == "OK" else "Minimum limit sağlanmıyor.", trace, _evaluation_evidence(inputs.source_values))


def _step_value(input_name: str, inputs: _ResolvedInputs) -> float:
    values = inputs.source_values
    if input_name in values:
        return float(values[input_name])
    raise ValueError(f"Unsupported input: {input_name}")


def _measurements(inputs: _ResolvedInputs, steps: list[EvaluationStep]) -> dict[str, object]:
    ratios = {step.step_id: step.ratio for step in steps}
    width = float(inputs.section.width_mm)
    depth = float(inputs.section.depth_mm)
    min_edge = min(width, depth)
    max_edge = max(width, depth)
    area = width * depth
    aspect_ratio = min_edge / max_edge
    return {"width_mm": inputs.section.width_mm, "depth_mm": inputs.section.depth_mm, "min_edge_mm": min_edge, "area_mm2": area, "aspect_ratio": aspect_ratio, "min_edge_ratio": ratios["column_min_edge"], "area_ratio": ratios["column_min_area"], "aspect_ratio_ratio": ratios["column_aspect_ratio"]}


def _evaluation_evidence(source_values: dict[str, object]) -> EvaluationEvidence:
    return EvaluationEvidence("canonical_model", "HIGH", list(source_values.keys()), source_values, "not_required", "not_applicable", [], [], [])


def _missing_evaluation_evidence(source_values: dict[str, object], missing_inputs: list[str]) -> EvaluationEvidence:
    return EvaluationEvidence("missing_required_input", "LOW", list(source_values.keys()), source_values, "not_required", "not_applicable", [], missing_inputs, [])


def _no_data_package(column_id: str, missing_inputs: list[str], source_values: dict[str, object]) -> EvaluationPackage:
    evidence = _missing_evaluation_evidence(source_values, missing_inputs)
    output = EvaluationOutput(f"column_geometry:{column_id}:", "COLUMN", str(source_values.get("column.label", column_id)), str(source_values.get("column.story_id", "")), {}, "NO_DATA", None, evidence, [])
    return EvaluationPackage("column_geometry", "COLUMN_GEOMETRY", "column_design", "GEOMETRY", "canonical_model", "NO_DATA", [output], {"total_outputs": 1, "by_status": {"NO_DATA": 1}}, evidence, ["Missing required input for column_geometry."])


def _output_to_check_result(package: EvaluationPackage, output: EvaluationOutput) -> CheckResult:
    status = output.status
    return CheckResult(
        check_id=package.evaluation_id,
        check_family=package.check_family,
        element_type=output.element_type,
        element_label=output.element_label,
        story=output.story,
        status=status,
        ratio=output.governing_ratio,
        value=None,
        limit=None,
        unit="mm",
        evaluation_level="NO_DATA" if status == "NO_DATA" else "DESIGN_LEVEL",
        tbdy_ref=COLUMN_GEOMETRY_RECIPE["tbdy_ref"],
        message=_message_for_status(status),
        action=_action_for_status(status),
        category=package.category,
        severity=COLUMN_GEOMETRY_RECIPE["severity"],
        report_section=COLUMN_GEOMETRY_RECIPE["report_section"],
        evidence=_check_evidence(output.evidence),
        sub_checks=[_evaluation_step_to_sub_check(step) for step in output.steps],
    )


def _evaluation_step_to_sub_check(step: EvaluationStep) -> SubCheckResult:
    return SubCheckResult(step.step_id, step.status, float(step.value), float(step.limit), step.unit, float(step.ratio), step.message, step.formula_trace, _check_evidence(step.evidence))


def _check_evidence(evidence: EvaluationEvidence) -> Evidence:
    return Evidence(evidence.evidence_type, evidence.confidence, evidence.source_fields, evidence.source_values, evidence.unit_conversion_status, evidence.combo_family_status, evidence.notes, evidence.missing_inputs)


def _message_for_status(status: str) -> str:
    if status == "OK":
        return "Kolon geometri minimum şartları sağlanıyor."
    if status == "FAIL":
        return "Kolon geometri minimum şartları sağlanmıyor."
    return "Kolon geometri kontrolü için gerekli veri eksik."


def _action_for_status(status: str) -> str:
    if status == "OK":
        return "No action required"
    if status == "FAIL":
        return "Kolon kesit boyutlarını kontrol edin."
    return "Eksik canonical inputları sağlayın."
