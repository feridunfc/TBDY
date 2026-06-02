"""
Pure Md-to-As flexure kernel.
Single-reinforced rectangular section.
Deterministic binary-search solution.
No external model adapters or postprocessing dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# =============================================================================
# Input / Output
# =============================================================================

@dataclass(frozen=True)
class FlexureMdToAsInput:
    """Eğilme tasarımı girdisi — birim: mm, kNm, MPa"""
    Md_kNm: float
    bw_mm: float
    d_mm: float
    fcd_mpa: float
    fyd_mpa: float
    alpha: float = 0.85
    beta: float = 0.85


@dataclass(frozen=True)
class FlexureMdToAsResult:
    """Eğilme tasarımı sonucu"""
    status: str = "NOT_EVALUATED"
    As_required_mm2: float = 0.0
    a_mm: float = 0.0
    c_mm: float = 0.0
    neutral_axis_ratio: float = 0.0
    lever_arm_z_mm: float = 0.0
    Mu_check_kNm: float = 0.0
    rho_required: float = 0.0
    iterations: int = 0
    evidence: Mapping[str, object] = field(default_factory=dict)

    @property
    def As_required_cm2(self) -> float:
        return self.As_required_mm2 / 100.0


# =============================================================================
# Status Constants
# =============================================================================

STATUS_OK = "OK"
STATUS_INVALID_INPUT = "INVALID_INPUT"
STATUS_NO_TENSION_REINFORCEMENT = "NO_TENSION_REINFORCEMENT_REQUIRED"
STATUS_NO_CONVERGENCE = "NO_CONVERGENCE"


# =============================================================================
# Core Functions
# =============================================================================

def _compute_mu(As_mm2: float, d_mm: float, fyd_mpa: float, fcd_mpa: float,
                bw_mm: float, alpha: float) -> float:
    """Verilen As için moment kapasitesi (Nmm)."""
    if As_mm2 <= 0:
        return 0.0
    a_mm = (As_mm2 * fyd_mpa) / (alpha * fcd_mpa * bw_mm)
    z_mm = d_mm - a_mm / 2.0
    return As_mm2 * fyd_mpa * z_mm  # Nmm


def _compute_a_mm(As_mm2: float, fyd_mpa: float, fcd_mpa: float,
                  bw_mm: float, alpha: float) -> float:
    """Basınç bloğu derinliği (mm)."""
    if As_mm2 <= 0 or fcd_mpa <= 0 or bw_mm <= 0:
        return 0.0
    return (As_mm2 * fyd_mpa) / (alpha * fcd_mpa * bw_mm)


def flexure_md_to_as(input_data: FlexureMdToAsInput) -> FlexureMdToAsResult:
    """
    Md → As_required via deterministic binary search.

    Args:
        input_data: FlexureMdToAsInput with Md_kNm, bw_mm, d_mm, fcd_mpa, fyd_mpa.

    Returns:
        FlexureMdToAsResult with As_required_mm2, a_mm, c_mm, Mu_check_kNm, evidence.
    """
    # -----------------------------------------------------------------
    # 1. Input validation
    # -----------------------------------------------------------------
    invalid: list[str] = []

    if input_data.Md_kNm < 0:
        invalid.append("Md_kNm < 0")
    if input_data.bw_mm <= 0:
        invalid.append("bw_mm <= 0")
    if input_data.d_mm <= 0:
        invalid.append("d_mm <= 0")
    if input_data.fcd_mpa <= 0:
        invalid.append("fcd_mpa <= 0")
    if input_data.fyd_mpa <= 0:
        invalid.append("fyd_mpa <= 0")
    if input_data.alpha <= 0:
        invalid.append("alpha <= 0")
    if input_data.beta <= 0:
        invalid.append("beta <= 0")

    if invalid:
        return FlexureMdToAsResult(
            status=STATUS_INVALID_INPUT,
            evidence={
                "method": "binary_search_single_reinforced_rectangular",
                "invalid_inputs": tuple(invalid),
                "formula_Mu": "Mu = As * fyd * (d - a/2)",
                "formula_a": "a = As * fyd / (alpha * fcd * bw)",
                "formula_c": "c = a / beta",
                "alpha": input_data.alpha,
                "beta": input_data.beta,
                "units": "mm_N_MPa",
            },
        )

    # -----------------------------------------------------------------
    # 2. Zero moment → no tension reinforcement
    # -----------------------------------------------------------------
    if input_data.Md_kNm <= 0:
        return FlexureMdToAsResult(
            status=STATUS_NO_TENSION_REINFORCEMENT,
            As_required_mm2=0.0,
            a_mm=0.0,
            c_mm=0.0,
            neutral_axis_ratio=0.0,
            lever_arm_z_mm=input_data.d_mm,
            Mu_check_kNm=0.0,
            rho_required=0.0,
            iterations=0,
            evidence={
                "method": "binary_search_single_reinforced_rectangular",
                "reason": "Md <= 0, no tension reinforcement required",
                "alpha": input_data.alpha,
                "beta": input_data.beta,
                "units": "mm_N_MPa",
            },
        )

    # -----------------------------------------------------------------
    # 3. Binary search setup
    # -----------------------------------------------------------------
    Md_Nmm = input_data.Md_kNm * 1_000_000.0  # kNm → Nmm
    tolerance = 0.001  # %0.1 tolerans
    max_iterations = 200
    As_high_initial_factor = 2.0  # FIX: was 1000, now reasonable initial guess multiplier

    # Alt sınır
    As_low = 0.0

    # Üst sınır tahmini: Md / (fyd * 0.9d)
    As_high = Md_Nmm / (input_data.fyd_mpa * 0.9 * input_data.d_mm)
    As_high *= As_high_initial_factor

    # Üst sınır yeterli mi kontrol et
    Mu_high = _compute_mu(As_high, input_data.d_mm, input_data.fyd_mpa,
                          input_data.fcd_mpa, input_data.bw_mm, input_data.alpha)

    safety_iterations = 0
    while Mu_high < Md_Nmm and safety_iterations < 100:
        As_high *= 2.0
        Mu_high = _compute_mu(As_high, input_data.d_mm, input_data.fyd_mpa,
                              input_data.fcd_mpa, input_data.bw_mm, input_data.alpha)
        safety_iterations += 1

    if Mu_high < Md_Nmm:
        return FlexureMdToAsResult(
            status=STATUS_NO_CONVERGENCE,
            evidence={
                "method": "binary_search_single_reinforced_rectangular",
                "reason": f"Upper bound search failed after {safety_iterations} doublings",
                "Md_Nmm": Md_Nmm,
                "last_Mu_Nmm": Mu_high,
                "last_As_mm2": As_high,
                "alpha": input_data.alpha,
                "beta": input_data.beta,
                "units": "mm_N_MPa",
            },
        )

    # -----------------------------------------------------------------
    # 4. Binary search
    # -----------------------------------------------------------------
    As_mid = 0.0
    iterations = 0

    for iterations in range(1, max_iterations + 1):
        As_mid = (As_low + As_high) / 2.0
        Mu_mid = _compute_mu(As_mid, input_data.d_mm, input_data.fyd_mpa,
                             input_data.fcd_mpa, input_data.bw_mm, input_data.alpha)

        if abs(Mu_mid - Md_Nmm) / Md_Nmm <= tolerance:
            break

        if Mu_mid < Md_Nmm:
            As_low = As_mid
        else:
            As_high = As_mid

    # Güvenli tarafta kal: Mu >= Md
    As_final = As_mid
    Mu_final = _compute_mu(As_final, input_data.d_mm, input_data.fyd_mpa,
                           input_data.fcd_mpa, input_data.bw_mm, input_data.alpha)

    if Mu_final < Md_Nmm:
        # Bir adım daha büyüt
        As_final = As_high
        Mu_final = _compute_mu(As_final, input_data.d_mm, input_data.fyd_mpa,
                               input_data.fcd_mpa, input_data.bw_mm, input_data.alpha)

    # -----------------------------------------------------------------
    # 5. Geometry calculations
    # -----------------------------------------------------------------
    a_mm = _compute_a_mm(As_final, input_data.fyd_mpa, input_data.fcd_mpa,
                         input_data.bw_mm, input_data.alpha)
    c_mm = a_mm / input_data.beta if input_data.beta > 0 else 0.0
    neutral_axis_ratio = c_mm / input_data.d_mm if input_data.d_mm > 0 else 0.0
    lever_arm_z_mm = input_data.d_mm - a_mm / 2.0
    rho_required = As_final / (input_data.bw_mm * input_data.d_mm) if input_data.bw_mm * input_data.d_mm > 0 else 0.0
    Mu_check_kNm = Mu_final / 1_000_000.0

    # -----------------------------------------------------------------
    # 6. Result
    # -----------------------------------------------------------------
    return FlexureMdToAsResult(
        status=STATUS_OK,
        As_required_mm2=As_final,
        a_mm=a_mm,
        c_mm=c_mm,
        neutral_axis_ratio=neutral_axis_ratio,
        lever_arm_z_mm=lever_arm_z_mm,
        Mu_check_kNm=Mu_check_kNm,
        rho_required=rho_required,
        iterations=iterations,
        evidence={
            "method": "binary_search_single_reinforced_rectangular",
            "formula_Mu": "Mu = As * fyd * (d - a/2)",
            "formula_a": "a = As * fyd / (alpha * fcd * bw)",
            "formula_c": "c = a / beta",
            "Md_kNm": input_data.Md_kNm,
            "Md_Nmm": Md_Nmm,
            "Mu_Nmm": Mu_final,
            "Mu_ge_Md": Mu_final >= Md_Nmm,
            "alpha": input_data.alpha,
            "beta": input_data.beta,
            "tolerance": tolerance,
            "max_iterations": max_iterations,
            "units": "mm_N_MPa",
        },
    )
