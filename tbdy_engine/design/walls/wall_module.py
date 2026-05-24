"""
tbdy/design_engine/modules/wall_module.py

Tek perde tasarım modülü.
Context builder (ModelContext) üzerinden çalışır.
TBDY 2018 Bölüm 7.6 + TS500 perde kontrollerini içerir.

Checks:
  - geometry        : TBDY 2018 7.6.1 (minimum boyut, kalınlık)
  - axial_flexure   : TBDY 2018 7.6.2 (PMM - perde eksenel+eğilme)
  - shear           : TBDY 2018 7.6.6 + TS500 (kesme güvenliği)
  - boundary_zone   : TBDY 2018 7.6.4 (başlık bölgesi gereksinimi)
  - confinement     : TBDY 2018 7.6.5 (başlık bölgesi sargısı)
  - shear_wall_reinf: TBDY 2018 7.6.3 (gövde donatısı - yatay/düşey)
  - overturning     : TBDY 2018 (devrilme kontrolü - screening)
  - drift_compat    : TBDY 2018 (göreli kat ötelemesi uyumluluğu - screening)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import logging

logger = logging.getLogger("wall_design")


# =============================================================================
# YARDIMCI VERİ YAPILARI
# =============================================================================

@dataclass
class MaterialSet:
    """Beton ve donatı tasarım malzemeleri"""
    fck: float  # MPa
    fcd: float  # MPa
    fyk: float  # MPa
    fyd: float  # MPa
    fywd: float  # MPa
    gamma_c: float
    gamma_s: float
    ecu: float = 0.003
    esy: float = 0.002

    @property
    def fctd(self) -> float:
        """TS500 - Beton eksenel çekme dayanımı"""
        return 0.35 * math.sqrt(self.fck) / self.gamma_c

    @property
    def Ec(self) -> float:
        """TS500 - Beton elastisite modülü (MPa)"""
        return 3250 * math.sqrt(self.fck) + 14000


@dataclass
class WallGeometry:
    """Perde geometrisi"""
    label: str
    story: str
    section_name: str
    length_mm: float  # lw - perde boyu (mm)
    thickness_mm: float  # bw - gövde kalınlığı (mm)
    clear_height_mm: float = 0.0  # Hw - net kat yüksekliği (mm)
    boundary_length_mm: float = 0.0  # başlık bölgesi uzunluğu (varsa)
    boundary_thickness_mm: float = 0.0  # başlık bölgesi kalınlığı
    is_coupled: bool = False  # boşluklu perde mi?
    coupling_beam_label: str = ""  # bağ kirişi etiketi

    @property
    def lw_m(self) -> float:
        return self.length_mm / 1000.0

    @property
    def bw_m(self) -> float:
        return self.thickness_mm / 1000.0

    @property
    def hw_m(self) -> float:
        return self.clear_height_mm / 1000.0

    @property
    def area_mm2(self) -> float:
        return self.length_mm * self.thickness_mm

    @property
    def area_m2(self) -> float:
        return self.area_mm2 / 1e6

    @property
    def aspect_ratio(self) -> float:
        """Hw/lw oranı - perde narinliği"""
        if self.length_mm <= 0:
            return 999.0
        return self.clear_height_mm / self.length_mm

    @property
    def is_slender_wall(self) -> float:
        """TBDY 7.6.2.2 - Hw/lw >= 2.0 ise narin perde"""
        return self.aspect_ratio >= 2.0

    @property
    def effective_depth_mm(self) -> float:
        """Kesme hesabı için faydalı yükseklik (d = 0.8*lw)"""
        return 0.8 * self.length_mm

    @property
    def I_gross_mm4(self) -> float:
        """Brüt kesit atalet momenti (düzlem içi eğilme)"""
        return self.thickness_mm * (self.length_mm ** 3) / 12.0


@dataclass
class WallForces:
    """Perde tasarım kuvvetleri (zarftan)"""
    label: str
    N_kn: float = 0.0  # eksenel kuvvet (basınç +, çekme -)
    M_inplane_knm: float = 0.0  # düzlem içi eğilme momenti
    V_inplane_kn: float = 0.0  # düzlem içi kesme kuvveti
    M_outofplane_knm: float = 0.0  # düzlem dışı eğilme (minor)
    V_outofplane_kn: float = 0.0  # düzlem dışı kesme
    T_knm: float = 0.0  # burulma momenti
    drift_ratio: float = 0.0  # göreli kat ötelemesi
    governing_combo: str = ""

    @property
    def is_tension(self) -> bool:
        return self.N_kn < -0.01

    @property
    def N_abs_kn(self) -> float:
        return abs(self.N_kn)

    @property
    def eccentricity_m(self) -> float:
        """Eksenel yük dışmerkezliği (m)"""
        if abs(self.N_kn) < 0.01:
            return 999.0
        return abs(self.M_inplane_knm) / abs(self.N_kn)


@dataclass
class WallRebar:
    """Perde donatı detayı"""
    label: str

    # Gövde donatısı
    rho_vertical_pct: float = 0.0  # düşey donatı oranı (%)
    rho_horizontal_pct: float = 0.0  # yatay donatı oranı (%)
    As_vertical_mm2: float = 0.0  # toplam düşey donatı
    As_horizontal_mm2: float = 0.0  # toplam yatay donatı
    bar_diameter_vertical_mm: float = 0.0
    bar_diameter_horizontal_mm: float = 0.0
    bar_spacing_vertical_mm: float = 200.0
    bar_spacing_horizontal_mm: float = 200.0

    # Başlık bölgesi donatısı
    has_boundary_data: bool = False
    boundary_length_mm: float = 0.0
    boundary_rebar_dia_mm: float = 0.0
    boundary_n_bars: int = 0
    As_boundary_mm2: float = 0.0
    boundary_stirrup_dia_mm: float = 0.0
    boundary_stirrup_spacing_mm: float = 0.0
    Ash_boundary_mm2: float = 0.0

    # Donatı kaynağı
    source: str = "unknown"  # etabs_design_summary, section_defs, default


@dataclass
class WallCheckResult:
    """Tek bir check sonucu"""
    check_name: str
    status: str  # OK, WARNING, FAIL, NO_DATA, NOT_EVALUATED
    ratio: float = 0.0
    value: float = 0.0
    limit: float = 0.0
    unit: str = ""
    message: str = ""
    tbdy_ref: str = ""
    evaluation_level: str = "NOT_EVALUATED"


@dataclass
class WallDesignOutput:
    """Tek perde için komple tasarım çıktısı"""
    label: str
    story: str
    section: str
    status: str = "NO_DATA"

    materials: Optional[MaterialSet] = None
    geometry: Optional[WallGeometry] = None
    forces: Optional[WallForces] = None
    rebar: Optional[WallRebar] = None

    checks: Dict[str, WallCheckResult] = field(default_factory=dict)

    governing_check: str = ""
    governing_ratio: float = 0.0


# =============================================================================
# GÜVENLİ DÖNÜŞÜM YARDIMCILARI
# =============================================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    """Güvenli float dönüşümü"""
    if value is None:
        return default
    try:
        v = float(value)
        return v if not math.isnan(v) else default
    except (ValueError, TypeError):
        return default


def _row_get_any(row: Any, keys: List[str], default: Any = None) -> Any:
    """Pandas Series / dict satırından alias destekli güvenli okuma"""
    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            value = None
        if value not in (None, "", float("nan")):
            return value
    return default


def _no_data_result(check_name: str, tbdy_ref: str, message: str = "Veri eksik") -> WallCheckResult:
    """Standart NO_DATA sonucu"""
    return WallCheckResult(
        check_name=check_name,
        status="NO_DATA",
        message=message,
        tbdy_ref=tbdy_ref,
        evaluation_level="NOT_EVALUATED",
    )


# =============================================================================
# TBDY 2018 / TS500 PERDE HESAP FONKSİYONLARI
# =============================================================================

def _compute_boundary_zone_required_length(
    lw_mm: float,
    bw_mm: float,
    N_kn: float,
    M_knm: float,
    fcd_mpa: float,
    drift_ratio: float = 0.0,
) -> Tuple[float, float, str]:
    """
    TBDY 2018 Madde 7.6.4 - Başlık bölgesi gereksinimi

    İki kriter:
    1. Gerilme kriteri: max basınç gerilmesi > 0.30*fcd → başlık gerekli
       Başlık uzunluğu: basınç gerilmesi >= 0.15*fcd olan bölge
    2. Deformasyon kriteri: drift oranı >= 0.005 ise başlık gerekli

    Returns:
        required_boundary_length_mm: Gerekli başlık uzunluğu (mm)
        max_stress_mpa: Maksimum basınç gerilmesi (MPa)
        reason: Başlık gereksinim sebebi
    """
    Ag_mm2 = lw_mm * bw_mm
    I_mm4 = bw_mm * (lw_mm ** 3) / 12.0

    if Ag_mm2 <= 0 or I_mm4 <= 0:
        return 0.0, 0.0, "Geometri yetersiz"

    # Kesit modülü
    S_mm3 = I_mm4 / (lw_mm / 2.0)

    # Eksenel + eğilme gerilmesi (en dış lif)
    N_N = N_kn * 1000.0  # kN -> N
    M_Nmm = abs(M_knm) * 1e6  # kNm -> Nmm

    sigma_axial = N_N / Ag_mm2  # MPa (basınç +)
    sigma_flexure = M_Nmm / S_mm3  # MPa

    # Maksimum basınç gerilmesi
    sigma_max_compression = sigma_axial + sigma_flexure

    # Minimum gerilme (çekme tarafı)
    sigma_min = sigma_axial - sigma_flexure

    # Başlık gereksinim kontrolü
    need_boundary_stress = sigma_max_compression > (0.30 * fcd_mpa) if fcd_mpa > 0 else False
    need_boundary_drift = drift_ratio >= 0.005

    if not need_boundary_stress and not need_boundary_drift:
        return 0.0, sigma_max_compression, "Başlık bölgesi gerekli değil"

    # Başlık uzunluğu hesabı: σ >= 0.15*fcd olan bölge
    if need_boundary_stress and sigma_max_compression > 0:
        sigma_target = 0.15 * fcd_mpa
        # Gerilme dağılımı lineer: σ(y) = N/Ag + M*y/I
        # σ(y) = sigma_target → y = (sigma_target - N/Ag) * I/M
        y_target_mm = (sigma_target - sigma_axial) * I_mm4 / M_Nmm if M_Nmm > 0 else 0.0
        boundary_length_stress = max(0.0, lw_mm / 2.0 - y_target_mm)
    else:
        boundary_length_stress = 0.0

    # Deformasyon kriteri: drift >= 0.005 → başlık uzunluğu en az 0.1*lw
    boundary_length_drift = 0.1 * lw_mm if need_boundary_drift else 0.0

    required_length = max(boundary_length_stress, boundary_length_drift)

    # Minimum başlık uzunluğu: TBDY 7.6.4.3 - max(lw/10, bw)
    required_length = max(required_length, lw_mm / 10.0, bw_mm)

    reason_parts = []
    if need_boundary_stress:
        reason_parts.append(f"gerilme (σ_max={sigma_max_compression:.1f}MPa > 0.30*fcd={0.30*fcd_mpa:.1f}MPa)")
    if need_boundary_drift:
        reason_parts.append(f"deformasyon (drift={drift_ratio:.4f} >= 0.005)")

    return required_length, sigma_max_compression, "; ".join(reason_parts)


def _compute_wall_axial_moment_capacity(
    lw_mm: float,
    bw_mm: float,
    fcd_mpa: float,
    fyd_mpa: float,
    As_vertical_mm2: float,
    N_kn: float,
) -> Tuple[float, float]:
    """
    TBDY 2018 7.6.2 - Perde PMM etkileşimi (basitleştirilmiş yaklaşık yöntem)

    Dikdörtgen perde için eşdeğer basınç bloğu yöntemi.
    Eksenel yük + donatı ile moment kapasitesi tahmini.

    Returns:
        Mr_knm: Moment kapasitesi (kN·m)
        utilization_ratio: Kullanım oranı (Md/Mr)
    """
    if lw_mm <= 0 or bw_mm <= 0:
        return 0.0, 999.0

    d_mm = 0.8 * lw_mm  # faydalı yükseklik (yaklaşık)

    # Donatı alanı oranı
    rho = As_vertical_mm2 / (lw_mm * bw_mm) if (lw_mm * bw_mm) > 0 else 0.0

    # Basitleştirilmiş etkileşim: Mr ≈ As*fyd*(0.8*lw) + N*(lw/2 - a/2)
    # (Bu formül tasarım amaçlı yaklaşık bir ifadedir, tam PMM değildir)

    # Basınç bloğu derinliği
    a_mm = (As_vertical_mm2 * fyd_mpa + N_kn * 1000.0) / (0.85 * fcd_mpa * bw_mm) if fcd_mpa > 0 and bw_mm > 0 else 0.0
    a_mm = min(a_mm, lw_mm)  # fiziksel sınır

    # Moment kolu
    z_mm = d_mm - a_mm / 2.0

    # Moment kapasitesi
    Mr_Nmm = As_vertical_mm2 * fyd_mpa * z_mm + N_kn * 1000.0 * (lw_mm / 2.0 - a_mm / 2.0)
    Mr_knm = Mr_Nmm / 1e6

    return max(0.0, Mr_knm), a_mm


def _compute_wall_shear_strength(
    lw_mm: float,
    bw_mm: float,
    fck_mpa: float,
    fcd_mpa: float,
    fywd_mpa: float,
    N_kn: float,
    As_horizontal_mm2: float,
    s_horizontal_mm: float = 200.0,
    is_slender: bool = True,
) -> Tuple[float, float, float]:
    """
    TBDY 2018 Madde 7.6.6 + TS500 - Perde kesme dayanımı

    Vr = Vc + Vw (TS500 modeli)
    Vc = 0.65 * fctd * bw * d * (1 + γ*N/Ag) (eksenel etkili)
    Vw = (As_h/s) * fywd * d

    TBDY 7.6.6.3: Ve <= 0.22*fcd*Ac (maksimum kesme)
    TBDY 7.6.6.4: Ve <= 0.65*fck^0.5*Ac (alternatif üst sınır)

    Returns:
        Vr_kn: Kesme dayanımı (kN)
        Vc_kn: Beton katkısı (kN)
        Vw_kn: Donatı katkısı (kN)
        Vr_max_kn: Maksimum kesme dayanımı (kN)
    """
    fctd = 0.35 * math.sqrt(abs(fck_mpa))

    d_mm = 0.8 * lw_mm
    Ag_mm2 = lw_mm * bw_mm
    Ac_mm2 = Ag_mm2  # perde kesit alanı

    # Beton katkısı (TS500)
    if N_kn >= 0:  # basınç
        N_Ag_mpa = N_kn * 1000.0 / Ag_mm2 if Ag_mm2 > 0 else 0.0
        factor = 1.0 + 0.07 * min(abs(N_Ag_mpa), 0.2 * fcd_mpa)  # sınırlı artış
    else:  # çekme - beton katkısı azalır
        factor = max(0.0, 1.0 - 0.30 * abs(N_kn * 1000.0 / Ag_mm2) if Ag_mm2 > 0 else 1.0)

    Vc_N = 0.65 * fctd * bw_mm * d_mm * factor
    Vc_kn = Vc_N / 1000.0

    # Donatı katkısı
    if s_horizontal_mm > 0 and As_horizontal_mm2 > 0:
        # As_h/s birim boy başına donatı
        Asw_per_mm = As_horizontal_mm2 / s_horizontal_mm  # yaklaşık
        Vw_N = Asw_per_mm * fywd_mpa * d_mm
        Vw_kn = Vw_N / 1000.0
    else:
        Vw_kn = 0.0

    Vr_kn = Vc_kn + Vw_kn

    # Maksimum kesme dayanımı (TBDY 7.6.6.3)
    Vr_max_1 = 0.22 * fcd_mpa * Ac_mm2 / 1000.0  # kN
    Vr_max_2 = 0.65 * math.sqrt(abs(fck_mpa)) * Ac_mm2 / 1000.0  # kN (alternatif)

    Vr_max_kn = min(Vr_max_1, Vr_max_2)

    return Vr_kn, Vc_kn, Vw_kn, Vr_max_kn


def _compute_wall_min_reinforcement(
    lw_mm: float,
    bw_mm: float,
    fctd_mpa: float,
    fyd_mpa: float,
) -> Tuple[float, float, float, float]:
    """
    TBDY 2018 Madde 7.6.3 - Perde gövde donatısı minimum oranları

    Düşey donatı: ρv >= 0.0025 (yüksek süneklik)
    Yatay donatı: ρh >= 0.0020 (yüksek süneklik)
    (TS500: ρ_min = 0.0015 her iki yönde)

    Returns:
        As_vertical_min_mm2: Minimum düşey donatı (mm2)
        As_horizontal_min_mm2: Minimum yatay donatı (mm2)
        rho_v_min: Minimum düşey donatı oranı
        rho_h_min: Minimum yatay donatı oranı
    """
    Ag_mm2 = lw_mm * bw_mm

    # TBDY 2018 minimum oranları (yüksek süneklik)
    rho_v_min = 0.0025
    rho_h_min = 0.0020

    # TS500 minimumları ile karşılaştır
    rho_ts500 = max(0.8 * fctd_mpa / fyd_mpa, 0.0015) if fyd_mpa > 0 else 0.0015

    rho_v_min = max(rho_v_min, rho_ts500)
    rho_h_min = max(rho_h_min, rho_ts500)

    As_v_min = rho_v_min * Ag_mm2
    As_h_min = rho_h_min * Ag_mm2

    return As_v_min, As_h_min, rho_v_min, rho_h_min


def _compute_wall_overturning(
    M_overturning_knm: float,
    N_stabilizing_kn: float,
    lw_m: float,
) -> Tuple[float, float]:
    """
    TBDY 2018 - Perde devrilme kontrolü (screening)

    Devrilme momenti: Mo
    Karşı koyma momenti: Mr = N * lw/2

    Returns:
        safety_factor: Mr/Mo (güvenlik katsayısı)
        Mr_knm: Karşı koyma momenti (kN·m)
    """
    Mr_knm = abs(N_stabilizing_kn) * lw_m / 2.0

    if abs(M_overturning_knm) < 0.01:
        return 999.0, Mr_knm

    safety_factor = Mr_knm / abs(M_overturning_knm)
    return safety_factor, Mr_knm


# =============================================================================
# WALL DESIGN MODULE
# =============================================================================

class WallDesignModule:
    """
    Perde Tasarım Modülü.

    ModelContext'ten okur, TBDY 2018 + TS500 kontrollerini yapar,
    her perde için WallDesignOutput üretir.
    """

    def __init__(self, ctx: Any):
        """
        Args:
            ctx: app.engine.context_builder.ModelContext
        """
        self.ctx = ctx
        self._materials: Optional[MaterialSet] = None
        self._walls: List[WallGeometry] = []
        self._forces: Dict[str, WallForces] = {}
        self._rebar: Dict[str, WallRebar] = {}
        self._outputs: List[WallDesignOutput] = []

    # -------------------------------------------------------------------------
    # RESOLVE
    # -------------------------------------------------------------------------

    def resolve_materials(self) -> MaterialSet:
        """Design basis'ten malzeme setini çöz"""
        db = self.ctx.design_basis

        fck = _safe_float(db.get("fck_mpa"), 30.0)
        fyk = _safe_float(db.get("fyk_mpa"), 420.0)
        gamma_c = _safe_float(db.get("gamma_c"), 1.5)
        gamma_s = _safe_float(db.get("gamma_s"), 1.15)

        self._materials = MaterialSet(
            fck=fck,
            fcd=fck / gamma_c,
            fyk=fyk,
            fyd=fyk / gamma_s,
            fywd=_safe_float(db.get("fywd_mpa"), fyk / gamma_s),
            gamma_c=gamma_c,
            gamma_s=gamma_s,
        )
        return self._materials

    def resolve_walls(self) -> List[WallGeometry]:
        """Topology ve geometry'den perde geometrilerini çöz"""
        walls = []

        topo_walls = self.ctx.topology.get("walls", [])
        section_dims = self.ctx.geometry.get("section_dims", {})
        wall_sections = self.ctx.geometry.get("wall_sections", {})
        story_heights = self.ctx.geometry.get("story_heights", {})

        for wall_data in topo_walls:
            label = str(wall_data.get("label", ""))
            story = str(wall_data.get("story", ""))

            if not label:
                continue

            # Kesit adı
            section_name = wall_sections.get(label, "")
            if not section_name:
                section_name = str(wall_data.get("section", ""))

            # Kesit boyutları
            dims = section_dims.get(section_name, {})
            length_mm = _safe_float(
                dims.get("length_mm") or dims.get("lw_mm") or (dims.get("length_m", 0.0) * 1000),
                2000.0,
            )
            thickness_mm = _safe_float(
                dims.get("thickness_mm") or dims.get("bw_mm") or (dims.get("thickness_m", 0.0) * 1000),
                250.0,
            )

            # Minimum değerler
            if length_mm < 500:
                length_mm = 2000.0
            if thickness_mm < 150:
                thickness_mm = 250.0

            # Net yükseklik
            clear_height_mm = _safe_float(
                story_heights.get(story, 0.0) * 1000,
                3000.0,
            )

            # Başlık bölgesi bilgisi
            boundary_length = _safe_float(dims.get("boundary_length_mm"), 0.0)
            boundary_thickness = _safe_float(dims.get("boundary_thickness_mm"), thickness_mm)

            # Boşluklu perde kontrolü
            is_coupled = str(wall_data.get("is_coupled", "")).lower() in ("true", "yes", "1")
            coupling_beam = str(wall_data.get("coupling_beam", ""))

            wall_geom = WallGeometry(
                label=label,
                story=story,
                section_name=section_name,
                length_mm=length_mm,
                thickness_mm=thickness_mm,
                clear_height_mm=clear_height_mm,
                boundary_length_mm=boundary_length,
                boundary_thickness_mm=boundary_thickness,
                is_coupled=is_coupled,
                coupling_beam_label=coupling_beam,
            )
            walls.append(wall_geom)

        self._walls = walls
        return walls

    def resolve_forces(self) -> Dict[str, WallForces]:
        """Envelope'tan perde kuvvetlerini çöz"""
        forces_map = self.ctx.envelopes.get("wall_forces_map", {})

        for label, env_data in forces_map.items():
            wf = WallForces(
                label=label,
                N_kn=_safe_float(env_data.get("P") or env_data.get("N")),
                M_inplane_knm=_safe_float(env_data.get("M3") or env_data.get("M_inplane")),
                V_inplane_kn=_safe_float(env_data.get("V2") or env_data.get("V_inplane")),
                M_outofplane_knm=_safe_float(env_data.get("M2") or env_data.get("M_outofplane")),
                V_outofplane_kn=_safe_float(env_data.get("V3") or env_data.get("V_outofplane")),
                T_knm=_safe_float(env_data.get("T")),
                drift_ratio=_safe_float(env_data.get("drift") or env_data.get("drift_ratio")),
                governing_combo=str(env_data.get("combo") or env_data.get("case", "")),
            )
            self._forces[label] = wf

        return self._forces

    def resolve_rebar(self) -> Dict[str, WallRebar]:
        """
        Perde donatı verilerini çöz.

        Öncelik:
        1. ETABS wall_design_summary
        2. Section-level wall_rebar_defs
        3. Auto proposal (minimum donatı)
        """
        self._rebar = {}

        if not self._walls:
            self.resolve_walls()

        # ETABS design summary
        design_summary = self.ctx.design_metadata.get("wall_design_summary")
        if design_summary is None:
            design_summary = self.ctx.tables.get("wall_design_summary")

        if design_summary is not None and not getattr(design_summary, "empty", True):
            self._resolve_rebar_from_etabs(design_summary)

        # Section-level definitions
        section_defs = self.ctx.design_metadata.get("wall_rebar_defs")
        if section_defs is None:
            section_defs = self.ctx.tables.get("wall_rebar_defs")

        if section_defs is not None and not getattr(section_defs, "empty", True):
            self._resolve_rebar_from_sections(section_defs)

        # Auto proposal for missing walls
        for wall in self._walls:
            if wall.label not in self._rebar:
                self._rebar[wall.label] = self._propose_minimum_rebar(wall)

        return self._rebar

    def _resolve_rebar_from_etabs(self, design_summary: Any) -> None:
        """ETABS design summary'den perde donatısı çöz"""
        for wall in self._walls:
            try:
                rows = design_summary[
                    design_summary.apply(
                        lambda r: str(r.get("label", r.get("Label", r.get("Pier", "")))).strip() == wall.label,
                        axis=1,
                    )
                ]
            except Exception:
                continue

            if rows is None or rows.empty:
                continue

            row = rows.iloc[0]

            # Gövde donatısı
            rho_v = _safe_float(row.get("rho_vertical") or row.get("rho_v"), 0.0025)
            rho_h = _safe_float(row.get("rho_horizontal") or row.get("rho_h"), 0.0020)

            if 0 < rho_v < 0.001:
                rho_v *= 100.0  # oran -> yüzde dönüşümü
            if 0 < rho_h < 0.001:
                rho_h *= 100.0

            As_v = rho_v * wall.area_mm2 / 100.0 if rho_v < 1.0 else rho_v * wall.area_mm2
            As_h = rho_h * wall.area_mm2 / 100.0 if rho_h < 1.0 else rho_h * wall.area_mm2

            # Başlık bölgesi
            boundary_len = _safe_float(row.get("boundary_length") or row.get("boundary_zone_length"), 0.0)
            if 0 < boundary_len < wall.length_mm / 100.0:
                boundary_len *= 1000.0  # m -> mm

            wr = WallRebar(
                label=wall.label,
                rho_vertical_pct=rho_v if rho_v < 1.0 else rho_v * 100.0,
                rho_horizontal_pct=rho_h if rho_h < 1.0 else rho_h * 100.0,
                As_vertical_mm2=As_v,
                As_horizontal_mm2=As_h,
                bar_diameter_vertical_mm=_safe_float(row.get("bar_dia_v"), 14.0),
                bar_diameter_horizontal_mm=_safe_float(row.get("bar_dia_h"), 12.0),
                bar_spacing_vertical_mm=_safe_float(row.get("spacing_v"), 200.0),
                bar_spacing_horizontal_mm=_safe_float(row.get("spacing_h"), 200.0),
                has_boundary_data=(boundary_len > 0),
                boundary_length_mm=boundary_len,
                boundary_rebar_dia_mm=_safe_float(row.get("boundary_bar_dia"), 0.0),
                boundary_n_bars=int(_safe_float(row.get("boundary_n_bars"), 0)),
                As_boundary_mm2=_safe_float(row.get("As_boundary"), 0.0),
                boundary_stirrup_dia_mm=_safe_float(row.get("boundary_stirrup_dia"), 0.0),
                boundary_stirrup_spacing_mm=_safe_float(row.get("boundary_stirrup_spacing"), 0.0),
                source="etabs_design_summary",
            )
            self._rebar[wall.label] = wr

    def _resolve_rebar_from_sections(self, section_defs: Any) -> None:
        """Section-level rebar defs'ten donatı çöz"""
        for wall in self._walls:
            if wall.label in self._rebar:
                continue

            sec_data = None
            try:
                sec_rows = section_defs[
                    section_defs.apply(
                        lambda r: str(r.get("section", r.get("name", ""))).strip() == wall.section_name,
                        axis=1,
                    )
                ]
                if not sec_rows.empty:
                    sec_data = sec_rows.iloc[0]
            except Exception:
                continue

            if sec_data is None:
                continue

            rho_v = _safe_float(sec_data.get("rho_vertical") or sec_data.get("rho_v"), 0.0025)
            rho_h = _safe_float(sec_data.get("rho_horizontal") or sec_data.get("rho_h"), 0.0020)

            if 0 < rho_v < 0.001:
                rho_v *= 100.0
            if 0 < rho_h < 0.001:
                rho_h *= 100.0

            As_v = rho_v * wall.area_mm2 / 100.0 if rho_v < 1.0 else rho_v * wall.area_mm2
            As_h = rho_h * wall.area_mm2 / 100.0 if rho_h < 1.0 else rho_h * wall.area_mm2

            wr = WallRebar(
                label=wall.label,
                rho_vertical_pct=rho_v if rho_v < 1.0 else rho_v * 100.0,
                rho_horizontal_pct=rho_h if rho_h < 1.0 else rho_h * 100.0,
                As_vertical_mm2=As_v,
                As_horizontal_mm2=As_h,
                source="section_rebar_defs",
            )
            self._rebar[wall.label] = wr

    def _propose_minimum_rebar(self, wall: WallGeometry) -> WallRebar:
        """Minimum perde donatısı önerisi"""
        if self._materials is None:
            self.resolve_materials()
        mat = self._materials

        As_v_min, As_h_min, rho_v_min, rho_h_min = _compute_wall_min_reinforcement(
            lw_mm=wall.length_mm,
            bw_mm=wall.thickness_mm,
            fctd_mpa=mat.fctd,
            fyd_mpa=mat.fyd,
        )

        wr = WallRebar(
            label=wall.label,
            rho_vertical_pct=rho_v_min * 100.0,
            rho_horizontal_pct=rho_h_min * 100.0,
            As_vertical_mm2=As_v_min,
            As_horizontal_mm2=As_h_min,
            bar_diameter_vertical_mm=14.0,
            bar_diameter_horizontal_mm=12.0,
            bar_spacing_vertical_mm=200.0,
            bar_spacing_horizontal_mm=200.0,
            source="default",
        )
        return wr

    # -------------------------------------------------------------------------
    # CHECKS
    # -------------------------------------------------------------------------

    def check_geometry(self, wall: WallGeometry) -> WallCheckResult:
        """
        TBDY 2018 Madde 7.6.1 - Perde minimum boyut kontrolü

        - Gövde kalınlığı >= 250 mm (yüksek süneklik)
        - Gövde kalınlığı >= kat yüksekliği / 16
        - Perde boyu >= 2.0 m (öneri)
        - Başlık bölgesi varsa kalınlık >= 300 mm
        """
        issues = []
        warnings = []

        # Minimum kalınlık
        if wall.thickness_mm < 250:
            issues.append(f"gövde kalınlığı {wall.thickness_mm:.0f}mm < 250mm")

        # Kalınlık / kat yüksekliği
        min_t_by_height = wall.clear_height_mm / 16.0
        if wall.thickness_mm < min_t_by_height:
            warnings.append(
                f"kalınlık {wall.thickness_mm:.0f}mm < Hw/16={min_t_by_height:.0f}mm"
            )

        # Minimum perde boyu
        if wall.length_mm < 1500:
            warnings.append(f"perde boyu {wall.length_mm:.0f}mm < 1500mm (önerilen min 2.0m)")

        # Başlık bölgesi kalınlığı
        if wall.boundary_length_mm > 0 and wall.boundary_thickness_mm < 300:
            warnings.append(f"başlık bölgesi kalınlığı {wall.boundary_thickness_mm:.0f}mm < 300mm")

        if wall.is_coupled:
            warnings.append("boşluklu perde - bağ kirişi kontrolleri ayrıca yapılmalı")

        if issues:
            return WallCheckResult(
                check_name="geometry",
                status="FAIL",
                ratio=0.0,
                value=wall.thickness_mm,
                limit=250.0,
                unit="mm",
                message="; ".join(issues + warnings),
                tbdy_ref="TBDY 2018 7.6.1",
                evaluation_level="DESIGN_LEVEL",
            )

        if warnings:
            return WallCheckResult(
                check_name="geometry",
                status="WARNING",
                ratio=1.0,
                value=wall.thickness_mm,
                limit=250.0,
                unit="mm",
                message="; ".join(warnings),
                tbdy_ref="TBDY 2018 7.6.1",
                evaluation_level="DESIGN_LEVEL",
            )

        return WallCheckResult(
            check_name="geometry",
            status="OK",
            ratio=1.0,
            value=wall.thickness_mm,
            limit=250.0,
            unit="mm",
            message=f"Geometri uygun (bw={wall.thickness_mm:.0f}mm, lw={wall.length_mm:.0f}mm, Hw={wall.clear_height_mm:.0f}mm)",
            tbdy_ref="TBDY 2018 7.6.1",
            evaluation_level="DESIGN_LEVEL",
        )

    def check_axial_flexure(
        self,
        wall: WallGeometry,
        forces: Optional[WallForces] = None,
        rebar: Optional[WallRebar] = None,
        mat: Optional[MaterialSet] = None,
    ) -> WallCheckResult:
        """
        TBDY 2018 Madde 7.6.2 - Perde eksenel + eğilme (PMM) kontrolü

        Eksenel yük + moment etkileşimi.
        Screening/Approximate seviyede basitleştirilmiş yöntem.
        Tam PMM için Section Designer entegrasyonu gerekir.
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if forces is None:
            forces = self._forces.get(wall.label)

        if rebar is None:
            rebar = self._rebar.get(wall.label)

        if not mat:
            return _no_data_result("axial_flexure", "TBDY 2018 7.6.2", "Malzeme verisi yok")

        if not forces:
            return _no_data_result("axial_flexure", "TBDY 2018 7.6.2", "Kuvvet verisi yok")

        if not rebar or rebar.As_vertical_mm2 <= 0:
            return _no_data_result("axial_flexure", "TBDY 2018 7.6.2", "Düşey donatı verisi yok")

        source = rebar.source
        evaluation_level = "DESIGN_LEVEL" if source != "default" else "APPROXIMATE"

        # Eksenel kapasite kontrolü
        Ag_m2 = wall.area_m2
        Ac_mm2 = wall.area_mm2
        N_limit_kn = 0.35 * Ac_mm2 * mat.fcd / 1000.0  # TBDY 7.6.2.1: Nd <= 0.35*Ac*fcd
        axial_ratio = abs(forces.N_kn) / N_limit_kn if N_limit_kn > 0 else 999.0

        # Moment kapasitesi (basitleştirilmiş)
        Mr_knm, a_mm = _compute_wall_axial_moment_capacity(
            lw_mm=wall.length_mm,
            bw_mm=wall.thickness_mm,
            fcd_mpa=mat.fcd,
            fyd_mpa=mat.fyd,
            As_vertical_mm2=rebar.As_vertical_mm2,
            N_kn=forces.N_kn,
        )

        moment_ratio = abs(forces.M_inplane_knm) / Mr_knm if Mr_knm > 0 else 999.0

        # Narin perde kontrolü (TBDY 7.6.2.2)
        if wall.is_slender_wall:
            # İkinci mertebe etkiler - yaklaşık büyütme
            beta = 1.0 / (1.0 - abs(forces.N_kn) / (0.75 * N_limit_kn)) if N_limit_kn > 0 else 1.0
            moment_ratio *= min(beta, 2.0)  # maksimum 2 kat büyütme

        # Yöneten oran
        governing_ratio = max(axial_ratio, moment_ratio)

        if forces.is_tension:
            # Çekme durumu özel mesaj
            return WallCheckResult(
                check_name="axial_flexure",
                status="WARNING",
                ratio=governing_ratio,
                value=forces.N_kn,
                limit=N_limit_kn,
                unit="kN",
                message=(
                    f"Perdede çekme kuvveti var: N={forces.N_kn:.0f}kN. "
                    f"Eksenel oran={axial_ratio:.3f}, Moment oranı={moment_ratio:.3f}. "
                    f"Çekme donatısı kontrolü DESIGN_LEVEL gerektirir."
                ),
                tbdy_ref="TBDY 2018 7.6.2",
                evaluation_level="SCREENING",
            )

        if governing_ratio > 1.0:
            status = "FAIL"
        elif source == "default":
            status = "WARNING"
        else:
            status = "OK"

        return WallCheckResult(
            check_name="axial_flexure",
            status=status,
            ratio=governing_ratio,
            value=max(abs(forces.N_kn), abs(forces.M_inplane_knm)),
            limit=min(N_limit_kn, Mr_knm) if Mr_knm > 0 else N_limit_kn,
            unit="kN / kN·m",
            message=(
                f"PMM: axial_ratio={axial_ratio:.3f} (Nd={abs(forces.N_kn):.0f}/{N_limit_kn:.0f}kN), "
                f"moment_ratio={moment_ratio:.3f} (Md={abs(forces.M_inplane_knm):.0f}/{Mr_knm:.0f}kNm). "
                f"Narin perde: {'evet' if wall.is_slender_wall else 'hayır'}"
            ),
            tbdy_ref="TBDY 2018 7.6.2",
            evaluation_level=evaluation_level,
        )

    def check_shear(
        self,
        wall: WallGeometry,
        forces: Optional[WallForces] = None,
        rebar: Optional[WallRebar] = None,
        mat: Optional[MaterialSet] = None,
    ) -> WallCheckResult:
        """
        TBDY 2018 Madde 7.6.6 + TS500 - Perde kesme güvenliği

        Ve <= Vr = Vc + Vw
        Vr <= Vr_max
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if forces is None:
            forces = self._forces.get(wall.label)

        if rebar is None:
            rebar = self._rebar.get(wall.label)

        if not mat:
            return _no_data_result("shear", "TBDY 2018 7.6.6", "Malzeme verisi yok")

        if not forces:
            return _no_data_result("shear", "TBDY 2018 7.6.6", "Kuvvet verisi yok")

        Ve = abs(forces.V_inplane_kn)
        if Ve <= 0.01:
            return WallCheckResult(
                check_name="shear",
                status="OK",
                ratio=0.0,
                value=0.0,
                limit=0.0,
                unit="kN",
                message="Kesme kuvveti ihmal edilebilir düzeyde",
                tbdy_ref="TBDY 2018 7.6.6",
                evaluation_level="DESIGN_LEVEL",
            )

        # Kesme dayanımı hesabı
        As_h = rebar.As_horizontal_mm2 if rebar else 0.0
        s_h = rebar.bar_spacing_horizontal_mm if rebar else 200.0

        Vr_kn, Vc_kn, Vw_kn, Vr_max_kn = _compute_wall_shear_strength(
            lw_mm=wall.length_mm,
            bw_mm=wall.thickness_mm,
            fck_mpa=mat.fck,
            fcd_mpa=mat.fcd,
            fywd_mpa=mat.fywd,
            N_kn=forces.N_kn,
            As_horizontal_mm2=As_h,
            s_horizontal_mm=s_h,
            is_slender=wall.is_slender_wall,
        )

        # Tasarım kesme kuvveti (TBDY 7.6.6.1 - kapasite tasarımı büyütmesi)
        # Basitleştirilmiş: Ve_design = Ve * 1.4 (kapasite tasarımı yaklaşık büyütme)
        Ve_design = Ve * 1.4

        ratio = Ve_design / Vr_max_kn if Vr_max_kn > 0 else 999.0

        source = rebar.source if rebar else "unknown"
        evaluation_level = "DESIGN_LEVEL" if source != "default" else "SCREENING"

        if ratio > 1.0:
            return WallCheckResult(
                check_name="shear",
                status="FAIL",
                ratio=ratio,
                value=Ve_design,
                limit=Vr_max_kn,
                unit="kN",
                message=(
                    f"Kesme FAIL: Ve_design={Ve_design:.0f}kN > Vr={Vr_max_kn:.0f}kN "
                    f"(Vc={Vc_kn:.0f}, Vw={Vw_kn:.0f}, max={Vr_max_kn:.0f}kN). "
                    f"ratio={ratio:.3f}"
                ),
                tbdy_ref="TBDY 2018 7.6.6",
                evaluation_level=evaluation_level,
            )

        status = "WARNING" if source == "default" else "OK"

        return WallCheckResult(
            check_name="shear",
            status=status,
            ratio=ratio,
            value=Ve_design,
            limit=Vr_max_kn,
            unit="kN",
            message=(
                f"Kesme OK: Ve_design={Ve_design:.0f}kN <= Vr={Vr_max_kn:.0f}kN "
                f"(Vc={Vc_kn:.0f}, Vw={Vw_kn:.0f}). ratio={ratio:.3f}"
            ),
            tbdy_ref="TBDY 2018 7.6.6",
            evaluation_level=evaluation_level,
        )

    def check_boundary_zone(
        self,
        wall: WallGeometry,
        forces: Optional[WallForces] = None,
        rebar: Optional[WallRebar] = None,
        mat: Optional[MaterialSet] = None,
    ) -> WallCheckResult:
        """
        TBDY 2018 Madde 7.6.4 - Perde başlık bölgesi kontrolü

        Gerilme ve deformasyon kriterlerine göre başlık bölgesi gereksinimi.
        Varsa başlık donatısı yeterliliği.
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if forces is None:
            forces = self._forces.get(wall.label)

        if rebar is None:
            rebar = self._rebar.get(wall.label)

        if not mat:
            return _no_data_result("boundary_zone", "TBDY 2018 7.6.4", "Malzeme verisi yok")

        if not forces:
            return _no_data_result("boundary_zone", "TBDY 2018 7.6.4", "Kuvvet verisi yok")

        # Başlık gereksinimi hesabı
        required_length, sigma_max, reason = _compute_boundary_zone_required_length(
            lw_mm=wall.length_mm,
            bw_mm=wall.thickness_mm,
            N_kn=forces.N_kn,
            M_knm=forces.M_inplane_knm,
            fcd_mpa=mat.fcd,
            drift_ratio=forces.drift_ratio,
        )

        existing_length = wall.boundary_length_mm
        if rebar and rebar.has_boundary_data:
            existing_length = max(existing_length, rebar.boundary_length_mm)

        if required_length <= 0:
            return WallCheckResult(
                check_name="boundary_zone",
                status="OK",
                ratio=0.0,
                value=sigma_max,
                limit=0.30 * mat.fcd,
                unit="MPa",
                message=f"Başlık bölgesi gerekli değil (σ_max={sigma_max:.1f}MPa <= 0.30*fcd={0.30*mat.fcd:.1f}MPa)",
                tbdy_ref="TBDY 2018 7.6.4",
                evaluation_level="DESIGN_LEVEL",
            )

        length_ratio = existing_length / required_length if required_length > 0 else 0.0

        source = rebar.source if rebar else "unknown"
        evaluation_level = "DESIGN_LEVEL" if source != "default" else "SCREENING"

        if length_ratio < 1.0:
            return WallCheckResult(
                check_name="boundary_zone",
                status="FAIL",
                ratio=length_ratio,
                value=existing_length,
                limit=required_length,
                unit="mm",
                message=(
                    f"Başlık bölgesi yetersiz: mevcut={existing_length:.0f}mm, "
                    f"gerekli={required_length:.0f}mm. "
                    f"Gereksinim: {reason}. "
                    f"σ_max={sigma_max:.1f}MPa, drift={forces.drift_ratio:.4f}"
                ),
                tbdy_ref="TBDY 2018 7.6.4",
                evaluation_level=evaluation_level,
            )

        status = "WARNING" if source == "default" else "OK"

        return WallCheckResult(
            check_name="boundary_zone",
            status=status,
            ratio=length_ratio,
            value=existing_length,
            limit=required_length,
            unit="mm",
            message=(
                f"Başlık bölgesi uygun: mevcut={existing_length:.0f}mm >= "
                f"gerekli={required_length:.0f}mm. Gereksinim: {reason}"
            ),
            tbdy_ref="TBDY 2018 7.6.4",
            evaluation_level=evaluation_level,
        )

    def check_shear_wall_reinforcement(
        self,
        wall: WallGeometry,
        rebar: Optional[WallRebar] = None,
        mat: Optional[MaterialSet] = None,
    ) -> WallCheckResult:
        """
        TBDY 2018 Madde 7.6.3 - Perde gövde donatısı minimum kontrolü

        Düşey donatı: ρv >= 0.0025
        Yatay donatı: ρh >= 0.0020
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if rebar is None:
            rebar = self._rebar.get(wall.label)

        if not mat:
            return _no_data_result("shear_wall_reinf", "TBDY 2018 7.6.3", "Malzeme verisi yok")

        if not rebar:
            return _no_data_result("shear_wall_reinf", "TBDY 2018 7.6.3", "Donatı verisi yok")

        As_v_min, As_h_min, rho_v_min, rho_h_min = _compute_wall_min_reinforcement(
            lw_mm=wall.length_mm,
            bw_mm=wall.thickness_mm,
            fctd_mpa=mat.fctd,
            fyd_mpa=mat.fyd,
        )

        issues = []
        rho_v_actual = rebar.rho_vertical_pct / 100.0 if rebar.rho_vertical_pct > 1.0 else rebar.rho_vertical_pct
        rho_h_actual = rebar.rho_horizontal_pct / 100.0 if rebar.rho_horizontal_pct > 1.0 else rebar.rho_horizontal_pct

        if rho_v_actual < rho_v_min:
            issues.append(f"ρv={rho_v_actual*100:.3f}% < {rho_v_min*100:.3f}%")
        if rho_h_actual < rho_h_min:
            issues.append(f"ρh={rho_h_actual*100:.3f}% < {rho_h_min*100:.3f}%")

        source = rebar.source
        evaluation_level = "DESIGN_LEVEL" if source != "default" else "SCREENING"

        if issues:
            return WallCheckResult(
                check_name="shear_wall_reinf",
                status="FAIL",
                ratio=min(rho_v_actual / rho_v_min if rho_v_min > 0 else 1.0,
                          rho_h_actual / rho_h_min if rho_h_min > 0 else 1.0),
                value=min(rho_v_actual, rho_h_actual) * 100.0,
                limit=max(rho_v_min, rho_h_min) * 100.0,
                unit="%",
                message=f"Minimum gövde donatısı sağlanmıyor: {'; '.join(issues)}",
                tbdy_ref="TBDY 2018 7.6.3",
                evaluation_level=evaluation_level,
            )

        status = "WARNING" if source == "default" else "OK"

        return WallCheckResult(
            check_name="shear_wall_reinf",
            status=status,
            ratio=1.0,
            value=max(rho_v_actual, rho_h_actual) * 100.0,
            limit=max(rho_v_min, rho_h_min) * 100.0,
            unit="%",
            message=f"Gövde donatısı uygun: ρv={rho_v_actual*100:.3f}%, ρh={rho_h_actual*100:.3f}%",
            tbdy_ref="TBDY 2018 7.6.3",
            evaluation_level=evaluation_level,
        )

    def check_overturning(
        self,
        wall: WallGeometry,
        forces: Optional[WallForces] = None,
    ) -> WallCheckResult:
        """
        TBDY 2018 - Perde devrilme kontrolü (screening)

        Karşı koyma momenti / Devirme momenti >= 1.5
        """
        if forces is None:
            forces = self._forces.get(wall.label)

        if not forces:
            return _no_data_result("overturning", "TBDY 2018", "Kuvvet verisi yok")

        if abs(forces.M_inplane_knm) < 0.01:
            return WallCheckResult(
                check_name="overturning",
                status="OK",
                ratio=0.0,
                value=0.0,
                limit=0.0,
                unit="kN·m",
                message="Devrilme momenti ihmal edilebilir",
                tbdy_ref="TBDY 2018",
                evaluation_level="SCREENING",
            )

        safety_factor, Mr_knm = _compute_wall_overturning(
            M_overturning_knm=forces.M_inplane_knm,
            N_stabilizing_kn=forces.N_kn,
            lw_m=wall.lw_m,
        )

        if safety_factor < 1.5:
            return WallCheckResult(
                check_name="overturning",
                status="WARNING",
                ratio=1.5 / safety_factor if safety_factor > 0 else 999.0,
                value=safety_factor,
                limit=1.5,
                unit="ratio",
                message=(
                    f"Devrilme güvenliği düşük: SF={safety_factor:.2f} < 1.5. "
                    f"Mr={Mr_knm:.0f}kNm, Mo={abs(forces.M_inplane_knm):.0f}kNm. "
                    f"Temel bağlantısı ve komşu perde etkileşimi DESIGN_LEVEL değerlendirilmeli."
                ),
                tbdy_ref="TBDY 2018",
                evaluation_level="SCREENING",
            )

        return WallCheckResult(
            check_name="overturning",
            status="OK",
            ratio=safety_factor,
            value=safety_factor,
            limit=1.5,
            unit="ratio",
            message=f"Devrilme güvenli: SF={safety_factor:.2f} >= 1.5 (Mr={Mr_knm:.0f}kNm, Mo={abs(forces.M_inplane_knm):.0f}kNm)",
            tbdy_ref="TBDY 2018",
            evaluation_level="SCREENING",
        )

    def check_drift_compat(
        self,
        wall: WallGeometry,
        forces: Optional[WallForces] = None,
    ) -> WallCheckResult:
        """
        TBDY 2018 - Göreli kat ötelemesi uyumluluğu (screening)

        Drift oranı kontrolü.
        """
        if forces is None:
            forces = self._forces.get(wall.label)

        if not forces:
            return _no_data_result("drift_compat", "TBDY 2018", "Drift verisi yok")

        drift = forces.drift_ratio
        if drift <= 0:
            return WallCheckResult(
                check_name="drift_compat",
                status="OK",
                ratio=0.0,
                value=0.0,
                limit=0.005,
                unit="ratio",
                message="Drift verisi sıfır - kontrol yapılamadı",
                tbdy_ref="TBDY 2018",
                evaluation_level="SCREENING",
            )

        # TBDY limit: %0.5 (yüksek süneklik)
        drift_limit = 0.005
        ratio = drift / drift_limit

        if ratio > 1.0:
            return WallCheckResult(
                check_name="drift_compat",
                status="WARNING",
                ratio=ratio,
                value=drift,
                limit=drift_limit,
                unit="ratio",
                message=(
                    f"Göreli kat ötelemesi yüksek: drift={drift:.4f} > {drift_limit:.4f}. "
                    f"Başlık bölgesi ve perde donatısı DESIGN_LEVEL kontrol edilmeli."
                ),
                tbdy_ref="TBDY 2018",
                evaluation_level="SCREENING",
            )

        return WallCheckResult(
            check_name="drift_compat",
            status="OK",
            ratio=ratio,
            value=drift,
            limit=drift_limit,
            unit="ratio",
            message=f"Drift uygun: {drift:.4f} <= {drift_limit:.4f}",
            tbdy_ref="TBDY 2018",
            evaluation_level="SCREENING",
        )

    # -------------------------------------------------------------------------
    # MAIN
    # -------------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """
        Komple perde tasarım paketi.

        Aggregate politika:
        - FAIL varsa FAIL
        - WARNING varsa WARNING
        - NO_DATA varsa WARNING
        - hepsi OK ise OK
        """
        self.resolve_materials()
        self.resolve_walls()
        self.resolve_forces()
        self.resolve_rebar()

        outputs: List[WallDesignOutput] = []

        for wall in self._walls:
            out = WallDesignOutput(
                label=wall.label,
                story=wall.story,
                section=wall.section_name,
                materials=self._materials,
                geometry=wall,
                forces=self._forces.get(wall.label),
                rebar=self._rebar.get(wall.label),
            )

            checks: Dict[str, WallCheckResult] = {}
            forces = out.forces
            rebar = out.rebar

            # 1. Geometri
            checks["geometry"] = self.check_geometry(wall)

            # 2. Eksenel + Eğilme (PMM)
            checks["axial_flexure"] = self.check_axial_flexure(wall, forces, rebar)

            # 3. Kesme
            checks["shear"] = self.check_shear(wall, forces, rebar)

            # 4. Başlık bölgesi
            checks["boundary_zone"] = self.check_boundary_zone(wall, forces, rebar)

            # 5. Gövde donatısı minimum
            checks["shear_wall_reinf"] = self.check_shear_wall_reinforcement(wall, rebar)

            # 6. Devrilme (screening)
            checks["overturning"] = self.check_overturning(wall, forces)

            # 7. Drift uyumluluğu (screening)
            checks["drift_compat"] = self.check_drift_compat(wall, forces)

            out.checks = checks

            # Status aggregation
            statuses = [c.status for c in checks.values()]
            if "FAIL" in statuses:
                out.status = "FAIL"
            elif "WARNING" in statuses:
                out.status = "WARNING"
            elif "NO_DATA" in statuses:
                out.status = "WARNING"
            elif all(s == "OK" for s in statuses):
                out.status = "OK"
            else:
                out.status = "NO_DATA"

            # Governing check
            ratios = [(name, c.ratio) for name, c in checks.items() if c.ratio > 0]
            if ratios:
                out.governing_check, out.governing_ratio = max(ratios, key=lambda x: x[1])

            outputs.append(out)

        self._outputs = outputs

        # Package summary
        ok = sum(1 for o in outputs if o.status == "OK")
        fail = sum(1 for o in outputs if o.status == "FAIL")
        warn = sum(1 for o in outputs if o.status == "WARNING")
        nodata = sum(1 for o in outputs if o.status == "NO_DATA")

        if fail > 0:
            pkg_status = "FAIL"
        elif warn > 0:
            pkg_status = "WARNING"
        elif nodata == len(outputs):
            pkg_status = "NO_DATA"
        elif nodata > 0:
            pkg_status = "WARNING"
        else:
            pkg_status = "OK"

        summary = {
            "total_walls": len(outputs),
            "ok": ok,
            "fail": fail,
            "warning": warn,
            "no_data": nodata,
            "package_status": pkg_status,
            "materials_used": {
                "fck": self._materials.fck if self._materials else None,
                "fcd": self._materials.fcd if self._materials else None,
                "fyk": self._materials.fyk if self._materials else None,
                "fyd": self._materials.fyd if self._materials else None,
            } if self._materials else None,
        }

        return {
            "outputs": [self._output_to_dict(o) for o in outputs],
            "summary": summary,
            "package_status": pkg_status,
        }

    def _output_to_dict(self, out: WallDesignOutput) -> Dict[str, Any]:
        """WallDesignOutput → dict (JSON serializable)"""
        return {
            "label": out.label,
            "story": out.story,
            "section": out.section,
            "status": out.status,
            "geometry": {
                "length_mm": out.geometry.length_mm if out.geometry else None,
                "thickness_mm": out.geometry.thickness_mm if out.geometry else None,
                "clear_height_mm": out.geometry.clear_height_mm if out.geometry else None,
                "aspect_ratio": out.geometry.aspect_ratio if out.geometry else None,
                "is_slender": out.geometry.is_slender_wall if out.geometry else None,
            } if out.geometry else None,
            "forces": {
                "N_kn": out.forces.N_kn if out.forces else None,
                "M_inplane_knm": out.forces.M_inplane_knm if out.forces else None,
                "V_inplane_kn": out.forces.V_inplane_kn if out.forces else None,
                "drift_ratio": out.forces.drift_ratio if out.forces else None,
            } if out.forces else None,
            "rebar": {
                "rho_vertical_pct": out.rebar.rho_vertical_pct if out.rebar else None,
                "rho_horizontal_pct": out.rebar.rho_horizontal_pct if out.rebar else None,
                "has_boundary": out.rebar.has_boundary_data if out.rebar else False,
                "source": out.rebar.source if out.rebar else "none",
            } if out.rebar else None,
            "checks": {
                name: {
                    "status": c.status,
                    "ratio": c.ratio,
                    "value": c.value,
                    "limit": c.limit,
                    "unit": c.unit,
                    "message": c.message,
                    "tbdy_ref": c.tbdy_ref,
                    "evaluation_level": c.evaluation_level,
                }
                for name, c in out.checks.items()
            },
            "governing_check": out.governing_check,
            "governing_ratio": out.governing_ratio,
        }


# =============================================================================
# CONVENIENCE
# =============================================================================

def run_wall_design(ctx: Any) -> Dict[str, Any]:
    """
    Convenience function: context'ten perde tasarımını çalıştır.

    Args:
        ctx: ModelContext

    Returns:
        Dict: Tasarım sonuçları
    """
    module = WallDesignModule(ctx)
    return module.run()