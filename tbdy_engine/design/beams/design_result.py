"""
BeamDesignResult — Design Engine çıktısı.
Sadece engine tarafından üretilir; immutable.
Verification ve crosscheck mutasyona uğratamaz.
Birim standardı: mm, kN, kNm, MPa, cm² (rapor).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class BeamFlexureDesignResult:
    """Tek bölge eğilme tasarım sonucu"""
    region: str = ""
    As_required_cm2: float = 0.0
    a_mm: float = 0.0
    c_mm: float = 0.0
    neutral_axis_ratio: float = 0.0
    lever_arm_z_mm: float = 0.0
    Mu_check_kNm: float = 0.0
    rho_required: float = 0.0
    status: str = "NOT_EVALUATED"
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BeamFlexureLimitResult:
    """Eğilme limit kontrol sonucu"""
    rho_min: float = 0.0
    rho_max: float = 0.0
    As_min_cm2: float = 0.0
    As_max_cm2: float = 0.0
    status: str = "NOT_EVALUATED"
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BeamPlasticMomentResult:
    """Plastik moment kapasitesi"""
    Mpr_kNm: float = 0.0
    a_mm: float = 0.0
    c_mm: float = 0.0
    lever_arm_mm: float = 0.0
    region: str = ""
    status: str = "NOT_EVALUATED"
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BeamCapacityDesignResult:
    """Kapasite tasarımı kesme kuvveti"""
    Ve_capacity_kN: float = 0.0
    plastic_shear_component_kN: float = 0.0
    Vg_kN: float = 0.0
    status: str = "NOT_EVALUATED"
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BeamShearDesignResult:
    """Kesme donatısı tasarım sonucu"""
    Vc_kN: float = 0.0
    Vs_required_kN: float = 0.0
    Asw_required_cm2_per_m: float = 0.0
    s_required_mm: float = 0.0
    status: str = "NOT_EVALUATED"
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BeamDesignResult:
    """
    Design Engine çıktısı — immutable.
    Verification ve crosscheck bu nesneyi değiştiremez.
    """
    beam_id: str
    label: str
    status: str = "NOT_EVALUATED"

    flexure: dict[str, BeamFlexureDesignResult] = field(default_factory=dict)
    flexure_limits: BeamFlexureLimitResult | None = None
    plastic_moments: dict[str, BeamPlasticMomentResult] = field(default_factory=dict)
    capacity_design: BeamCapacityDesignResult | None = None
    shear: BeamShearDesignResult | None = None

    governing_ratio: float = 0.0
    evidence: Mapping[str, object] = field(default_factory=dict)
