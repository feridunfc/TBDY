from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evaluation import EvaluationEvidence, EvaluationOutput, EvaluationPackage, EvaluationStep
from .models import (
    Beam,
    CanonicalSnapshot,
    CheckResult,
    Evidence,
    FormulaTrace,
    Section,
    SubCheckResult,
    WorkbenchCell,
)


BEAM_GEOMETRY_RECIPE: dict[str, Any] = {
    "check_id": "beam_geometry",
    "check_family": "beam_design",
    "element_type": "BEAM",
    "title": "Kiriş Geometri Kontrolü",
    "tbdy_ref": "TBDY 2018 §7.4.1",
    "category": "GEOMETRY",
    "severity": "LOW",
    "report_section": "beams",
    "required_inputs": [
        "beam.element_id",
        "beam.label",
        "beam.story_id",
        "beam.section_id",
        "section.width_mm",
        "section.depth_mm",
    ],
    "steps": [
        {
            "step_id": "beam_width_min",
            "input": "section.width_mm",
            "operation": "greater_equal",
            "limit": 250.0,
            "unit": "mm",
            "lhs_label": "b_w",
        },
        {
            "step_id": "beam_height_min",
            "input": "section.depth_mm",
            "operation": "greater_equal",
            "limit": 300.0,
            "unit": "mm",
            "lhs_label": "h",
        },
    ],
}


@dataclass(frozen=True)
class _ResolvedInputs:
    beam: Beam
    section: Section
    source_values: dict[str, object]


@dataclass(frozen=True)
class _InputResolution:
    resolved: _ResolvedInputs | None
    missing_inputs: list[str]
    source_values: dict[str, object]


def evaluate_beam_geometry_package(snapshot: CanonicalSnapshot, beam_id: str) -> EvaluationPackage:
    resolution = _resolve_inputs(snapshot, beam_id)
    if resolution.resolved is None:
        return _no_data_package(beam_id, resolution.missing_inputs, resolution.source_values)

    steps = [_run_evaluation_step(step, resolution.resolved) for step in BEAM_GEOMETRY_RECIPE["steps"]]
    status = "FAIL" if any(step.status == "FAIL" for step in steps) else "OK"
    governing_ratio = min(step.ratio for step in steps if step.ratio is not None)
    measurements = _measurements(resolution.resolved, steps)
    evidence = _evaluation_evidence(resolution.resolved.source_values)
    output = EvaluationOutput(
        output_id=f"{BEAM_GEOMETRY_RECIPE['check_id']}:{resolution.resolved.beam.label}:{resolution.resolved.beam.story_id}",
        element_type=BEAM_GEOMETRY_RECIPE["element_type"],
        element_label=resolution.resolved.beam.label,
        story=resolution.resolved.beam.story_id,
        measurements=measurements,
        status=status,
        governing_ratio=governing_ratio,
        evidence=evidence,
        steps=steps,
    )
    return EvaluationPackage(
        evaluation_id=BEAM_GEOMETRY_RECIPE["check_id"],
        evaluation_type="BEAM_GEOMETRY",
        check_family=BEAM_GEOMETRY_RECIPE["check_family"],
        category=BEAM_GEOMETRY_RECIPE["category"],
        source="canonical_model",
        status=status,
        outputs=[output],
        summary={"total_outputs": 1, "by_status": {status: 1}},
        evidence=evidence,
        diagnostics=[],
    )


def beam_geometry_package_to_check_results(package: EvaluationPackage) -> list[CheckResult]:
    return [_output_to_check_result(package, output) for output in package.outputs]


def evaluate_beam_geometry(snapshot: CanonicalSnapshot, beam_id: str) -> CheckResult:
    package = evaluate_beam_geometry_package(snapshot, beam_id)
    results = beam_geometry_package_to_check_results(package)
    return results[0]


def build_workbench_cell(check_result: CheckResult) -> WorkbenchCell:
    return WorkbenchCell(
        cell_id=f"{check_result.check_id}:{check_result.element_label}:{check_result.story}",
        title=BEAM_GEOMETRY_RECIPE["title"],
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


def _resolve_inputs(snapshot: CanonicalSnapshot, beam_id: str) -> _InputResolution:
    beam = snapshot.beams.get(beam_id)
    if beam is None:
        return _InputResolution(
            resolved=None,
            missing_inputs=["beam"],
            source_values={"requested_beam_id": beam_id},
        )

    source_values: dict[str, object] = {
        "beam.element_id": beam.element_id,
        "beam.label": beam.label,
        "beam.story_id": beam.story_id,
        "beam.section_id": beam.section_id,
    }
    section = snapshot.sections.get(beam.section_id)
    if section is None:
        return _InputResolution(
            resolved=None,
            missing_inputs=["section"],
            source_values=source_values,
        )

    source_values.update(
        {
            "section.section_id": section.section_id,
            "section.width_mm": section.width_mm,
            "section.depth_mm": section.depth_mm,
        }
    )
    missing: list[str] = []
    if section.width_mm is None:
        missing.append("section.width_mm")
    if section.depth_mm is None:
        missing.append("section.depth_mm")
    if missing:
        return _InputResolution(resolved=None, missing_inputs=missing, source_values=source_values)

    return _InputResolution(
        resolved=_ResolvedInputs(beam=beam, section=section, source_values=source_values),
        missing_inputs=[],
        source_values=source_values,
    )


def _run_evaluation_step(step: dict[str, Any], inputs: _ResolvedInputs) -> EvaluationStep:
    value = _step_value(step["input"], inputs)
    limit = float(step["limit"])
    result = _greater_equal(value, limit)
    status = "OK" if result else "FAIL"
    ratio = value / limit
    trace = FormulaTrace(
        display_expression=f"{step['lhs_label']} >= {limit:g} {step['unit']}",
        lhs_label=str(step["lhs_label"]),
        lhs_value=value,
        operator=">=",
        rhs_value=limit,
        result=result,
    )
    return EvaluationStep(
        step_id=str(step["step_id"]),
        status=status,
        value=value,
        limit=limit,
        unit=str(step["unit"]),
        ratio=ratio,
        message="OK" if status == "OK" else "Minimum limit sağlanmıyor.",
        formula_trace=trace,
        evidence=_evaluation_evidence(inputs.source_values),
    )


def _step_value(input_name: str, inputs: _ResolvedInputs) -> float:
    if input_name == "section.width_mm":
        return float(inputs.section.width_mm)
    if input_name == "section.depth_mm":
        return float(inputs.section.depth_mm)
    raise ValueError(f"Unsupported input: {input_name}")


def _greater_equal(value: float, limit: float) -> bool:
    return value >= limit


def _measurements(inputs: _ResolvedInputs, steps: list[EvaluationStep]) -> dict[str, object]:
    ratios = {step.step_id: step.ratio for step in steps}
    return {
        "width_mm": inputs.section.width_mm,
        "depth_mm": inputs.section.depth_mm,
        "width_ratio": ratios["beam_width_min"],
        "depth_ratio": ratios["beam_height_min"],
    }


def _evaluation_evidence(source_values: dict[str, object]) -> EvaluationEvidence:
    return EvaluationEvidence(
        evidence_type="canonical_model",
        confidence="HIGH",
        source_fields=list(source_values.keys()),
        source_values=source_values,
        unit_conversion_status="not_required",
        combo_family_status="not_applicable",
        notes=[],
        missing_inputs=[],
        assumptions=[],
    )


def _missing_evaluation_evidence(
    source_values: dict[str, object], missing_inputs: list[str]
) -> EvaluationEvidence:
    return EvaluationEvidence(
        evidence_type="missing_required_input",
        confidence="LOW",
        source_fields=list(source_values.keys()),
        source_values=source_values,
        unit_conversion_status="not_required",
        combo_family_status="not_applicable",
        notes=[],
        missing_inputs=missing_inputs,
        assumptions=[],
    )


def _no_data_package(
    beam_id: str, missing_inputs: list[str], source_values: dict[str, object]
) -> EvaluationPackage:
    evidence = _missing_evaluation_evidence(source_values, missing_inputs)
    output = EvaluationOutput(
        output_id=f"{BEAM_GEOMETRY_RECIPE['check_id']}:{beam_id}:",
        element_type=BEAM_GEOMETRY_RECIPE["element_type"],
        element_label=str(source_values.get("beam.label", beam_id)),
        story=str(source_values.get("beam.story_id", "")),
        measurements={},
        status="NO_DATA",
        governing_ratio=None,
        evidence=evidence,
        steps=[],
    )
    return EvaluationPackage(
        evaluation_id=BEAM_GEOMETRY_RECIPE["check_id"],
        evaluation_type="BEAM_GEOMETRY",
        check_family=BEAM_GEOMETRY_RECIPE["check_family"],
        category=BEAM_GEOMETRY_RECIPE["category"],
        source="canonical_model",
        status="NO_DATA",
        outputs=[output],
        summary={"total_outputs": 1, "by_status": {"NO_DATA": 1}},
        evidence=evidence,
        diagnostics=["Missing required input for beam_geometry."],
    )


def _output_to_check_result(package: EvaluationPackage, output: EvaluationOutput) -> CheckResult:
    status = output.status
    message = _message_for_status(status)
    action = _action_for_status(status)
    evaluation_level = "NO_DATA" if status == "NO_DATA" else "DESIGN_LEVEL"
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
        evaluation_level=evaluation_level,
        tbdy_ref=BEAM_GEOMETRY_RECIPE["tbdy_ref"],
        message=message,
        action=action,
        category=package.category,
        severity=BEAM_GEOMETRY_RECIPE["severity"],
        report_section=BEAM_GEOMETRY_RECIPE["report_section"],
        evidence=_check_evidence(output.evidence),
        sub_checks=[_evaluation_step_to_sub_check(step) for step in output.steps],
    )


def _evaluation_step_to_sub_check(step: EvaluationStep) -> SubCheckResult:
    return SubCheckResult(
        step_id=step.step_id,
        status=step.status,
        value=float(step.value),
        limit=float(step.limit),
        unit=step.unit,
        ratio=float(step.ratio),
        message=step.message,
        formula_trace=step.formula_trace,
        evidence=_check_evidence(step.evidence),
    )


def _check_evidence(evidence: EvaluationEvidence) -> Evidence:
    return Evidence(
        evidence_type=evidence.evidence_type,
        confidence=evidence.confidence,
        source_fields=evidence.source_fields,
        source_values=evidence.source_values,
        unit_conversion_status=evidence.unit_conversion_status,
        combo_family_status=evidence.combo_family_status,
        notes=evidence.notes,
        missing_inputs=evidence.missing_inputs,
    )


def _message_for_status(status: str) -> str:
    if status == "OK":
        return "Kiriş geometri minimum şartları sağlanıyor."
    if status == "FAIL":
        return "Kiriş geometri minimum şartları sağlanmıyor."
    return "Kiriş geometri kontrolü için gerekli veri eksik."


def _action_for_status(status: str) -> str:
    if status == "OK":
        return "No action required"
    if status == "FAIL":
        return "Kiriş kesit boyutlarını kontrol edin."
    return "Eksik canonical inputları sağlayın."
