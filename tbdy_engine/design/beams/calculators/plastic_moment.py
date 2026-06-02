"""
Pure plastic moment capacity kernel.
Single-reinforced rectangular section: As → Mpr.
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
STATUS_NO_REINFORCEMENT = "NO_REINFORCEMENT"
STATUS_COMPRESSION_BLOCK_EXCEEDS_SECTION = "COMPRESSION_BLOCK_EXCEEDS_SECTION"


# =============================================================================
# Input / Output
# =============================================================================

@dataclass(frozen=True)
class PlasticMomentInput:
    """Plastik moment girdisi — birim: mm, MPa, cm²"""
    As_cm2: float
    bw_mm: float
    d_mm: float
    fcd_mpa: float
    fyk_mpa: float
    alpha: float = 0.85
    beta: float = 0.85
    steel_overstrength: float = 1.25


@dataclass(frozen=True)
class PlasticMomentResult:
    """Plastik moment sonucu"""
    status: str = "NOT_EVALUATED"
    As_cm2: float = 0.0
    As_mm2: float = 0.0
    fs_capacity_mpa: float = 0.0
    Mpr_kNm: float = 0.0
    a_mm: float = 0.0
    c_mm: float = 0.0
    lever_arm_z_mm: float = 0.0
    rho: float = 0.0
    neutral_axis_ratio: float = 0.0
    evidence: Mapping[str, object] = field(default_factory=dict)


# =============================================================================
# Core Function
# =============================================================================

def plastic_moment(input_data: PlasticMomentInput) -> PlasticMomentResult:
    """
    Compute plastic moment capacity for single-reinforced rectangular section.

    fs_capacity = steel_overstrength * fyk
    a = As * fs_capacity / (alpha * fcd * bw)
    z = d - a/2
    Mpr = As * fs_capacity * z
    """
    # -----------------------------------------------------------------
    # 1. Input validation
    # -----------------------------------------------------------------
    invalid: list[str] = []

    if input_data.As_cm2 < 0:
        invalid.append("As_cm2 < 0")
    if input_data.bw_mm <= 0:
        invalid.append("bw_mm <= 0")
    if input_data.d_mm <= 0:
        invalid.append("d_mm <= 0")
    if input_data.fcd_mpa <= 0:
        invalid.append("fcd_mpa <= 0")
    if input_data.fyk_mpa <= 0:
        invalid.append("fyk_mpa <= 0")
    if input_data.alpha <= 0:
        invalid.append("alpha <= 0")
    if input_data.beta <= 0:
        invalid.append("beta <= 0")
    if input_data.steel_overstrength <= 0:
        invalid.append("steel_overstrength <= 0")

    if invalid:
        return PlasticMomentResult(
            status=STATUS_INVALID_INPUT,
            evidence={
                "method": "plastic_moment_single_reinforced_rectangular",
                "invalid_inputs": tuple(invalid),
            },
        )

    # -----------------------------------------------------------------
    # 2. Zero reinforcement
    # -----------------------------------------------------------------
    if input_data.As_cm2 == 0:
        return PlasticMomentResult(
            status=STATUS_NO_REINFORCEMENT,
            As_cm2=0.0,
            As_mm2=0.0,
            evidence={
                "method": "plastic_moment_single_reinforced_rectangular",
                "reason": "As_cm2 == 0",
            },
        )

    # -----------------------------------------------------------------
    # 3. Compute
    # -----------------------------------------------------------------
    As_mm2 = input_data.As_cm2 * 100.0
    fs_capacity_mpa = input_data.steel_overstrength * input_data.fyk_mpa

    a_mm = As_mm2 * fs_capacity_mpa / (
        input_data.alpha * input_data.fcd_mpa * input_data.bw_mm
    )
    c_mm = a_mm / input_data.beta if input_data.beta > 0 else 0.0
    lever_arm_z_mm = input_data.d_mm - a_mm / 2.0
    area_bd_mm2 = input_data.bw_mm * input_data.d_mm

    # -----------------------------------------------------------------
    # 4. Sanity check
    # -----------------------------------------------------------------
    if a_mm >= input_data.d_mm or lever_arm_z_mm <= 0:
        return PlasticMomentResult(
            status=STATUS_COMPRESSION_BLOCK_EXCEEDS_SECTION,
            As_cm2=input_data.As_cm2,
            As_mm2=As_mm2,
            fs_capacity_mpa=fs_capacity_mpa,
            a_mm=a_mm,
            c_mm=c_mm,
            lever_arm_z_mm=lever_arm_z_mm,
            rho=As_mm2 / area_bd_mm2 if area_bd_mm2 > 0 else 0.0,
            neutral_axis_ratio=c_mm / input_data.d_mm if input_data.d_mm > 0 else 0.0,
            evidence={
                "method": "plastic_moment_single_reinforced_rectangular",
                "reason": "compression block exceeds effective depth",
                "formula_a": "a = As*fs_capacity/(alpha*fcd*bw)",
                "alpha": input_data.alpha,
                "beta": input_data.beta,
                "steel_overstrength": input_data.steel_overstrength,
                "units": "mm_N_MPa",
            },
        )

    # -----------------------------------------------------------------
    # 5. Moment
    # -----------------------------------------------------------------
    Mpr_Nmm = As_mm2 * fs_capacity_mpa * lever_arm_z_mm
    Mpr_kNm = Mpr_Nmm / 1_000_000.0

    # -----------------------------------------------------------------
    # 6. Return
    # -----------------------------------------------------------------
    return PlasticMomentResult(
        status=STATUS_OK,
        As_cm2=input_data.As_cm2,
        As_mm2=As_mm2,
        fs_capacity_mpa=fs_capacity_mpa,
        Mpr_kNm=Mpr_kNm,
        a_mm=a_mm,
        c_mm=c_mm,
        lever_arm_z_mm=lever_arm_z_mm,
        rho=As_mm2 / area_bd_mm2 if area_bd_mm2 > 0 else 0.0,
        neutral_axis_ratio=c_mm / input_data.d_mm if input_data.d_mm > 0 else 0.0,
        evidence={
            "method": "plastic_moment_single_reinforced_rectangular",
            "formula_fs_capacity": "fs_capacity = steel_overstrength * fyk",
            "formula_a": "a = As * fs_capacity / (alpha * fcd * bw)",
            "formula_c": "c = a / beta",
            "formula_z": "z = d - a/2",
            "formula_Mpr": "Mpr = As * fs_capacity * z",
            "alpha": input_data.alpha,
            "beta": input_data.beta,
            "steel_overstrength": input_data.steel_overstrength,
            "fs_capacity_mpa": fs_capacity_mpa,
            "units": "mm_N_MPa",
            "policy_note": "Plastic moment policy pending code-article benchmark",
        },
    )
