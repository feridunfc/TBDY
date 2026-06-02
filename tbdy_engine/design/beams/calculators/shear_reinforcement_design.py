"""
Pure shear reinforcement spacing requirement kernel.
V_design → Vc, Vs_required, s_required, s_limited.
No external model adapters or postprocessing dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from typing import Any, Mapping


# =============================================================================
# Status Constants
# =============================================================================

STATUS_OK = "OK"
STATUS_INVALID_INPUT = "INVALID_INPUT"
STATUS_MIN_SHEAR_REINFORCEMENT_GOVERNS = "MIN_SHEAR_REINFORCEMENT_GOVERNS"
STATUS_SHEAR_REINFORCEMENT_REQUIRED = "SHEAR_REINFORCEMENT_REQUIRED"


# =============================================================================
# Input / Output
# =============================================================================

@dataclass(frozen=True)
class ShearReinforcementDesignInput:
    """Kesme donatısı tasarım girdisi — birim: mm, kN, MPa"""
    V_design_kN: float
    bw_mm: float
    d_mm: float
    fctd_mpa: float
    fywd_mpa: float
    stirrup_diameter_mm: float
    stirrup_legs: int
    cot_theta: float = 1.0
    vc_factor: float = 0.65
    s_max_mm: float = 200.0


@dataclass(frozen=True)
class ShearReinforcementDesignResult:
    """Kesme donatısı tasarım sonucu"""
    status: str = "NOT_EVALUATED"
    V_design_kN: float = 0.0
    Vc_kN: float = 0.0
    Vs_required_kN: float = 0.0
    bar_area_mm2: float = 0.0
    Asw_per_stirrup_mm2: float = 0.0
    s_required_mm: float | None = None
    s_required_limited_mm: float | None = None
    s_max_mm: float = 0.0
    governing: str = ""
    evidence: Mapping[str, object] = field(default_factory=dict)


# =============================================================================
# Core Function
# =============================================================================

def shear_reinforcement_design(
    input_data: ShearReinforcementDesignInput,
) -> ShearReinforcementDesignResult:
    """
    Compute required stirrup spacing from design shear force.

    Vc = vc_factor * fctd * bw * d
    Vs_required = max(V_design - Vc, 0)
    s = Asw * fywd * d * cot_theta / Vs_required
    """
    # -----------------------------------------------------------------
    # 1. Input validation
    # -----------------------------------------------------------------
    invalid: list[str] = []

    if input_data.V_design_kN < 0:
        invalid.append("V_design_kN < 0")
    if input_data.bw_mm <= 0:
        invalid.append("bw_mm <= 0")
    if input_data.d_mm <= 0:
        invalid.append("d_mm <= 0")
    if input_data.fctd_mpa <= 0:
        invalid.append("fctd_mpa <= 0")
    if input_data.fywd_mpa <= 0:
        invalid.append("fywd_mpa <= 0")
    if input_data.stirrup_diameter_mm <= 0:
        invalid.append("stirrup_diameter_mm <= 0")
    if input_data.stirrup_legs <= 0:
        invalid.append("stirrup_legs <= 0")
    if input_data.cot_theta <= 0:
        invalid.append("cot_theta <= 0")
    if input_data.vc_factor < 0:
        invalid.append("vc_factor < 0")
    if input_data.s_max_mm <= 0:
        invalid.append("s_max_mm <= 0")

    if invalid:
        return ShearReinforcementDesignResult(
            status=STATUS_INVALID_INPUT,
            evidence={
                "method": "shear_reinforcement_spacing_requirement",
                "invalid_inputs": tuple(invalid),
            },
        )

    # -----------------------------------------------------------------
    # 2. Concrete contribution
    # -----------------------------------------------------------------
    Vc_N = input_data.vc_factor * input_data.fctd_mpa * input_data.bw_mm * input_data.d_mm
    Vc_kN = Vc_N / 1000.0

    # -----------------------------------------------------------------
    # 3. Required steel contribution
    # -----------------------------------------------------------------
    Vs_required_kN = max(input_data.V_design_kN - Vc_kN, 0.0)

    # -----------------------------------------------------------------
    # 4. Stirrup geometry
    # -----------------------------------------------------------------
    bar_area_mm2 = pi * input_data.stirrup_diameter_mm ** 2 / 4.0
    Asw_per_stirrup_mm2 = input_data.stirrup_legs * bar_area_mm2

    # -----------------------------------------------------------------
    # 5. Minimum shear reinforcement governs
    # -----------------------------------------------------------------
    if Vs_required_kN <= 0:
        return ShearReinforcementDesignResult(
            status=STATUS_MIN_SHEAR_REINFORCEMENT_GOVERNS,
            V_design_kN=input_data.V_design_kN,
            Vc_kN=Vc_kN,
            Vs_required_kN=0.0,
            bar_area_mm2=bar_area_mm2,
            Asw_per_stirrup_mm2=Asw_per_stirrup_mm2,
            s_required_mm=None,
            s_required_limited_mm=input_data.s_max_mm,
            s_max_mm=input_data.s_max_mm,
            governing="s_max",
            evidence={
                "method": "shear_reinforcement_spacing_requirement",
                "formula_Vc": "Vc = vc_factor * fctd * bw * d",
                "formula_bar_area": "pi * diameter^2 / 4",
                "reason": "V_design <= Vc, minimum detailing governs",
                "vc_factor": input_data.vc_factor,
                "cot_theta": input_data.cot_theta,
                "units": "mm_N_MPa_kN",
                "policy_note": "Minimum shear reinforcement policy pending benchmark",
            },
        )

    # -----------------------------------------------------------------
    # 6. Required spacing
    # -----------------------------------------------------------------
    Vs_required_N = Vs_required_kN * 1000.0

    s_required_mm = (
        Asw_per_stirrup_mm2
        * input_data.fywd_mpa
        * input_data.d_mm
        * input_data.cot_theta
        / Vs_required_N
    )
    s_limited = min(s_required_mm, input_data.s_max_mm)
    governing = "shear" if s_required_mm < input_data.s_max_mm else "s_max"

    # -----------------------------------------------------------------
    # 7. Return
    # -----------------------------------------------------------------
    return ShearReinforcementDesignResult(
        status=STATUS_SHEAR_REINFORCEMENT_REQUIRED,
        V_design_kN=input_data.V_design_kN,
        Vc_kN=Vc_kN,
        Vs_required_kN=Vs_required_kN,
        bar_area_mm2=bar_area_mm2,
        Asw_per_stirrup_mm2=Asw_per_stirrup_mm2,
        s_required_mm=s_required_mm,
        s_required_limited_mm=s_limited,
        s_max_mm=input_data.s_max_mm,
        governing=governing,
        evidence={
            "method": "shear_reinforcement_spacing_requirement",
            "formula_Vc": "Vc = vc_factor * fctd * bw * d",
            "formula_Vs_required": "Vs_required = max(V_design - Vc, 0)",
            "formula_bar_area": "pi * diameter^2 / 4",
            "formula_spacing": "s = Asw * fywd * d * cot_theta / Vs_required",
            "vc_factor": input_data.vc_factor,
            "cot_theta": input_data.cot_theta,
            "units": "mm_N_MPa_kN",
            "policy_note": "Shear reinforcement policy pending code-article benchmark",
        },
    )
