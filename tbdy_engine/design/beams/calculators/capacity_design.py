"""
Pure capacity design shear force kernel.
Mpr_left + Mpr_right + Vg → Ve_capacity.
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
STATUS_UNSUPPORTED_DIRECTION = "UNSUPPORTED_DIRECTION"


# =============================================================================
# Input / Output
# =============================================================================

@dataclass(frozen=True)
class CapacityDesignVeInput:
    """Kapasite tasarımı kesme girdisi — birim: kNm, kN, mm"""
    Mpr_left_kNm: float
    Mpr_right_kNm: float
    Vg_kN: float
    Ln_mm: float
    direction: str = "absolute"


@dataclass(frozen=True)
class CapacityDesignVeResult:
    """Kapasite tasarımı kesme sonucu"""
    status: str = "NOT_EVALUATED"
    Mpr_left_kNm: float = 0.0
    Mpr_right_kNm: float = 0.0
    Vg_kN: float = 0.0
    Ln_mm: float = 0.0
    plastic_shear_component_kN: float = 0.0
    Ve_capacity_kN: float = 0.0
    direction: str = "absolute"
    evidence: Mapping[str, object] = field(default_factory=dict)


# =============================================================================
# Core Function
# =============================================================================

def capacity_design_ve(input_data: CapacityDesignVeInput) -> CapacityDesignVeResult:
    """
    Compute capacity design shear force from plastic moments.

    plastic_shear = (Mpr_left + Mpr_right) / Ln
    Ve_capacity = abs(plastic_shear) + abs(Vg)
    """
    # -----------------------------------------------------------------
    # 1. Input validation
    # -----------------------------------------------------------------
    invalid: list[str] = []

    if input_data.Mpr_left_kNm < 0:
        invalid.append("Mpr_left_kNm < 0")
    if input_data.Mpr_right_kNm < 0:
        invalid.append("Mpr_right_kNm < 0")
    if input_data.Ln_mm <= 0:
        invalid.append("Ln_mm <= 0")

    if invalid:
        return CapacityDesignVeResult(
            status=STATUS_INVALID_INPUT,
            Mpr_left_kNm=input_data.Mpr_left_kNm,
            Mpr_right_kNm=input_data.Mpr_right_kNm,
            Vg_kN=input_data.Vg_kN,
            Ln_mm=input_data.Ln_mm,
            direction=input_data.direction,
            evidence={
                "method": "capacity_design_ve_absolute_scalar",
                "invalid_inputs": tuple(invalid),
            },
        )

    # -----------------------------------------------------------------
    # 2. Direction check
    # -----------------------------------------------------------------
    if input_data.direction != "absolute":
        return CapacityDesignVeResult(
            status=STATUS_UNSUPPORTED_DIRECTION,
            Mpr_left_kNm=input_data.Mpr_left_kNm,
            Mpr_right_kNm=input_data.Mpr_right_kNm,
            Vg_kN=input_data.Vg_kN,
            Ln_mm=input_data.Ln_mm,
            direction=input_data.direction,
            evidence={
                "method": "capacity_design_ve_absolute_scalar",
                "unsupported_direction": input_data.direction,
                "supported_directions": ("absolute",),
            },
        )

    # -----------------------------------------------------------------
    # 3. Compute
    # -----------------------------------------------------------------
    Ln_m = input_data.Ln_mm / 1000.0
    plastic_shear = (input_data.Mpr_left_kNm + input_data.Mpr_right_kNm) / Ln_m
    Ve = abs(plastic_shear) + abs(input_data.Vg_kN)

    # -----------------------------------------------------------------
    # 4. Return
    # -----------------------------------------------------------------
    return CapacityDesignVeResult(
        status=STATUS_OK,
        Mpr_left_kNm=input_data.Mpr_left_kNm,
        Mpr_right_kNm=input_data.Mpr_right_kNm,
        Vg_kN=input_data.Vg_kN,
        Ln_mm=input_data.Ln_mm,
        plastic_shear_component_kN=plastic_shear,
        Ve_capacity_kN=Ve,
        direction=input_data.direction,
        evidence={
            "method": "capacity_design_ve_absolute_scalar",
            "formula_plastic_shear": "plastic_shear = (Mpr_left + Mpr_right) / Ln",
            "formula_Ve": "Ve = abs(plastic_shear) + abs(Vg)",
            "Ln_m": Ln_m,
            "direction_policy": "absolute scalar capacity demand",
            "units": "kNm_m_kN",
            "policy_note": "Directional left/right capacity shears deferred to later sprint",
        },
    )
