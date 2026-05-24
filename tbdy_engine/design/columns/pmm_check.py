"""
tbdy/design_engine/modules/pmm_check.py

Kolon PMM (eksenel + iki eksenli moment) kapasite kontrolu.
TBDY 2018 Madde 7.3.3 - Betonarme kolon etkilesim diyagrami.

Strateji (oncelik sirasi):
1. ETABS design summary PMM ratio (varsa)
2. Basitlestirilmis bagimsiz PMM (karsilikli etkilesim)
3. NO_DATA
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import json


# =============================================================================
# PMM RESULT
# =============================================================================

@dataclass
class PMMResult:
    """
    PMM kontrol sonucu.

    TBDY 2018 Madde 7.3.3 uyarinca:
    Nd <= Nrd  VE  (Mxd/Mrxd)^α + (Myd/Mryd)^β <= 1.0
    """
    column_label: str
    status: str = "NO_DATA"  # OK, FAIL, NO_DATA
    source: str = "none"  # etabs, simplified, none

    # Eksenel
    Nd_kn: float = 0.0  # tasarim eksenel yuku
    Nrd_kn: float = 0.0  # eksenel kapasite
    axial_ratio: float = 0.0  # Nd/Nrd

    # Momentler
    Mxd_knm: float = 0.0  # x yonu tasarim momenti
    Myd_knm: float = 0.0  # y yonu tasarim momenti
    Mrxd_knm: float = 0.0  # x yonu moment kapasitesi
    Mryd_knm: float = 0.0  # y yonu moment kapasitesi

    # Etkilesim
    alpha: float = 1.0  # etkilesim ussu (x)
    beta: float = 1.0  # etkilesim ussu (y)
    interaction_ratio: float = 0.0  # (Mx/Mrx)^α + (My/Mry)^β
    governing_ratio: float = 0.0  # max(axial_ratio, interaction_ratio)

    # ETABS (varsa)
    etabs_pmm_ratio: Optional[float] = None
    etabs_design_case: Optional[str] = None

    # Detay
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_ok(self) -> bool:
        return self.status == "OK"

    @property
    def is_fail(self) -> bool:
        return self.status == "FAIL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_label": self.column_label,
            "status": self.status,
            "source": self.source,
            "demands": {
                "Nd_kn": round(self.Nd_kn, 1),
                "Mxd_knm": round(self.Mxd_knm, 1),
                "Myd_knm": round(self.Myd_knm, 1),
            },
            "capacities": {
                "Nrd_kn": round(self.Nrd_kn, 1),
                "Mrxd_knm": round(self.Mrxd_knm, 1),
                "Mryd_knm": round(self.Mryd_knm, 1),
            },
            "ratios": {
                "axial_ratio": round(self.axial_ratio, 4),
                "interaction_ratio": round(self.interaction_ratio, 4),
                "governing_ratio": round(self.governing_ratio, 4),
                "alpha": self.alpha,
                "beta": self.beta,
            },
            "etabs": {
                "pmm_ratio": self.etabs_pmm_ratio,
                "design_case": self.etabs_design_case,
            } if self.etabs_pmm_ratio is not None else None,
            "message": self.message,
            "details": self.details,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# =============================================================================
# BASITLESTIRILMIS PMM HESABI
# =============================================================================

def _compute_steel_areas(
        As_total_mm2: float,
        n_bars: int,
        arrangement: str = "uniform",
) -> Tuple[float, float, float, float]:
    """
    Donati dagilimini coz.

    Returns:
        As_corner: kose donatilari toplami (mm2)
        As_face_x: x yuzu donatilari (mm2)
        As_face_y: y yuzu donatilari (mm2)
        As_interior: ic donatilar (mm2)
    """
    area_per_bar = As_total_mm2 / n_bars if n_bars > 0 else 0

    # Basitlestirilmis: uniform dagilim
    n_corners = 4
    n_faces = n_bars - n_corners
    n_face_x = n_faces // 2 if n_faces >= 2 else 0
    n_face_y = n_faces - n_face_x

    return (
        n_corners * area_per_bar,
        n_face_x * area_per_bar,
        n_face_y * area_per_bar,
        0.0,  # interior
    )


def _compute_plastic_centroid(
        b_m: float,
        h_m: float,
        cover_m: float,
        As_total_mm2: float,
        fcd_mpa: float,
        fyd_mpa: float,
) -> float:
    """Plastik merkez (basitlestirilmis: geometrik merkez)"""
    return h_m / 2


def _compute_axial_capacity(
        Ac_m2: float,
        As_mm2: float,
        fcd_mpa: float,
        fyd_mpa: float,
) -> float:
    """
    Saf eksenel basinc kapasitesi.

    Nrd = 0.85 * fcd * Ac + fyd * As  (TS500)
    """
    Ac_mm2 = Ac_m2 * 1e6
    Nrd_N = 0.85 * fcd_mpa * Ac_mm2 + fyd_mpa * As_mm2
    return Nrd_N / 1000  # kN


def _compute_moment_capacity_uniaxial(
        b_m: float,
        h_m: float,
        cover_m: float,
        As_face_mm2: float,
        As_corner_mm2: float,
        Nd_kn: float,
        fcd_mpa: float,
        fyd_mpa: float,
) -> float:
    """
    Tek eksenli basitlestirilmis moment kapasitesi.

    Yaklasim: Esdeger gerilme blogu (TS500)
    Tarafsiz eksen derinligi iteratif degil, eksenel yukten tahmin.

    Mrd ~ As_face * fyd * (h - 2*cover) * (1 - 0.5 * ω)
    ω = (As * fyd) / (Ac * fcd)
    """
    d = h_m - cover_m  # faydali yukseklik
    Ac_mm2 = b_m * h_m * 1e6
    As_total = As_face_mm2 + As_corner_mm2

    if Ac_mm2 <= 0 or fcd_mpa <= 0:
        return 0.0

    # Mekanik donati orani
    omega = (As_total * fyd_mpa) / (Ac_mm2 * fcd_mpa)
    omega = min(omega, 0.4)  # dengeli donati siniri

    # Moment kolu
    z = d * (1 - 0.4 * omega)  # yaklasik
    z = max(z, 0.1)

    # Moment kapasitesi
    Mrd_Nmm = As_total * fyd_mpa * z * 1000  # Nmm
    Mrd_knm = Mrd_Nmm / 1e6

    # Eksenel yuk etkisi (Nd > 0 basinc)
    if Nd_kn > 0:
        Nd_MN = Nd_kn / 1000
        n = Nd_MN / (Ac_mm2 * fcd_mpa / 1e6) if Ac_mm2 > 0 else 0
        # Moment kapasitesi artar (basinc)
        enhancement = 1.0 + 1.5 * n * (1 - n)  # yaklasik etkilesim
        Mrd_knm *= max(enhancement, 0.5)
    else:
        # Cekme: azalir
        reduction = max(0.0, 1.0 + Nd_kn / 500)  # ampirik
        Mrd_knm *= reduction

    return Mrd_knm


def _compute_interaction_exponent(
        Nd_kn: float,
        Nrd_kn: float,
) -> Tuple[float, float]:
    """
    Etkilesim usleri α, β (TBDY 2018 Denklem 7.3)

    Nd/Nrd <= 0.2 → α = β = 1.0
    0.2 < Nd/Nrd <= 0.5 → α = β = 1.5
    Nd/Nrd > 0.5 → α = β = 2.0
    """
    ratio = abs(Nd_kn) / Nrd_kn if Nrd_kn > 0 else 1.0

    if ratio <= 0.2:
        return 1.0, 1.0
    elif ratio <= 0.5:
        return 1.5, 1.5
    else:
        return 2.0, 2.0


# =============================================================================
# PMM CHECKER
# =============================================================================

class PMMChecker:
    """
    Kolon PMM kontrolu.

    Kullanim:
        checker = PMMChecker()
        result = checker.check(
            column_label="C1",
            Nd_kn=-1500,
            Mxd_knm=120,
            Myd_knm=50,
            width_m=0.5,
            depth_m=0.5,
            fcd_mpa=20,
            fyd_mpa=365,
            As_total_mm2=1200,
            n_bars=8,
        )
    """

    def __init__(self):
        self.cover_m = 0.04  # varsayilan paspayi (m)

    def check(
            self,
            column_label: str,
            Nd_kn: float,
            Mxd_knm: float,
            Myd_knm: float,
            width_m: float,
            depth_m: float,
            fcd_mpa: float,
            fyd_mpa: float,
            As_total_mm2: float,
            n_bars: int,
            etabs_pmm_ratio: Optional[float] = None,
            etabs_design_case: Optional[str] = None,
    ) -> PMMResult:
        """
        PMM kontrolunu calistir.

        Returns:
            PMMResult
        """
        # ETABS varsa dogrudan kullan
        if etabs_pmm_ratio is not None:
            status = "OK" if etabs_pmm_ratio <= 1.0 else "FAIL"
            return PMMResult(
                column_label=column_label,
                status=status,
                source="etabs",
                Nd_kn=Nd_kn,
                Mxd_knm=Mxd_knm,
                Myd_knm=Myd_knm,
                etabs_pmm_ratio=etabs_pmm_ratio,
                etabs_design_case=etabs_design_case,
                governing_ratio=etabs_pmm_ratio,
                message=f"ETABS PMM ratio = {etabs_pmm_ratio:.3f}",
            )

        # Bagimsiz basitlestirilmis hesap
        if fcd_mpa <= 0 or fyd_mpa <= 0 or width_m <= 0 or depth_m <= 0:
            return PMMResult(
                column_label=column_label,
                status="NO_DATA",
                source="none",
                Nd_kn=Nd_kn,
                Mxd_knm=Mxd_knm,
                Myd_knm=Myd_knm,
                message="Yetersiz malzeme/geometri verisi",
            )

        # Donati dagilimi
        As_corner, As_face_x, As_face_y, _ = _compute_steel_areas(
            As_total_mm2, n_bars
        )

        Ac_m2 = width_m * depth_m

        # Kapasiteler
        Nrd = _compute_axial_capacity(Ac_m2, As_total_mm2, fcd_mpa, fyd_mpa)
        Mrxd = _compute_moment_capacity_uniaxial(
            depth_m, width_m, self.cover_m,
            As_face_x, As_corner,
            Nd_kn, fcd_mpa, fyd_mpa,
        )
        Mryd = _compute_moment_capacity_uniaxial(
            width_m, depth_m, self.cover_m,
            As_face_y, As_corner,
            Nd_kn, fcd_mpa, fyd_mpa,
        )

        # Oranlar
        axial_ratio = abs(Nd_kn) / Nrd if Nrd > 0 else 999

        alpha, beta = _compute_interaction_exponent(Nd_kn, Nrd)

        # Etkilesim
        ratio_x = abs(Mxd_knm) / Mrxd if Mrxd > 0 else 999
        ratio_y = abs(Myd_knm) / Mryd if Mryd > 0 else 999

        interaction_ratio = (ratio_x ** alpha) + (ratio_y ** beta)
        governing_ratio = max(axial_ratio, interaction_ratio)

        # Status
        if axial_ratio > 1.0 or interaction_ratio > 1.0:
            status = "FAIL"
        else:
            status = "OK"

        return PMMResult(
            column_label=column_label,
            status=status,
            source="simplified",
            Nd_kn=Nd_kn,
            Nrd_kn=Nrd,
            axial_ratio=axial_ratio,
            Mxd_knm=Mxd_knm,
            Myd_knm=Myd_knm,
            Mrxd_knm=Mrxd,
            Mryd_knm=Mryd,
            alpha=alpha,
            beta=beta,
            interaction_ratio=interaction_ratio,
            governing_ratio=governing_ratio,
            message=f"Basitlestirilmis PMM: axial={axial_ratio:.3f}, interaction={interaction_ratio:.3f}",
            details={
                "As_total_mm2": As_total_mm2,
                "n_bars": n_bars,
                "As_corner": round(As_corner, 1),
                "As_face_x": round(As_face_x, 1),
                "As_face_y": round(As_face_y, 1),
                "omega_x": round((As_face_x + As_corner) * fyd_mpa / (width_m * depth_m * 1e6 * fcd_mpa),
                                 4) if fcd_mpa > 0 else 0,
            },
        )


# =============================================================================
# CONVENIENCE
# =============================================================================

# Global singleton
pmm_checker = PMMChecker()


def check_pmm(
        column_label: str,
        Nd_kn: float,
        Mxd_knm: float,
        Myd_knm: float,
        width_m: float,
        depth_m: float,
        fcd_mpa: float,
        fyd_mpa: float,
        As_total_mm2: float,
        n_bars: int = 8,
        etabs_pmm_ratio: Optional[float] = None,
) -> PMMResult:
    """
    Convenience function: PMM kontrolu yap.

    Args:
        column_label: Kolon etiketi
        Nd_kn: Tasarim eksenel yuku (kN, basinc +)
        Mxd_knm: X yonu tasarim momenti
        Myd_knm: Y yonu tasarim momenti
        width_m: Kesit genisligi (m)
        depth_m: Kesit yuksekligi (m)
        fcd_mpa: Beton tasarim dayanimi
        fyd_mpa: Donati tasarim dayanimi
        As_total_mm2: Toplam boyuna donati alani
        n_bars: Donati adedi
        etabs_pmm_ratio: ETABS PMM orani (varsa)

    Returns:
        PMMResult
    """
    return pmm_checker.check(
        column_label=column_label,
        Nd_kn=Nd_kn,
        Mxd_knm=Mxd_knm,
        Myd_knm=Myd_knm,
        width_m=width_m,
        depth_m=depth_m,
        fcd_mpa=fcd_mpa,
        fyd_mpa=fyd_mpa,
        As_total_mm2=As_total_mm2,
        n_bars=n_bars,
        etabs_pmm_ratio=etabs_pmm_ratio,
    )