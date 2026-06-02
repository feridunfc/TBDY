"""
Reinforcement verification functions.
Compares provided reinforcement against design results.
Never computes design demand; never mutates design results.
"""

from __future__ import annotations

from .provided_reinforcement import BeamProvidedReinforcement
from .verification_result import (
    BeamVerificationResult,
    VerificationCheck,
    STATUS_PASS,
    STATUS_FAIL,
    STATUS_UNKNOWN,
    overall_status,
)

# Design result imports — allowed for type checking only
# NOTE: Result dataclass imports from calculators are acceptable for R13.
# Future sprint should move shared result types to design_result.py.
from tbdy_engine.design.beams.beam_region_flexure import (
    BeamFlexureRegionDesignResult,
    STATUS_MISSING_DEMAND,
    STATUS_OVER_REINFORCED,
)
from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
    ShearReinforcementDesignResult,
)


# =============================================================================
# Region → Provided Mapping
# =============================================================================

_REGION_TO_PROVIDED: dict[str, str] = {
    "top_left":   "top_left_As_cm2",
    "bottom_mid": "bottom_mid_As_cm2",
    "top_right":  "top_right_As_cm2",
}

_REGION_TO_CHECK_ID: dict[str, str] = {
    "top_left":   "verification:flexure:top_left_as_ge_required",
    "bottom_mid": "verification:flexure:bottom_mid_as_ge_required",
    "top_right":  "verification:flexure:top_right_as_ge_required",
}


# =============================================================================
# Flexure Verification
# =============================================================================

def verify_flexure_regions(
    flexure_region_result: BeamFlexureRegionDesignResult,
    provided: BeamProvidedReinforcement,
) -> tuple[VerificationCheck, ...]:
    """Check provided As against design-required As per region."""
    checks: list[VerificationCheck] = []

    for region_name, provided_attr in _REGION_TO_PROVIDED.items():
        region = flexure_region_result.regions.get(region_name)
        check_id = _REGION_TO_CHECK_ID[region_name]

        if region is None:
            checks.append(VerificationCheck(
                check_id=check_id,
                status=STATUS_UNKNOWN,
                category="flexure",
                message="region result missing",
            ))
            continue

        required = region.As_design_required_cm2
        provided_value = getattr(provided, provided_attr)

        # Missing demand
        if region.status == STATUS_MISSING_DEMAND:
            checks.append(VerificationCheck(
                check_id=check_id,
                status=STATUS_UNKNOWN,
                category="flexure",
                demand_value=required,
                provided_value=provided_value,
                message="design demand missing",
                evidence={"region_status": region.status},
            ))
            continue

        # Over-reinforced
        if region.status == STATUS_OVER_REINFORCED:
            checks.append(VerificationCheck(
                check_id=check_id,
                status=STATUS_FAIL,
                category="flexure",
                demand_value=required,
                provided_value=provided_value,
                message="design required reinforcement exceeds maximum ratio",
                evidence={"region_status": region.status},
            ))
            continue

        # Missing provided
        if provided_value is None:
            checks.append(VerificationCheck(
                check_id=check_id,
                status=STATUS_UNKNOWN,
                category="flexure",
                demand_value=required,
                provided_value=None,
                message="provided reinforcement missing",
            ))
            continue

        # Zero or negative provided
        if provided_value <= 0:
            checks.append(VerificationCheck(
                check_id=check_id,
                status=STATUS_FAIL,
                category="flexure",
                demand_value=required,
                provided_value=provided_value,
                utilization=None,
                message="provided reinforcement must be positive",
            ))
            continue

        # Compare
        utilization = required / provided_value
        status = STATUS_PASS if provided_value >= required else STATUS_FAIL

        checks.append(VerificationCheck(
            check_id=check_id,
            status=status,
            category="flexure",
            demand_value=required,
            provided_value=provided_value,
            utilization=utilization,
            message="provided reinforcement checked against design required area",
            evidence={
                "region": region_name,
                "region_status": region.status,
            },
        ))

    return tuple(checks)


# =============================================================================
# Shear Verification
# =============================================================================

def verify_stirrup_spacing(
    shear_result: ShearReinforcementDesignResult,
    provided: BeamProvidedReinforcement,
) -> tuple[VerificationCheck, ...]:
    """Check provided stirrup spacing against required spacing."""
    check_id = "verification:shear:provided_spacing_le_required"

    if provided.stirrup is None:
        return (VerificationCheck(
            check_id=check_id,
            status=STATUS_UNKNOWN,
            category="shear",
            demand_value=shear_result.s_required_limited_mm,
            provided_value=None,
            message="provided stirrup missing",
        ),)

    required_spacing = shear_result.s_required_limited_mm
    provided_spacing = provided.stirrup.spacing_mm

    if required_spacing is None:
        return (VerificationCheck(
            check_id=check_id,
            status=STATUS_UNKNOWN,
            category="shear",
            demand_value=None,
            provided_value=provided_spacing,
            message="required spacing missing",
        ),)

    # Zero or negative provided spacing
    if provided_spacing <= 0:
        return (VerificationCheck(
            check_id=check_id,
            status=STATUS_FAIL,
            category="shear",
            demand_value=required_spacing,
            provided_value=provided_spacing,
            utilization=None,
            message="provided stirrup spacing must be positive",
        ),)

    utilization = provided_spacing / required_spacing
    status = STATUS_PASS if provided_spacing <= required_spacing else STATUS_FAIL

    return (VerificationCheck(
        check_id=check_id,
        status=status,
        category="shear",
        demand_value=required_spacing,
        provided_value=provided_spacing,
        utilization=utilization,
        message="provided stirrup spacing checked against required spacing",
        evidence={
            "provided_diameter_mm": provided.stirrup.diameter_mm,
            "provided_legs": provided.stirrup.legs,
        },
    ),)


# =============================================================================
# Combined Runner
# =============================================================================

def verify_beam_reinforcement(
    *,
    beam_id: str,
    label: str,
    provided: BeamProvidedReinforcement,
    flexure_region_result: BeamFlexureRegionDesignResult | None = None,
    shear_result: ShearReinforcementDesignResult | None = None,
) -> BeamVerificationResult:
    """
    Run flexure and shear verification checks.

    Design results are never mutated.
    Returns a new BeamVerificationResult.
    """
    # Identity guard
    if beam_id != provided.beam_id or label != provided.label:
        return BeamVerificationResult(
            beam_id=beam_id,
            label=label,
            status=STATUS_UNKNOWN,
            checks=(),
            evidence={
                "method": "beam_reinforcement_verification",
                "invalid_inputs": (
                    f"provided identity mismatch: "
                    f"expected={beam_id}/{label}, "
                    f"provided={provided.beam_id}/{provided.label}",
                ),
            },
        )

    checks: list[VerificationCheck] = []

    if flexure_region_result is not None:
        checks.extend(verify_flexure_regions(flexure_region_result, provided))

    if shear_result is not None:
        checks.extend(verify_stirrup_spacing(shear_result, provided))

    checks_tuple = tuple(checks)

    return BeamVerificationResult(
        beam_id=beam_id,
        label=label,
        status=overall_status(checks_tuple),
        checks=checks_tuple,
        evidence={
            "method": "beam_reinforcement_verification",
            "provided_source": provided.source,
        },
    )
