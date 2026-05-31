from __future__ import annotations

from tbdy_engine.design.beams.beam_core import BeamCoreResult
from tbdy_engine.design.beams.core_check import CoreCheck
from tbdy_engine.design.beams.evaluation_package import (
    BeamCheckEvaluation,
    BeamEvaluationPackage,
)


def beam_core_result_to_evaluation_packages(
    result: BeamCoreResult,
) -> tuple[BeamEvaluationPackage, ...]:
    if result.status == "INVALID_INPUT":
        return (_invalid_input_package(result),)

    checks = tuple(core_check_to_beam_check_evaluation(check) for check in result.core_checks)
    messages = _package_messages(result.status)

    package = BeamEvaluationPackage(
        component=result.context.beam_id,
        checks=checks,
        evidence={
            "story": result.context.story,
            "section_name": result.context.section_name,
            "status": result.status,
            "core_check_evidence_by_id": {
                check.id: dict(check.evidence) for check in result.core_checks
            },
        },
        messages=messages,
        story=result.context.story,
        section=result.context.section_name,
    )
    return (package,)


def core_check_to_beam_check_evaluation(check: CoreCheck) -> BeamCheckEvaluation:
    messages = (check.message,) if check.message else ()
    return BeamCheckEvaluation(
        check_type=check.name,
        status=check.status,
        demand=check.demand,
        capacity=check.capacity,
        ratio=check.ratio,
        unit=check.unit,
        code_ref=check.code_ref,
        messages=messages,
    )


def _invalid_input_package(result: BeamCoreResult) -> BeamEvaluationPackage:
    validation_errors = tuple(result.validation_errors)
    check = BeamCheckEvaluation(
        check_type="beam_core_input",
        status="NO_DATA",
        demand=None,
        capacity=None,
        ratio=None,
        unit=None,
        code_ref="TBDY core input validation",
        messages=validation_errors,
    )
    return BeamEvaluationPackage(
        component=result.context.beam_id,
        checks=(check,),
        evidence={
            "validation_errors": validation_errors,
            "story": result.context.story,
            "section_name": result.context.section_name,
            "status": result.status,
        },
        messages=validation_errors,
        story=result.context.story,
        section=result.context.section_name,
    )


def _package_messages(status: str) -> tuple[str, ...]:
    if status == "NO_DATA":
        return ("Beam core result contains NO_DATA checks.",)
    if status == "FAIL":
        return ("Beam core result contains failing checks.",)
    return ()