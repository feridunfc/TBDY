"""
Pure flexure reinforcement ratio limits kernel.
Determines rho_min, rho_max, and whether moment or minimum reinforcement governs.
No external model adapters or postprocessing dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# =============================================================================
# Status Constants
# =============================================================================

STATUS_OK = "OK"
STATUS_INVALID_INPUT = "INVALID_INPUT"
STATUS_MIN_REINFORCEMENT_GOVERNS = "MIN_REINFORCEMENT_GOVERNS"
STATUS_OVER_REINFORCED = "OVER_REINFORCED"


# =============================================================================
# Input / Output
# =============================================================================

@dataclass(frozen=True)
class FlexureLimitsInput:
    """Eğilme donatı sınır girdisi — birim: mm, MPa, cm²"""
    As_required_cm2: float
    bw_mm: float
    d_mm: float
    fctd_mpa: float
    fyd_mpa: float
    rho_max: float = 0.02


@dataclass(frozen=True)
class FlexureLimitsResult:
    """Eğilme donatı sınır sonucu"""
    status: str = "NOT_EVALUATED"
    As_required_cm2: float = 0.0
    As_min_cm2: float = 0.0
    As_max_cm2: float = 0.0
    As_design_required_cm2: float = 0.0
    rho_required: float = 0.0
    rho_min: float = 0.0
    rho_max: float = 0.0
    governing: str = ""
    evidence: Mapping[str, object] = field(default_factory=dict)


# =============================================================================
# Core Function
# =============================================================================

def flexure_limits(input_data: FlexureLimitsInput) -> FlexureLimitsResult:
    """
    Compute reinforcement ratio limits and determine governing case.

    Args:
        input_data: FlexureLimitsInput (As_required_cm2, bw_mm, d_mm, fctd_mpa, fyd_mpa, rho_max)

    Returns:
        FlexureLimitsResult with rho_min, rho_max, As_min, As_max, status, evidence.
    """
    # -----------------------------------------------------------------
    # 1. Input validation
    # -----------------------------------------------------------------
    invalid: list[str] = []

    if input_data.As_required_cm2 < 0:
        invalid.append("As_required_cm2 < 0")
    if input_data.bw_mm <= 0:
        invalid.append("bw_mm <= 0")
    if input_data.d_mm <= 0:
        invalid.append("d_mm <= 0")
    if input_data.fctd_mpa <= 0:
        invalid.append("fctd_mpa <= 0")
    if input_data.fyd_mpa <= 0:
        invalid.append("fyd_mpa <= 0")
    if input_data.rho_max <= 0:
        invalid.append("rho_max <= 0")

    if invalid:
        return FlexureLimitsResult(
            status=STATUS_INVALID_INPUT,
            evidence={
                "method": "flexure_reinforcement_ratio_limits",
                "invalid_inputs": tuple(invalid),
                "formula_rho_min": "max(0.8*fctd/fyd, 0.001)",
                "formula_rho_required": "As_required / (bw * d)",
                "units": "mm_MPa_cm2",
            },
        )

    # -----------------------------------------------------------------
    # 2. Compute ratios and areas
    # -----------------------------------------------------------------
    area_bd_mm2 = input_data.bw_mm * input_data.d_mm
    As_required_mm2 = input_data.As_required_cm2 * 100.0

    rho_required = As_required_mm2 / area_bd_mm2
    rho_min = max(0.8 * input_data.fctd_mpa / input_data.fyd_mpa, 0.001)

    As_min_cm2 = rho_min * area_bd_mm2 / 100.0
    As_max_cm2 = input_data.rho_max * area_bd_mm2 / 100.0

    # -----------------------------------------------------------------
    # 3. Determine status and governing
    # -----------------------------------------------------------------
    if rho_required > input_data.rho_max:
        status = STATUS_OVER_REINFORCED
        governing = "rho_max"
        As_design_required_cm2 = input_data.As_required_cm2
    elif rho_required < rho_min:
        status = STATUS_MIN_REINFORCEMENT_GOVERNS
        governing = "rho_min"
        As_design_required_cm2 = As_min_cm2
    else:
        status = STATUS_OK
        governing = "moment"
        As_design_required_cm2 = input_data.As_required_cm2

    # -----------------------------------------------------------------
    # 4. Return
    # -----------------------------------------------------------------
    return FlexureLimitsResult(
        status=status,
        As_required_cm2=input_data.As_required_cm2,
        As_min_cm2=As_min_cm2,
        As_max_cm2=As_max_cm2,
        As_design_required_cm2=As_design_required_cm2,
        rho_required=rho_required,
        rho_min=rho_min,
        rho_max=input_data.rho_max,
        governing=governing,
        evidence={
            "method": "flexure_reinforcement_ratio_limits",
            "formula_rho_required": "rho_required = As_required / (bw * d)",
            "formula_rho_min": "rho_min = max(0.8*fctd/fyd, 0.001)",
            "formula_As_min": "As_min = rho_min*bw*d",
            "formula_As_max": "As_max = rho_max*bw*d",
            "area_bd_mm2": area_bd_mm2,
            "units": "mm_MPa_cm2",
        },
    )
