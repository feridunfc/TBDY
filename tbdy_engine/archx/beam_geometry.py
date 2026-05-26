from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def evaluate_beam_geometry(snapshot: CanonicalSnapshot, beam_id: str) -> CheckResult:
    resolution = _resolve_inputs(snapshot, beam_id)
    if resolution.resolved is None:
        return _no_data_result(beam_id, resolution.missing_inputs)

    sub_checks = [_run_step(step, resolution.resolved) for step in BEAM_GEOMETRY_RECIPE["steps"]]
    status = "FAIL" if any(sub.status == "FAIL" for sub in sub_checks) else "OK"
    ratio = min(sub.ratio for sub in sub_checks)
    message = (
        "Kiriş geometri minimum şartları sağlanıyor."
        if status == "OK"
        else "Kiriş geometri minimum şartları sağlanmıyor."
    )
    action = "No action required" if status == "OK" else "Kiriş kesit boyutlarını kontrol edin."
    return CheckResult(
        check_id=BEAM_GEOMETRY_RECIPE["check_id"],
        check_family=BEAM_GEOMETRY_RECIPE["check_family"],
        element_type=BEAM_GEOMETRY_RECIPE["element_type"],
        element_label=resolution.resolved.beam.label,
        story=resolution.resolved.beam.story_id,
        status=status,
        ratio=ratio,
        value=None,
        limit=None,
        unit="mm",
        evaluation_level="DESIGN_LEVEL",
        tbdy_ref=BEAM_GEOMETRY_RECIPE["tbdy_ref"],
        message=message,
        action=action,
        category=BEAM_GEOMETRY_RECIPE["category"],
        severity=BEAM_GEOMETRY_RECIPE["severity"],
        report_section=BEAM_GEOMETRY_RECIPE["report_section"],
        evidence=_canonical_evidence(resolution.resolved.source_values),
        sub_checks=sub_checks,
    )


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
        return _InputResolution(resolved=None, missing_inputs=["beam"])

    section = snapshot.sections.get(beam.section_id)
    if section is None:
        return _InputResolution(resolved=None, missing_inputs=["section"])

    missing: list[str] = []
    if section.width_mm is None:
        missing.append("section.width_mm")
    if section.depth_mm is None:
        missing.append("section.depth_mm")
    if missing:
        return _InputResolution(resolved=None, missing_inputs=missing)

    source_values = {
        "beam.element_id": beam.element_id,
        "beam.label": beam.label,
        "beam.story_id": beam.story_id,
        "beam.section_id": beam.section_id,
        "section.section_id": section.section_id,
        "section.width_mm": section.width_mm,
        "section.depth_mm": section.depth_mm,
    }
    return _InputResolution(
        resolved=_ResolvedInputs(beam=beam, section=section, source_values=source_values),
        missing_inputs=[],
    )


def _run_step(step: dict[str, Any], inputs: _ResolvedInputs) -> SubCheckResult:
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
    if input_name == "section.width_mm":
        return float(inputs.section.width_mm)
    if input_name == "section.depth_mm":
        return float(inputs.section.depth_mm)
    raise ValueError(f"Unsupported input: {input_name}")


def _greater_equal(value: float, limit: float) -> bool:
    return value >= limit


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


def _no_data_result(beam_id: str, missing_inputs: list[str]) -> CheckResult:
    source_values = {"requested_beam_id": beam_id}
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
        check_id=BEAM_GEOMETRY_RECIPE["check_id"],
        check_family=BEAM_GEOMETRY_RECIPE["check_family"],
        element_type=BEAM_GEOMETRY_RECIPE["element_type"],
        element_label=beam_id,
        story="",
        status="NO_DATA",
        ratio=None,
        value=None,
        limit=None,
        unit="mm",
        evaluation_level="NO_DATA",
        tbdy_ref=BEAM_GEOMETRY_RECIPE["tbdy_ref"],
        message="Kiriş geometri kontrolü için gerekli veri eksik.",
        action="Eksik canonical inputları sağlayın.",
        category=BEAM_GEOMETRY_RECIPE["category"],
        severity=BEAM_GEOMETRY_RECIPE["severity"],
        report_section=BEAM_GEOMETRY_RECIPE["report_section"],
        evidence=evidence,
        sub_checks=[],
    )
