from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from tbdy_engine.design.beams.calculators.flexure import FlexureResult, TBDYFlexureCalculator
from tbdy_engine.design.beams.calculators.geometry import GeometryResult, TBDYGeometryCalculator
from tbdy_engine.design.beams.calculators.shear import ShearResult, TBDYShearCalculator
from tbdy_engine.design.beams.context import (
    BeamModelContext,
    build_beam_model_context,
    validate_beam_model_context,
)
from tbdy_engine.design.beams.core_check import (
    CoreCheck,
    flexure_check_to_core_check,
    geometry_check_to_core_check,
    shear_check_to_core_check,
)


@dataclass(frozen=True)
class BeamCoreResult:
    context: BeamModelContext
    validation_errors: tuple[str, ...]
    geometry: GeometryResult | None
    shear: ShearResult | None
    flexure: FlexureResult | None
    core_checks: tuple[CoreCheck, ...]
    status: str


def evaluate_beam_core(data: Mapping[str, object]) -> BeamCoreResult:
    context = build_beam_model_context(data)
    validation_errors = validate_beam_model_context(context)

    if validation_errors:
        return BeamCoreResult(
            context=context,
            validation_errors=validation_errors,
            geometry=None,
            shear=None,
            flexure=None,
            core_checks=(),
            status="INVALID_INPUT",
        )

    geometry = TBDYGeometryCalculator().calculate(context)
    shear = TBDYShearCalculator().calculate(context)
    flexure = TBDYFlexureCalculator().calculate(context)

    core_checks = (
        tuple(
            geometry_check_to_core_check(
                beam_id=context.beam_id,
                story=context.story,
                section_name=context.section_name,
                check=check,
            )
            for check in geometry.checks
        )
        + tuple(
            shear_check_to_core_check(
                beam_id=context.beam_id,
                story=context.story,
                section_name=context.section_name,
                check=check,
            )
            for check in shear.checks
        )
        + tuple(
            flexure_check_to_core_check(
                beam_id=context.beam_id,
                story=context.story,
                section_name=context.section_name,
                check=check,
            )
            for check in flexure.checks
        )
    )

    status = _aggregate_status(geometry.status, shear.status, flexure.status)

    return BeamCoreResult(
        context=context,
        validation_errors=(),
        geometry=geometry,
        shear=shear,
        flexure=flexure,
        core_checks=core_checks,
        status=status,
    )


def _aggregate_status(*statuses: str) -> str:
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if any(status == "NO_DATA" for status in statuses):
        return "NO_DATA"
    return "OK"