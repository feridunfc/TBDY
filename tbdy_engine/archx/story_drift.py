from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evaluation import EvaluationEvidence, EvaluationOutput, EvaluationPackage, EvaluationStep
from .models import CanonicalSnapshot, CheckResult, DesignBasis, Evidence, FormulaTrace, Story, SubCheckResult, WorkbenchCell


STORY_DRIFT_RECIPE: dict[str, Any] = {
    "check_id": "story_drift",
    "check_family": "global_check",
    "element_type": "STORY",
    "title": "Göreli Kat Ötelemesi Kontrolü",
    "tbdy_ref": "TBDY 2018 §4.9",
    "category": "DRIFT",
    "severity": "HIGH",
    "report_section": "global",
    "steps": [
        {"step_id": "story_drift_ratio", "input": "story.drift_ratio", "limit": "design_basis.drift_limit", "unit": "ratio", "lhs_label": "Delta_i / h_i"}
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
    source_values: dict[str, object]


def evaluate_story_drift_package(snapshot: CanonicalSnapshot, story_id: str) -> EvaluationPackage:
    resolution = _resolve_inputs(snapshot, story_id)
    if resolution.resolved is None:
        return _no_data_package(story_id, resolution.missing_inputs, resolution.notes, resolution.source_values)

    steps = [_run_evaluation_step(step, resolution.resolved) for step in STORY_DRIFT_RECIPE["steps"]]
    step = steps[0]
    status = "FAIL" if step.status == "FAIL" else "OK"
    evidence = _evaluation_evidence(resolution.resolved.source_values)
    output = EvaluationOutput(
        output_id=f"story_drift:{resolution.resolved.story.story_id}:{resolution.resolved.story.story_id}",
        element_type="STORY",
        element_label=resolution.resolved.story.story_id,
        story=resolution.resolved.story.story_id,
        measurements=_measurements(resolution.resolved, step),
        status=status,
        governing_ratio=step.ratio,
        evidence=evidence,
        steps=steps,
    )
    return EvaluationPackage(
        evaluation_id="story_drift",
        evaluation_type="STORY_DRIFT",
        check_family="global_check",
        category="DRIFT",
        source="canonical_model",
        status=status,
        outputs=[output],
        summary={"total_outputs": 1, "by_status": {status: 1}},
        evidence=evidence,
        diagnostics=[],
    )


def story_drift_package_to_check_results(package: EvaluationPackage) -> list[CheckResult]:
    return [_output_to_check_result(package, output) for output in package.outputs]


def evaluate_story_drift(snapshot: CanonicalSnapshot, story_id: str) -> CheckResult:
    package = evaluate_story_drift_package(snapshot, story_id)
    return story_drift_package_to_check_results(package)[0]


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
        result_panel={"status": check_result.status, "ratio": check_result.ratio, "value": check_result.value, "limit": check_result.limit, "message": check_result.message, "action": check_result.action},
        evidence_panel=check_result.evidence,
        code_ref={"tbdy_ref": check_result.tbdy_ref},
    )


def _resolve_inputs(snapshot: CanonicalSnapshot, story_id: str) -> _InputResolution:
    story = snapshot.stories.get(story_id)
    if story is None:
        return _InputResolution(None, ["story"], [], {"requested_story_id": story_id})

    source_values: dict[str, object] = {
        "story.story_id": story.story_id,
        "story.height_mm": story.height_mm,
        "story.drift_max_mm": story.drift_max_mm,
    }
    design_basis = snapshot.design_basis
    if design_basis is None:
        return _InputResolution(None, ["design_basis"], [], source_values)

    source_values.update({"design_basis.code": design_basis.code, "design_basis.drift_limit": design_basis.drift_limit})
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
        return _InputResolution(None, missing, notes, source_values)

    drift_ratio = float(story.drift_max_mm) / float(story.height_mm)
    source_values["story.drift_ratio"] = drift_ratio
    return _InputResolution(_ResolvedInputs(story, design_basis, drift_ratio, source_values), [], [], source_values)


def _run_evaluation_step(step: dict[str, Any], inputs: _ResolvedInputs) -> EvaluationStep:
    value = inputs.drift_ratio
    limit = float(inputs.design_basis.drift_limit)
    result = value <= limit
    ratio = value / limit
    trace = FormulaTrace(f"{step['lhs_label']} <= {limit:g}", str(step["lhs_label"]), value, "<=", limit, result)
    return EvaluationStep(str(step["step_id"]), "OK" if result else "FAIL", value, limit, str(step["unit"]), ratio, "OK" if result else "Drift limit aşılmış.", trace, _evaluation_evidence(inputs.source_values))


def _measurements(inputs: _ResolvedInputs, step: EvaluationStep) -> dict[str, object]:
    return {
        "height_mm": inputs.story.height_mm,
        "drift_max_mm": inputs.story.drift_max_mm,
        "drift_limit": inputs.design_basis.drift_limit,
        "drift_ratio": inputs.drift_ratio,
        "usage_ratio": step.ratio,
    }


def _evaluation_evidence(source_values: dict[str, object]) -> EvaluationEvidence:
    return EvaluationEvidence("canonical_model", "HIGH", list(source_values.keys()), source_values, "not_required", "not_applicable", [], [], [])


def _missing_evaluation_evidence(source_values: dict[str, object], missing_inputs: list[str], notes: list[str]) -> EvaluationEvidence:
    return EvaluationEvidence("missing_required_input", "LOW", list(source_values.keys()), source_values, "not_required", "not_applicable", notes, missing_inputs, [])


def _no_data_package(story_id: str, missing_inputs: list[str], notes: list[str], source_values: dict[str, object]) -> EvaluationPackage:
    evidence = _missing_evaluation_evidence(source_values, missing_inputs, notes)
    output = EvaluationOutput(f"story_drift:{story_id}:{story_id}", "STORY", str(source_values.get("story.story_id", story_id)), str(source_values.get("story.story_id", story_id)), {}, "NO_DATA", None, evidence, [])
    diagnostics = ["Missing required input for story_drift."] + notes
    return EvaluationPackage("story_drift", "STORY_DRIFT", "global_check", "DRIFT", "canonical_model", "NO_DATA", [output], {"total_outputs": 1, "by_status": {"NO_DATA": 1}}, evidence, diagnostics)


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
        value=_result_value(output),
        limit=_result_limit(output),
        unit="ratio",
        evaluation_level="NO_DATA" if status == "NO_DATA" else "DESIGN_LEVEL",
        tbdy_ref=STORY_DRIFT_RECIPE["tbdy_ref"],
        message=_message_for_status(status),
        action=_action_for_status(status),
        category=package.category,
        severity=STORY_DRIFT_RECIPE["severity"],
        report_section=STORY_DRIFT_RECIPE["report_section"],
        evidence=_check_evidence(output.evidence),
        sub_checks=[_evaluation_step_to_sub_check(step) for step in output.steps],
    )


def _result_value(output: EvaluationOutput) -> float | None:
    if not output.steps:
        return None
    return output.steps[0].value


def _result_limit(output: EvaluationOutput) -> float | None:
    if not output.steps:
        return None
    return output.steps[0].limit


def _evaluation_step_to_sub_check(step: EvaluationStep) -> SubCheckResult:
    return SubCheckResult(step.step_id, step.status, float(step.value), float(step.limit), step.unit, float(step.ratio), step.message, step.formula_trace, _check_evidence(step.evidence))


def _check_evidence(evidence: EvaluationEvidence) -> Evidence:
    return Evidence(evidence.evidence_type, evidence.confidence, evidence.source_fields, evidence.source_values, evidence.unit_conversion_status, evidence.combo_family_status, evidence.notes, evidence.missing_inputs)


def _message_for_status(status: str) -> str:
    if status == "OK":
        return "Göreli kat ötelemesi sınırı sağlanıyor."
    if status == "FAIL":
        return "Göreli kat ötelemesi sınırı aşılmış."
    return "Göreli kat ötelemesi kontrolü için gerekli veri eksik."


def _action_for_status(status: str) -> str:
    if status == "OK":
        return "No action required"
    if status == "FAIL":
        return "Kat rijitliğini ve taşıyıcı sistem düzenini kontrol edin."
    return "Eksik canonical inputları sağlayın."
