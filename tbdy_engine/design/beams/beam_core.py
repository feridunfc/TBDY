from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from tbdy_engine.design.beams.calculators.flexure import FlexureResult, TBDYFlexureCalculator
from tbdy_engine.design.beams.calculators.geometry import GeometryResult, TBDYGeometryCalculator
from tbdy_engine.design.beams.calculators.shear import (
    ShearResult,
    TBDYShearCalculator,
    calculate_capacity_shear_demand,
    capacity_design_ve_le_vr_check,
)
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
    shear = _append_capacity_design_shear_check(context, shear, flexure)

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


def _append_capacity_design_shear_check(
    context: BeamModelContext,
    shear: ShearResult,
    flexure: FlexureResult,
) -> ShearResult:
    """Append existing O3 capacity-design Ve <= Vr check without changing formulas."""

    if any(check.name == "beam_shear_capacity_design_ve_le_vr" for check in shear.checks):
        return shear

    capacity_demand = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=flexure.top_plastic_moment_kNm,
        right_plastic_moment_kNm=flexure.bottom_plastic_moment_kNm,
        Ln_mm=context.Ln_mm,
        gravity_shear_kN=abs(context.Vd_left_kN) if context.Vd_left_kN is not None else None,
    )

    capacity_check = capacity_design_ve_le_vr_check(
        capacity_shear_demand=capacity_demand,
        Vr_kN=shear.Vr_kN,
        Vc_kN=shear.Vc_kN,
        Vw_kN=shear.Vw_kN,
        Asw_mm2=shear.Asw_mm2,
        fywd_mpa=context.fywd_mpa,
        d_mm=context.d_mm,
        stirrup_spacing_mm=context.stirrup_spacing_mm,
    )

    checks = tuple(shear.checks) + (capacity_check,)
    status = _aggregate_status(*(check.status for check in checks))

    return replace(shear, checks=checks, status=status)


def _aggregate_status(*statuses: str) -> str:
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if any(status == "NO_DATA" for status in statuses):
        return "NO_DATA"
    return "OK"