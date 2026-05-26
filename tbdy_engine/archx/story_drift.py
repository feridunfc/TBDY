from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    CanonicalSnapshot,
    CheckResult,
    DesignBasis,
    Evidence,
    FormulaTrace,
    Story,
    SubCheckResult,
    WorkbenchCell,
)


STORY_DRIFT_RECIPE: dict[str, Any] = {
    "check_id": "story_drift",
    "check_family": "global_check",
    "element_type": "STORY",
    "title": "Göreli Kat Ötelemesi Kontrolü",
    "tbdy_ref": "TBDY 2018 §4.9",
    "category": "DRIFT",
    "severity": "HIGH",
    "report_section": "global",
    "required_inputs": [
        "story.story_id",
        "story.height_mm",
        "story.drift_max_mm",
        "design_basis.drift_limit",
    ],
    "steps": [
        {
            "step_id": "story_drift_ratio",
            "input": "story.drift_ratio",
            "operation": "less_equal",
            "limit": "design_basis.drift_limit",
            "unit": "ratio",
            "lhs_label": "Δ_i / h_i",
        }
    ],
}


@dataclass(frozen=True)
class _ResolvedInputs:
    story: Story
    design_basis: DesignBasis
    drift_ratio: float
    source_values: dict[str, object]


@dataclass(frozen=True)
class _InputResolution:
    resolved: _ResolvedInputs | None
    missing_inputs: list[str]
    notes: list[str]


def evaluate_story_drift(snapshot: CanonicalSnapshot, story_id: str) -> CheckResult:
    resolution = _resolve_inputs(snapshot, story_id)
    if resolution.resolved is None:
        return _no_data_result(story_id, resolution.missing_inputs, resolution.notes)

    sub_checks = [_run_step(step, resolution.resolved) for step in STORY_DRIFT_RECIPE["steps"]]
    sub_check = sub_checks[0]
    status = "FAIL" if sub_check.status == "FAIL" else "OK"
    message = (
        "Göreli kat ötelemesi sınırı sağlanıyor."
        if status == "OK"
        else "Göreli kat ötelemesi sınırı aşılmış."
    )
    action = "No action required" if status == "OK" else "Kat rijitliğini ve taşıyıcı sistem düzenini kontrol edin."
    return CheckResult(
        check_id=STORY_DRIFT_RECIPE["check_id"],
        check_family=STORY_DRIFT_RECIPE["check_family"],
        element_type=STORY_DRIFT_RECIPE["element_type"],
        element_label=resolution.resolved.story.story_id,
        story=resolution.resolved.story.story_id,
        status=status,
        ratio=sub_check.ratio,
        value=sub_check.value,
        limit=sub_check.limit,
        unit="ratio",
        evaluation_level="DESIGN_LEVEL",
        tbdy_ref=STORY_DRIFT_RECIPE["tbdy_ref"],
        message=message,
        action=action,
        category=STORY_DRIFT_RECIPE["category"],
        severity=STORY_DRIFT_RECIPE["severity"],
        report_section=STORY_DRIFT_RECIPE["report_section"],
        evidence=_canonical_evidence(resolution.resolved.source_values),
        sub_checks=sub_checks,
    )


def build_story_workbench_cell(check_result: CheckResult) -> WorkbenchCell:
    return WorkbenchCell(
        cell_id=f"{check_result.check_id}:{check_result.element_label}:{check_result.story}",
        title=STORY_DRIFT_RECIPE["title"],
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
            "value": check_result.value,
            "limit": check_result.limit,
            "message": check_result.message,
            "action": check_result.action,
        },
        evidence_panel=check_result.evidence,
        code_ref={"tbdy_ref": check_result.tbdy_ref},
    )


def _resolve_inputs(snapshot: CanonicalSnapshot, story_id: str) -> _InputResolution:
    story = snapshot.stories.get(story_id)
    if story is None:
        return _InputResolution(resolved=None, missing_inputs=["story"], notes=[])

    design_basis = snapshot.design_basis
    if design_basis is None:
        return _InputResolution(resolved=None, missing_inputs=["design_basis"], notes=[])

    missing: list[str] = []
    notes: list[str] = []
    if story.height_mm is None:
        missing.append("story.height_mm")
    elif story.height_mm <= 0:
        missing.append("story.height_mm")
        notes.append("Invalid input: story.height_mm must be greater than zero.")
    if story.drift_max_mm is None:
        missing.append("story.drift_max_mm")
    if design_basis.drift_limit is None:
        missing.append("design_basis.drift_limit")
    if missing:
        return _InputResolution(resolved=None, missing_inputs=missing, notes=notes)

    height = float(story.height_mm)
    drift = float(story.drift_max_mm)
    drift_limit = float(design_basis.drift_limit)
    drift_ratio = drift / height
    source_values = {
        "story.story_id": story.story_id,
        "story.height_mm": story.height_mm,
        "story.drift_max_mm": story.drift_max_mm,
        "design_basis.code": design_basis.code,
        "design_basis.drift_limit": design_basis.drift_limit,
        "story.drift_ratio": drift_ratio,
    }
    return _InputResolution(
        resolved=_ResolvedInputs(story=story, design_basis=design_basis, drift_ratio=drift_ratio, source_values=source_values),
        missing_inputs=[],
        notes=[],
    )


def _run_step(step: dict[str, Any], inputs: _ResolvedInputs) -> SubCheckResult:
    operation = str(step["operation"])
    if operation != "less_equal":
        raise ValueError(f"Unsupported operation: {operation}")
    value = inputs.drift_ratio
    limit = float(inputs.design_basis.drift_limit)
    result = value <= limit
    ratio = value / limit
    trace = FormulaTrace(
        display_expression=f"{step['lhs_label']} <= {limit:g}",
        lhs_label=str(step["lhs_label"]),
        lhs_value=value,
        operator="<=",
        rhs_value=limit,
        result=result,
    )
    return SubCheckResult(
        step_id=str(step["step_id"]),
        status="OK" if result else "FAIL",
        value=value,
        limit=limit,
        unit=str(step["unit"]),
        ratio=ratio,
        message="OK" if result else "Drift limit aşılmış.",
        formula_trace=trace,
        evidence=_canonical_evidence(inputs.source_values),
    )


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


def _no_data_result(story_id: str, missing_inputs: list[str], notes: list[str]) -> CheckResult:
    source_values = {"requested_story_id": story_id}
    evidence = Evidence(
        evidence_type="missing_required_input",
        confidence="LOW",
        source_fields=list(source_values.keys()),
        source_values=source_values,
        unit_conversion_status="not_required",
        combo_family_status="not_applicable",
        notes=notes,
        missing_inputs=missing_inputs,
    )
    return CheckResult(
        check_id=STORY_DRIFT_RECIPE["check_id"],
        check_family=STORY_DRIFT_RECIPE["check_family"],
        element_type=STORY_DRIFT_RECIPE["element_type"],
        element_label=story_id,
        story=story_id,
        status="NO_DATA",
        ratio=None,
        value=None,
        limit=None,
        unit="ratio",
        evaluation_level="NO_DATA",
        tbdy_ref=STORY_DRIFT_RECIPE["tbdy_ref"],
        message="Göreli kat ötelemesi kontrolü için gerekli veri eksik.",
        action="Eksik canonical inputları sağlayın.",
        category=STORY_DRIFT_RECIPE["category"],
        severity=STORY_DRIFT_RECIPE["severity"],
        report_section=STORY_DRIFT_RECIPE["report_section"],
        evidence=evidence,
        sub_checks=[],
    )
