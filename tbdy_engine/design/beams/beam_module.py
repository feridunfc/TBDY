"""
tbdy/design_engine/modules/beam_module.py

Tek kiris tasarim modulu.
Context builder (ModelContext) uzerinden calisir.
TBDY 2018 Bolum 7.4 + TS500 kiris kontrollerini icerir.

Checks:
  - geometry       : TBDY 2018 7.4.1 (minimum boyut, govde genisligi)
  - flexure        : TS500 egilme (cekme/basinc donatisi)
  - shear          : TS500 kesme (Vc + Vw)
  - torsion        : TS500 burulma (screening)
  - deflection     : TS500 sehim (screening/approximate)
  - crack_control  : TS500 catlak kontrolu (screening)
  - ductility      : TBDY 2018 7.4.2 (basinc donatisi orani, sargi)
  - capacity_hierarchy : TBDY 2018 7.4.3 (kolon-kiris birlesimi - screening)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import re
import logging

logger = logging.getLogger("beam_design")


# =============================================================================
# YARDIMCI VERI YAPILARI
# =============================================================================

@dataclass
class MaterialSet:
    """Beton ve donati tasarim malzemeleri (Column moduluyle ortak)"""
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
        """TS500 - Beton eksenel cekme dayanimi"""
        return 0.35 * math.sqrt(self.fck) / self.gamma_c

    @property
    def Ec(self) -> float:
        """TS500 - Beton elastisite modulu (MPa)"""
        return 3250 * math.sqrt(self.fck) + 14000


@dataclass
class BeamGeometry:
    """Kiris geometrisi"""
    label: str
    story: str
    section_name: str
    width_mm: float  # bw (mm olarak - TS500 formulleri mm kullanir)
    depth_mm: float  # h (mm)
    clear_span_m: float = 0.0  # net aciklik (m)
    flange_width_mm: float = 0.0  # tabla genisligi (T-kiris icin)
    flange_thickness_mm: float = 0.0  # tabla kalinligi

    @property
    def bw_m(self) -> float:
        return self.width_mm / 1000.0

    @property
    def h_m(self) -> float:
        return self.depth_mm / 1000.0

    @property
    def effective_depth_mm(self) -> float:
        """Kesme hesabi icin faydali yukseklik d = h - 50mm (paspayi)"""
        return self.depth_mm - 50.0

    @property
    def area_mm2(self) -> float:
        return self.width_mm * self.depth_mm

    @property
    def is_deep_beam(self) -> bool:
        """TS500 - Yuksek kiris kontrolu: ln/h <= 2.5 (derin kiris)"""
        if self.clear_span_m <= 0:
            return False
        return (self.clear_span_m / self.h_m) <= 2.5


@dataclass
class BeamForces:
    """Kiris tasarim kuvvetleri (zarftan)"""
    label: str
    M_pos_knm: float = 0.0  # aciklik pozitif moment (kN*m)
    M_neg_left_knm: float = 0.0  # sol mesnet negatif moment
    M_neg_right_knm: float = 0.0  # sag mesnet negatif moment
    V_max_kn: float = 0.0  # maksimum kesme kuvveti
    V_at_support_kn: float = 0.0  # mesnet yuzunde kesme
    T_max_knm: float = 0.0  # maksimum burulma momenti
    governing_combo: str = ""

    @property
    def M_max_neg_knm(self) -> float:
        return max(abs(self.M_neg_left_knm), abs(self.M_neg_right_knm))


@dataclass
class BeamRebar:
    """Kiris donati detayi"""
    label: str

    # Boyuna donati
    As_bottom_mm2: float = 0.0  # alt donati (aciklik)
    As_top_mm2: float = 0.0  # ust donati (mesnet)
    As_compression_mm2: float = 0.0  # basinc donatisi
    n_bars_bottom: int = 0
    n_bars_top: int = 0
    bar_diameter_long_mm: float = 0.0
    rho_tension_pct: float = 0.0  # cekme donatisi orani (%)

    # Enine donati (etriye)
    has_stirrup_data: bool = False
    stirrup_diameter_mm: float = 0.0
    stirrup_spacing_mm: float = 0.0
    stirrup_legs: int = 2  # etriye kol sayisi
    Asw_per_mm: float = 0.0  # birim boy basina etriye alani (mm2/mm)

    # Govde donatisi
    has_skin_rebar: bool = False
    As_skin_mm2: float = 0.0


@dataclass
class BeamCheckResult:
    """Tek bir check sonucu"""
    check_name: str
    status: str  # OK, WARNING, FAIL, NO_DATA, NOT_EVALUATED
    ratio: float = 0.0
    value: float = 0.0
    limit: float = 0.0
    unit: str = ""
    message: str = ""
    tbdy_ref: str = ""
    evaluation_level: str = "NOT_EVALUATED"  # DESIGN_LEVEL, SCREENING, APPROXIMATE, ETABS_DESIGN_RESULT


@dataclass
class BeamDesignOutput:
    """Tek kiris icin komple tasarim ciktisi"""
    label: str
    story: str
    section: str
    status: str = "NO_DATA"

    materials: Optional[MaterialSet] = None
    geometry: Optional[BeamGeometry] = None
    forces: Optional[BeamForces] = None
    rebar: Optional[BeamRebar] = None

    checks: Dict[str, BeamCheckResult] = field(default_factory=dict)

    governing_check: str = ""
    governing_ratio: float = 0.0


# =============================================================================
# GUVENLI DONUSUM YARDIMCILARI
# =============================================================================


def _parse_rect_section_mm(section_name: str) -> Tuple[float, float]:
    """
    Parse ETABS section names like B40x70, B60x100.

    Conservative policy:
    - Do not silently convert suspicious dimensions such as 100 to 1000 mm.
    - If a parsed dimension is suspicious, downstream checks must return WARNING
      and ask the engineer to verify section dimensions.

    Current convention:
    - values < 100 are treated as cm and converted to mm.
    - values >= 100 are kept as mm.
    """
    s = str(section_name or "").upper()
    m = re.search(r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", s)

    if not m:
        return 300.0, 500.0

    b = _safe_float(m.group(1), 30.0)
    h = _safe_float(m.group(2), 50.0)

    if b < 100.0:
        b *= 10.0
    if h < 100.0:
        h *= 10.0

    return b, h


def _df_col(df: Any, names: List[str]) -> Optional[str]:
    if df is None or not hasattr(df, "columns"):
        return None

    norm = {str(n).lower().replace(" ", "").replace("_", "") for n in names}

    for c in df.columns:
        cc = str(c).lower().replace(" ", "").replace("_", "")
        if cc in norm:
            return c

    for c in df.columns:
        cc = str(c).lower().replace(" ", "").replace("_", "")
        if any(n in cc for n in norm):
            return c

    return None


def _as_mm2_from_etabs(value: Any) -> float:
    v = _safe_float(value, 0.0)
    if 0.0 < v < 100.0:
        return v * 1_000_000.0
    return v

def _safe_float(value: Any, default: float = 0.0) -> float:
    """Guvenli float donusumu"""
    if value is None:
        return default
    try:
        v = float(value)
        return v if not math.isnan(v) else default
    except (ValueError, TypeError):
        return default


def _row_get_any(row: Any, keys: List[str], default: Any = None) -> Any:
    """Pandas Series / dict satirindan alias destekli guvenli okuma"""
    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            value = None
        if value not in (None, "", float("nan")):
            return value
    return default


def _no_data_result(check_name: str, tbdy_ref: str, message: str = "Veri eksik") -> BeamCheckResult:
    """Standart NO_DATA sonucu uret"""
    return BeamCheckResult(
        check_name=check_name,
        status="NO_DATA",
        message=message,
        tbdy_ref=tbdy_ref,
        evaluation_level="NOT_EVALUATED",
    )


# =============================================================================
# TS500 / TBDY 2018 HESAP FONKSIYONLARI
# =============================================================================

def _compute_flexural_capacity_rectangular(
    As_mm2: float,
    d_mm: float,
    b_mm: float,
    fyd_mpa: float,
    fcd_mpa: float,
    As_comp_mm2: float = 0.0,
    d_prime_mm: float = 40.0,
) -> Tuple[float, float]:
    """
    TS500 - Dikdortgen kesit egilme kapasitesi (basit denge denklemleri)

    a = As * fyd / (0.85 * fcd * b)
    Mr = As * fyd * (d - a/2)

    Returns:
        Mr_knm: Moment kapasitesi (kN*m)
        a_mm: Basinc blogu derinligi (mm)
    """
    if As_mm2 <= 0 or d_mm <= 0 or b_mm <= 0:
        return 0.0, 0.0

    # Basinc blogu derinligi
    a_mm = (As_mm2 * fyd_mpa) / (0.85 * fcd_mpa * b_mm) if fcd_mpa > 0 and b_mm > 0 else 0.0

    # Moment kapasitesi (N*mm -> kN*m)
    Mr_nmm = As_mm2 * fyd_mpa * (d_mm - a_mm / 2.0)
    Mr_knm = Mr_nmm / 1e6

    return Mr_knm, a_mm


def _compute_min_flexural_rebar(bw_mm: float, d_mm: float, fctd_mpa: float, fyd_mpa: float) -> float:
    """
    TS500 Madde 7.3.2 - Minimum cekme donatisi

    As_min = 0.8 * fctd * bw * d / fyd
    (TS500 2019 guncellemesi: As_min = max(0.8*fctd/fyd, 0.0015) * bw * d)
    """
    rho_min = max(0.8 * fctd_mpa / fyd_mpa, 0.0015)
    return rho_min * bw_mm * d_mm


def _compute_max_flexural_rebar(bw_mm: float, d_mm: float, fcd_mpa: float, fyd_mpa: float,
                                fck_mpa: float) -> float:
    """
    TS500 Madde 7.3.4 - Maksimum cekme donatisi

    rho_max = 0.85 * rho_b (dengeli donati orani)
    rho_b = 0.85 * k1 * fcd / fyd * (εcu / (εcu + εsy))
    k1 = 0.85 - 0.006*(fck-25) >= 0.70  (fck MPa)
    """
    k1 = max(0.70, 0.85 - 0.006 * (fck_mpa - 25.0))
    ecu = 0.003
    esy = 0.002  # S420 icin ~0.0021

    rho_b = 0.85 * k1 * (fcd_mpa / fyd_mpa) * (ecu / (ecu + esy))
    rho_max = 0.85 * rho_b

    return rho_max * bw_mm * d_mm


def _compute_shear_strength_concrete_beam(
    bw_mm: float,
    d_mm: float,
    fck_mpa: float,
    As_mm2: float = 0.0,
    Vd_kn: float = 0.0,
    Md_knm: float = 0.0,
) -> Tuple[float, float]:
    """
    TS500 Madde 8.1 - Betonarme kesme dayanimi (Vc) - Kiris

    Vc = 0.65 * fctd * bw * d  (basit yontem)
    Vc = 0.65 * fctd * bw * d * (1 + γ * Nd/Ag)  (eksenel varsa)

    Detayli yontem:
    Vc = [0.65 * fctd * bw * d + Vd * (As * d / Md)] (Vd/Md <= 1.0)

    Returns:
        Vc_kn: Beton katkisi (kN)
        Vc_max_kn: Maksimum kesme dayanimi (kN) - TS500 8.1.5
    """
    fctd = 0.35 * math.sqrt(abs(fck_mpa))

    # Basit yontem
    Vc_N = 0.65 * fctd * bw_mm * d_mm
    Vc_kn = Vc_N / 1000.0

    # Detayli yontem denemesi (eger moment ve donati varsa)
    if As_mm2 > 0 and Md_knm > 0 and Vd_kn > 0:
        Vd_over_Md = abs(Vd_kn) / (abs(Md_knm) * 1000.0) * (As_mm2 * d_mm)
        Vc_detailed_N = 0.65 * fctd * bw_mm * d_mm + abs(Vd_kn * 1000) * min(Vd_over_Md, 1.0)
        Vc_kn = Vc_detailed_N / 1000.0

    # Maksimum kesme dayanimi (TS500 8.1.5 - ezilme kontrolu)
    Vc_max_kn = 0.22 * (fck_mpa / 1.5) * bw_mm * d_mm / 1000.0

    return Vc_kn, Vc_max_kn


def _compute_shear_strength_stirrups(
    Asw_per_mm: float,
    d_mm: float,
    fywd_mpa: float,
) -> float:
    """
    TS500 Madde 8.1.4 - Etriye kesme dayanimi

    Vw = Asw/s * fywd * d

    Returns:
        Vw_kn: Etriye katkisi (kN)
    """
    if Asw_per_mm <= 0:
        return 0.0
    Vw_N = Asw_per_mm * fywd_mpa * d_mm
    return Vw_N / 1000.0


def _compute_min_stirrup_area(bw_mm: float, fctd_mpa: float, fywk_mpa: float) -> float:
    """
    TS500 Madde 8.2.2 - Minimum etriye alani

    Asw/s >= 0.3 * fctd * bw / fywk

    Returns:
        Asw_per_mm_min: mm2/mm
    """
    return 0.3 * fctd_mpa * bw_mm / fywk_mpa


def _compute_ductility_compression_requirement(
    M_pos_knm: float,
    M_neg_knm: float,
) -> float:
    """
    TBDY 2018 Madde 7.4.2 - Basinc donatisi kontrolu

    Mesnet bolgesinde:
    As_compression >= 0.5 * As_tension (yuksek suneklik)

    Returns:
        required_compression_ratio: Gerekli basinc/cekme donatisi orani
    """
    # Basitce 0.5 orani (tam hesap icin detayli PMM gerekir)
    return 0.5


def _compute_deflection_approx(
    L_m: float,
    h_mm: float,
    M_knm: float,
    Ec_mpa: float,
    I_mm4: float,
) -> Tuple[float, float]:
    """
    TS500 - Yaklasik sehim hesabi (basit kiris, duzgun yayili yuk varsayimi)

    delta = 5 * M * L^2 / (48 * Ec * I)

    Returns:
        deflection_mm: Sehim (mm)
        limit_mm: Sehim siniri L/360 (mm)
    """
    L_mm = L_m * 1000.0

    if Ec_mpa <= 0 or I_mm4 <= 0:
        return 0.0, L_mm / 360.0

    # M (N*mm) = M_knm * 1e6
    M_Nmm = abs(M_knm) * 1e6

    # Sehim (mm)
    deflection_mm = 5.0 * M_Nmm * (L_mm ** 2) / (48.0 * Ec_mpa * I_mm4)

    # Limit: L/360 (TS500)
    limit_mm = L_mm / 360.0

    return deflection_mm, limit_mm


# =============================================================================
# BEAM DESIGN MODULE
# =============================================================================

class BeamDesignModule:
    """
    Kiris Tasarim Modulu.

    ModelContext'ten okur, TBDY 2018 + TS500 kontrollerini yapar,
    her kiris icin BeamDesignOutput uretir.
    """

    def __init__(self, ctx: Any):
        """
        Args:
            ctx: app.engine.context_builder.ModelContext
        """
        self.ctx = ctx
        self._materials: Optional[MaterialSet] = None
        self._beams: List[BeamGeometry] = []
        self._forces: Dict[str, BeamForces] = {}
        self._rebar: Dict[str, BeamRebar] = {}
        self._outputs: List[BeamDesignOutput] = []

    # -------------------------------------------------------------------------
    # RESOLVE
    # -------------------------------------------------------------------------

    def resolve_materials(self) -> MaterialSet:
        """Design basis'ten malzeme setini coz"""
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

    def resolve_beams(self) -> List[BeamGeometry]:
        """
        Sprint 3.1b - Beam Inventory Normalization.

        Main inventory:
        - beam_design_summary unique story|label

        Topology:
        - only enrichment source for section/span/joints

        Excluded:
        - topology-only beams without design summary
        - Fxxx / empty-section frames not present in design summary

        Unit ambiguity:
        - B60x100 / B60x130 are not FAIL.
        - marked as unit_ambiguous=True on BeamGeometry.
        """
        self._beams = []

        tables = getattr(self.ctx, "tables", {}) or {}
        design_metadata = getattr(self.ctx, "design_metadata", {}) or {}
        topology = getattr(self.ctx, "topology", {}) or {}
        geometry = getattr(self.ctx, "geometry", {}) or {}

        df = tables.get("beam_design_summary")
        if df is None:
            df = design_metadata.get("beam_design_summary")

        if df is None or getattr(df, "empty", True):
            return self._beams

        label_col = _df_col(df, ["label", "beam", "frame", "element", "objlabel"])
        story_col = _df_col(df, ["story", "level"])
        sec_col = _df_col(df, ["designsect", "section", "section_name"])

        if not label_col:
            return self._beams

        section_dims = geometry.get("section_dims", {}) or {}
        beam_sections = geometry.get("beam_sections", {}) or {}
        beam_spans = geometry.get("beam_spans", {}) or {}
        beam_end_joints = topology.get("beam_end_joints", {}) if isinstance(topology, dict) else {}

        seen = set()
        beams: List[BeamGeometry] = []

        for _, row in df.iterrows():
            label = str(row.get(label_col) or "").strip()
            story = str(row.get(story_col) or "").strip() if story_col else ""

            if not label:
                continue

            key = f"{story}|{label}"

            if key in seen:
                continue
            seen.add(key)

            section_name = str(row.get(sec_col) or "").strip() if sec_col else ""

            if not section_name:
                section_name = str(beam_sections.get(key) or beam_sections.get(label) or "").strip()

            if label.upper().startswith("F") and not section_name:
                continue

            if not section_name:
                section_name = ""

            dims = section_dims.get(section_name, {}) or {}
            width_mm = _safe_float(dims.get("width_mm") or dims.get("b_mm"), 0.0)
            depth_mm = _safe_float(dims.get("depth_mm") or dims.get("h_mm"), 0.0)

            if width_mm <= 0 or depth_mm <= 0:
                width_mm, depth_mm = _parse_rect_section_mm(section_name)

            clear_span = _safe_float(beam_spans.get(key), 0.0)
            if clear_span <= 0:
                clear_span = _safe_float(beam_spans.get(label), 0.0)
            if clear_span <= 0:
                clear_span = 5.0

            beam = BeamGeometry(
                label=label,
                story=story,
                section_name=section_name,
                width_mm=width_mm,
                depth_mm=depth_mm,
                clear_span_m=clear_span,
            )

            joints = beam_end_joints.get(key) or beam_end_joints.get(label) or {}
            setattr(beam, "joint_i", joints.get("i"))
            setattr(beam, "joint_j", joints.get("j"))
            setattr(beam, "inventory_source", "beam_design_summary")
            setattr(beam, "inventory_key", key)
            setattr(beam, "unit_ambiguous", _beam_section_unit_ambiguous(section_name))

            beams.append(beam)

        self._beams = beams
        return self._beams



    def resolve_forces(self) -> Dict[str, BeamForces]:
        """
        Resolve beam force envelopes.

        Priority:
        1. ctx.envelopes["beam_forces_map"].
        2. ETABS beam_forces table.
        """
        self._forces = {}

        forces_map = self.ctx.envelopes.get("beam_forces_map", {}) or {}
        if isinstance(forces_map, dict) and forces_map:
            for label, env_data in forces_map.items():
                if not isinstance(env_data, dict):
                    continue

                bf = BeamForces(
                    label=str(label),
                    M_pos_knm=_safe_float(env_data.get("M_pos") or env_data.get("M3_pos")),
                    M_neg_left_knm=_safe_float(env_data.get("M_neg_left") or env_data.get("M3_neg_left")),
                    M_neg_right_knm=_safe_float(env_data.get("M_neg_right") or env_data.get("M3_neg_right")),
                    V_max_kn=_safe_float(env_data.get("V_max") or env_data.get("V2_max")),
                    V_at_support_kn=_safe_float(env_data.get("V_support") or env_data.get("V2_support")),
                    T_max_knm=_safe_float(env_data.get("T_max") or env_data.get("T")),
                    governing_combo=str(env_data.get("combo") or env_data.get("case") or ""),
                )
                self._forces[str(label)] = bf

            return self._forces

        df = self.ctx.tables.get("beam_forces")
        if df is None or getattr(df, "empty", True):
            return self._forces

        label_col = _df_col(df, ["label", "beam", "frame", "element"])
        combo_col = _df_col(df, ["combo", "case", "outputcase", "loadcase"])
        m3_col = _df_col(df, ["m3", "m3_knm", "moment3"])
        v2_col = _df_col(df, ["v2", "v2_kn", "shear2"])
        t_col = _df_col(df, ["t", "torsion", "torsion_knm"])

        if not label_col:
            return self._forces

        for label, group in df.groupby(label_col):
            label_s = str(label).strip()
            if not label_s:
                continue

            m_values = []
            v_values = []
            t_values = []
            combo = ""

            for _, row in group.iterrows():
                m = _safe_float(row.get(m3_col), 0.0) if m3_col else 0.0
                v = _safe_float(row.get(v2_col), 0.0) if v2_col else 0.0
                t = _safe_float(row.get(t_col), 0.0) if t_col else 0.0

                m_values.append(m)
                v_values.append(v)
                t_values.append(t)

            if combo_col and not group.empty:
                combo = str(group.iloc[0].get(combo_col) or "")

            positives = [x for x in m_values if x > 0]
            negatives = [x for x in m_values if x < 0]

            m_pos = max(positives) if positives else 0.0
            m_neg = min(negatives) if negatives else 0.0
            v_max = max([abs(x) for x in v_values], default=0.0)
            t_max = max([abs(x) for x in t_values], default=0.0)

            self._forces[label_s] = BeamForces(
                label=label_s,
                M_pos_knm=abs(m_pos),
                M_neg_left_knm=abs(m_neg),
                M_neg_right_knm=abs(m_neg),
                V_max_kn=v_max,
                V_at_support_kn=v_max,
                T_max_knm=t_max,
                governing_combo=combo,
            )

        return self._forces

    def resolve_rebar(self) -> Dict[str, BeamRebar]:
        """
        Resolve beam rebar.

        Priority:
        1. BeamRebarResolver from design/beams/rebar_set.py
           - provided schedule if available
           - ETABS beam_design_summary fallback
        2. Auto proposal for missing beams.

        Internal key in self._rebar remains beam.label for compatibility with current
        output. Resolver lookup uses story|label first to avoid cross-story mismatch.
        """
        from .rebar_set import BeamRebarResolver

        self._rebar = {}

        if not self._beams:
            self.resolve_beams()

        try:
            resolved = BeamRebarResolver(self.ctx).resolve()
        except Exception:
            resolved = {}

        for beam in self._beams:
            composite_key = f"{beam.story}|{beam.label}"
            rr = resolved.get(composite_key) or resolved.get(beam.label)

            if rr is None:
                continue

            data = rr.to_dict() if hasattr(rr, "to_dict") else dict(rr)

            As_top = _safe_float(data.get("as_top_provided_mm2"), 0.0)
            As_bot = _safe_float(data.get("as_bottom_provided_mm2"), 0.0)
            avs_per_m = _safe_float(data.get("av_s_provided_mm2_per_m"), 0.0)

            br = BeamRebar(
                label=beam.label,
                As_bottom_mm2=As_bot,
                As_top_mm2=As_top,
                As_compression_mm2=min(As_top, As_bot) if As_top > 0 and As_bot > 0 else 0.0,
                Asw_per_mm=avs_per_m / 1000.0 if avs_per_m > 0 else 0.0,
                has_stirrup_data=avs_per_m > 0,
                stirrup_diameter_mm=_safe_float(data.get("stirrup_diameter_mm"), 0.0),
                stirrup_spacing_mm=_safe_float(data.get("stirrup_spacing_mm"), 0.0),
                stirrup_legs=int(_safe_float(data.get("stirrup_leg_count"), 2)),
                rho_tension_pct=(max(As_top, As_bot) / beam.area_mm2 * 100.0) if beam.area_mm2 > 0 else 0.0,
            )
            setattr(br, "source", data.get("source") or "beam_rebar_resolver")
            setattr(br, "resolver_key", composite_key)
            setattr(br, "resolver_status", data.get("status") or "UNKNOWN")
            setattr(br, "resolver_note", data.get("note") or "")

            self._rebar[beam.label] = br

        for beam in self._beams:
            if beam.label not in self._rebar:
                self._rebar[beam.label] = self._propose_minimum_rebar(beam)

        return self._rebar

    def _resolve_rebar_from_etabs(self, design_summary: Any) -> None:
        """ETABS design summary'den donati coz"""
        for beam in self._beams:
            try:
                rows = design_summary[
                    design_summary.apply(
                        lambda r: str(r.get("label", r.get("Label", r.get("Frame", "")))).strip() == beam.label,
                        axis=1,
                    )
                ]
            except Exception:
                continue

            if rows is None or rows.empty:
                continue

            # En kritik istasyonu bul (maksimum As)
            best_row = None
            max_As = 0.0
            for _, row in rows.iterrows():
                As_top = _safe_float(row.get("As_top") or row.get("top_area"), 0.0)
                As_bot = _safe_float(row.get("As_bottom") or row.get("bottom_area"), 0.0)
                # m2 -> mm2 donusumu
                if 0 < As_top < 1.0:
                    As_top *= 1e6
                if 0 < As_bot < 1.0:
                    As_bot *= 1e6
                total = As_top + As_bot
                if total > max_As:
                    max_As = total
                    best_row = row

            if best_row is None:
                continue

            As_top = _safe_float(best_row.get("As_top") or best_row.get("top_area"), 0.0)
            As_bot = _safe_float(best_row.get("As_bottom") or best_row.get("bottom_area"), 0.0)
            if 0 < As_top < 1.0:
                As_top *= 1e6
            if 0 < As_bot < 1.0:
                As_bot *= 1e6

            Asw = _safe_float(best_row.get("Asw_per_m") or best_row.get("Asw"), 0.0)
            if 0 < Asw < 0.01:
                Asw *= 1e6  # m2/m -> mm2/m
            Asw_per_mm = Asw / 1000.0 if Asw > 0 else 0.0  # mm2/mm

            br = BeamRebar(
                label=beam.label,
                As_bottom_mm2=As_bot,
                As_top_mm2=As_top,
                Asw_per_mm=Asw_per_mm,
                has_stirrup_data=(Asw_per_mm > 0),
                rho_tension_pct=(max(As_top, As_bot) / beam.area_mm2 * 100.0) if beam.area_mm2 > 0 else 0.0,
            )
            setattr(br, "source", "etabs_design_summary")
            self._rebar[beam.label] = br

    def _resolve_rebar_from_sections(self, section_defs: Any) -> None:
        """Section-level rebar defs'ten donati coz"""
        for beam in self._beams:
            if beam.label in self._rebar:
                continue

            sec_data = None
            try:
                sec_rows = section_defs[
                    section_defs.apply(
                        lambda r: str(r.get("section", r.get("name", ""))).strip() == beam.section_name,
                        axis=1,
                    )
                ]
                if not sec_rows.empty:
                    sec_data = sec_rows.iloc[0]
            except Exception:
                continue

            if sec_data is None:
                continue

            As_top = _safe_float(sec_data.get("As_top_mm2") or sec_data.get("top_area"), 0.0)
            As_bot = _safe_float(sec_data.get("As_bottom_mm2") or sec_data.get("bottom_area"), 0.0)
            Asw = _safe_float(sec_data.get("Asw_mm2_per_m"), 0.0)

            br = BeamRebar(
                label=beam.label,
                As_bottom_mm2=As_bot,
                As_top_mm2=As_top,
                Asw_per_mm=Asw / 1000.0 if Asw > 0 else 0.0,
                has_stirrup_data=(Asw > 0),
                rho_tension_pct=(max(As_top, As_bot) / beam.area_mm2 * 100.0) if beam.area_mm2 > 0 else 0.0,
            )
            setattr(br, "source", "section_rebar_defs")
            self._rebar[beam.label] = br

    def _propose_minimum_rebar(self, beam: BeamGeometry) -> BeamRebar:
        """Minimum donati onerisi (auto proposal)"""
        if self._materials is None:
            self.resolve_materials()
        mat = self._materials

        d_mm = beam.effective_depth_mm
        As_min = _compute_min_flexural_rebar(beam.width_mm, d_mm, mat.fctd, mat.fyd)

        # Minimum etriye
        Asw_min_per_mm = _compute_min_stirrup_area(beam.width_mm, mat.fctd, mat.fyk)

        br = BeamRebar(
            label=beam.label,
            As_bottom_mm2=As_min,
            As_top_mm2=As_min * 1.5,  # mesnet icin biraz daha fazla
            Asw_per_mm=Asw_min_per_mm,
            has_stirrup_data=True,
            stirrup_diameter_mm=8.0,
            stirrup_spacing_mm=200.0,
            stirrup_legs=2,
            rho_tension_pct=(As_min * 1.5 / beam.area_mm2 * 100.0) if beam.area_mm2 > 0 else 0.0,
        )
        setattr(br, "source", "default")
        return br

    # -------------------------------------------------------------------------
    # CHECKS
    # -------------------------------------------------------------------------

    def check_geometry(self, beam: BeamGeometry) -> BeamCheckResult:
        """
        TBDY 2018 Madde 7.4.1 - Kiris minimum boyut kontrolu

        Yuksek suneklikli kirisler:
        - Govde genisligi >= 250 mm
        - h/b orani >= 2.0 (tercihen)
        - Derin kiris kontrolu (ln/h > 2.5 normal kiris)
        """
        issues = []

        if beam.width_mm < 250:
            issues.append(f"govde genisligi {beam.width_mm:.0f}mm < 250mm")

        h_over_b = beam.depth_mm / beam.width_mm if beam.width_mm > 0 else 0
        if h_over_b < 1.5:
            issues.append(f"h/b={h_over_b:.2f} < 1.5 (proportion warning, not capacity failure; recommended h/b >= 2.0)")

        if beam.is_deep_beam:
            issues.append(f"derin kiris: ln/h={(beam.clear_span_m / beam.h_m):.2f} <= 2.5")

        if issues:
            return BeamCheckResult(
                check_name="geometry",
                status="FAIL" if any("250mm" in i for i in issues) else "WARNING",
                ratio=0.0,
                value=beam.width_mm,
                limit=250.0,
                unit="mm",
                message="; ".join(issues),
                tbdy_ref="TBDY 2018 7.4.1",
                evaluation_level="DESIGN_LEVEL",
            )

        return BeamCheckResult(
            check_name="geometry",
            status="OK",
            ratio=1.0,
            value=beam.width_mm,
            limit=250.0,
            unit="mm",
            message=f"Geometri uygun (bw={beam.width_mm:.0f}mm, h={beam.depth_mm:.0f}mm)",
            tbdy_ref="TBDY 2018 7.4.1",
            evaluation_level="DESIGN_LEVEL",
        )

    def check_flexure(
        self,
        beam: BeamGeometry,
        forces: Optional[BeamForces] = None,
        rebar: Optional[BeamRebar] = None,
        mat: Optional[MaterialSet] = None,
    ) -> BeamCheckResult:
        """
        TS500 beam flexure check.

        Important:
        If source=etabs_beam_design_summary, astop/asbot values are ETABS design
        output/demand values, not a user-provided final rebar schedule. Therefore
        this function reports ETABS_DESIGN_RESULT instead of re-checking minimum
        detailing as if the bars were final provided reinforcement.
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if forces is None:
            forces = self._forces.get(beam.label)

        if rebar is None:
            rebar = self._rebar.get(beam.label)

        if not mat:
            return _no_data_result("flexure", "TS500", "Material data missing")

        if not rebar or (rebar.As_bottom_mm2 <= 0 and rebar.As_top_mm2 <= 0):
            return _no_data_result("flexure", "TS500", "Beam rebar data missing")

        source = str(getattr(rebar, "source", "unknown"))

        if source == "etabs_beam_design_summary":
            if rebar.As_top_mm2 > 0 and rebar.As_bottom_mm2 > 0:
                return BeamCheckResult(
                    check_name="flexure",
                    status="OK",
                    ratio=1.0,
                    value=max(rebar.As_top_mm2, rebar.As_bottom_mm2),
                    limit=0.0,
                    unit="mm2",
                    message=(
                        f"ETABS beam design summary used: "
                        f"As_top={rebar.As_top_mm2:.0f}mm2, As_bottom={rebar.As_bottom_mm2:.0f}mm2. "
                        f"This is design rebar demand, not user-provided final schedule."
                    ),
                    tbdy_ref="TS500 / TBDY 2018 7.4.2",
                    evaluation_level="ETABS_DESIGN_RESULT",
                )

            return BeamCheckResult(
                check_name="flexure",
                status="WARNING",
                ratio=0.0,
                value=0.0,
                limit=0.0,
                unit="mm2",
                message="ETABS beam design summary exists but top/bottom As is incomplete",
                tbdy_ref="TS500 / TBDY 2018 7.4.2",
                evaluation_level="ETABS_DESIGN_RESULT",
            )

        if not forces:
            return _no_data_result("flexure", "TS500", "Force envelope missing")

        evaluation_level = "DESIGN_LEVEL" if source != "default" else "SCREENING"

        d_mm = beam.effective_depth_mm
        ratios = []

        if rebar.As_bottom_mm2 > 0:
            Mr_pos, _ = _compute_flexural_capacity_rectangular(
                As_mm2=rebar.As_bottom_mm2,
                d_mm=d_mm,
                b_mm=beam.width_mm,
                fyd_mpa=mat.fyd,
                fcd_mpa=mat.fcd,
            )
            Md_pos = abs(forces.M_pos_knm)
            if Md_pos > 0:
                ratios.append(Md_pos / Mr_pos if Mr_pos > 0 else 999.0)

        if rebar.As_top_mm2 > 0:
            Mr_neg, _ = _compute_flexural_capacity_rectangular(
                As_mm2=rebar.As_top_mm2,
                d_mm=d_mm,
                b_mm=beam.width_mm,
                fyd_mpa=mat.fyd,
                fcd_mpa=mat.fcd,
            )
            Md_neg = forces.M_max_neg_knm
            if Md_neg > 0:
                ratios.append(Md_neg / Mr_neg if Mr_neg > 0 else 999.0)

        As_min = _compute_min_flexural_rebar(beam.width_mm, d_mm, mat.fctd, mat.fyd)
        min_rebar_ok = rebar.As_bottom_mm2 >= As_min and rebar.As_top_mm2 >= As_min
        governing_ratio = max(ratios) if ratios else 0.0

        if governing_ratio > 1.0:
            status = "FAIL"
        elif not min_rebar_ok:
            status = "FAIL"
            governing_ratio = max(governing_ratio, 1.01)
        elif source == "default":
            status = "WARNING"
        else:
            status = "OK"

        messages = []
        if ratios:
            messages.append(f"Md/Mr ratio={governing_ratio:.3f}")
        if not min_rebar_ok:
            messages.append(
                f"As_min={As_min:.0f}mm2 not satisfied "
                f"(bottom={rebar.As_bottom_mm2:.0f}, top={rebar.As_top_mm2:.0f})"
            )

        return BeamCheckResult(
            check_name="flexure",
            status=status,
            ratio=governing_ratio,
            value=governing_ratio,
            limit=1.0,
            unit="ratio",
            message="; ".join(messages) if messages else f"Flexure OK (ratio={governing_ratio:.3f})",
            tbdy_ref="TS500 / TBDY 2018 7.4.2",
            evaluation_level=evaluation_level,
        )

    def check_shear(
        self,
        beam: BeamGeometry,
        forces: Optional[BeamForces] = None,
        rebar: Optional[BeamRebar] = None,
        mat: Optional[MaterialSet] = None,
    ) -> BeamCheckResult:
        """
        TS500 + TBDY 2018 7.4.5 - Beam shear check.

        Ve <= Vr = Vc + Vw

        Fail-safe:
        If section dimension is unit-ambiguous, do not produce a false FAIL. Return WARNING
        and ask the engineer to verify section dimensions.
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if forces is None:
            forces = self._forces.get(beam.label)

        if rebar is None:
            rebar = self._rebar.get(beam.label)

        if not mat:
            return _no_data_result("shear", "TS500 8.1 / TBDY 2018 7.4.5", "Material data missing")

        if not forces:
            return _no_data_result("shear", "TS500 8.1 / TBDY 2018 7.4.5", "Force envelope missing")

        Ve = max(abs(forces.V_max_kn), abs(forces.V_at_support_kn))

        if Ve <= 0:
            return BeamCheckResult(
                check_name="shear",
                status="OK",
                ratio=0.0,
                value=0.0,
                limit=0.0,
                unit="kN",
                message="Shear force is zero; check not governing",
                tbdy_ref="TS500 8.1",
                evaluation_level="DESIGN_LEVEL",
            )

        d_mm = beam.effective_depth_mm

        if beam.depth_mm < 300.0 or d_mm <= 150.0:
            return BeamCheckResult(
                check_name="shear",
                status="WARNING",
                ratio=0.0,
                value=Ve,
                limit=0.0,
                unit="kN",
                message=(
                    f"Beam shear WARNING: unit ambiguous section; verify whether section dimensions are cm or mm before DESIGN_LEVEL shear check: "
                    f"section={beam.section_name}, bw={beam.width_mm:.0f}mm, h={beam.depth_mm:.0f}mm, d={d_mm:.0f}mm. "
                    f"Unit ambiguous section; verify B60x100/B60x130-style dimensions are cm or mm in ETABS/table mapping."
                ),
                tbdy_ref="TS500 8.1 / TBDY 2018 7.4.5",
                evaluation_level="SCREENING",
            )

        Vc_kn, Vc_max_kn = _compute_shear_strength_concrete_beam(
            bw_mm=beam.width_mm,
            d_mm=d_mm,
            fck_mpa=mat.fck,
            As_mm2=rebar.As_bottom_mm2 if rebar else 0.0,
            Vd_kn=Ve,
            Md_knm=max(abs(forces.M_pos_knm), forces.M_max_neg_knm),
        )

        Vw_kn = 0.0
        if rebar and rebar.has_stirrup_data and rebar.Asw_per_mm > 0:
            Vw_kn = _compute_shear_strength_stirrups(
                Asw_per_mm=rebar.Asw_per_mm,
                d_mm=d_mm,
                fywd_mpa=mat.fywd,
            )

        Vr_kn = Vc_kn + Vw_kn
        Vr_max_kn = min(Vr_kn, Vc_max_kn)

        ratio = Ve / Vr_max_kn if Vr_max_kn > 0 else 999.0

        source = getattr(rebar, "source", "unknown") if rebar else "unknown"
        evaluation_level = "DESIGN_LEVEL" if source != "default" else "SCREENING"

        if ratio > 1.0:
            Asw_min = _compute_min_stirrup_area(beam.width_mm, mat.fctd, mat.fyk)

            if rebar and rebar.Asw_per_mm < Asw_min:
                msg = (
                    f"Shear FAIL: Ve={Ve:.0f}kN > Vr={Vr_max_kn:.0f}kN "
                    f"(Vc={Vc_kn:.0f}, Vw={Vw_kn:.0f}); "
                    f"minimum stirrup also not satisfied: "
                    f"Asw={rebar.Asw_per_mm*1000:.1f}mm2/m < min={Asw_min*1000:.1f}mm2/m"
                )
            else:
                msg = f"Shear FAIL: Ve={Ve:.0f}kN > Vr={Vr_max_kn:.0f}kN (Vc={Vc_kn:.0f}, Vw={Vw_kn:.0f})"

            return BeamCheckResult(
                check_name="shear",
                status="FAIL",
                ratio=ratio,
                value=Ve,
                limit=Vr_max_kn,
                unit="kN",
                message=msg,
                tbdy_ref="TS500 8.1 / TBDY 2018 7.4.5",
                evaluation_level=evaluation_level,
            )

        status = "WARNING" if source == "default" else "OK"

        return BeamCheckResult(
            check_name="shear",
            status=status,
            ratio=ratio,
            value=Ve,
            limit=Vr_max_kn,
            unit="kN",
            message=f"Shear OK: Ve={Ve:.0f}kN <= Vr={Vr_max_kn:.0f}kN (Vc={Vc_kn:.0f}, Vw={Vw_kn:.0f})",
            tbdy_ref="TS500 8.1 / TBDY 2018 7.4.5",
            evaluation_level=evaluation_level,
        )

    def check_ductility(
        self,
        beam: BeamGeometry,
        rebar: Optional[BeamRebar] = None,
        mat: Optional[MaterialSet] = None,
    ) -> BeamCheckResult:
        """
        TBDY 2018 7.4.2 beam ductility/detailing check.

        If source=etabs_beam_design_summary, the available data is design demand,
        not final user-provided bar layout. Compression reinforcement and detailing
        checks cannot be completed at DESIGN_LEVEL. Return WARNING instead of FAIL.
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if rebar is None:
            rebar = self._rebar.get(beam.label)

        if not mat:
            return _no_data_result("ductility", "TBDY 2018 7.4.2", "Material data missing")

        if not rebar or rebar.As_top_mm2 <= 0:
            return _no_data_result("ductility", "TBDY 2018 7.4.2", "Beam rebar data missing")

        source = str(getattr(rebar, "source", "unknown"))

        if source == "etabs_beam_design_summary":
            return BeamCheckResult(
                check_name="ductility",
                status="WARNING",
                ratio=0.0,
                value=0.0,
                limit=0.0,
                unit="",
                message=(
                    "Ductility/detailing requires final provided beam rebar schedule. "
                    "ETABS beam_design_summary demand values are available, but bar layout, "
                    "compression bars and confinement detailing are not complete."
                ),
                tbdy_ref="TBDY 2018 7.4.2",
                evaluation_level="SCREENING",
            )

        d_mm = beam.effective_depth_mm
        issues = []

        As_max = _compute_max_flexural_rebar(beam.width_mm, d_mm, mat.fcd, mat.fyd, mat.fck)
        if rebar.As_top_mm2 > As_max:
            issues.append(f"top rebar exceeds As_max={As_max:.0f}mm2")

        As_min = _compute_min_flexural_rebar(beam.width_mm, d_mm, mat.fctd, mat.fyd)
        if rebar.As_bottom_mm2 < As_min:
            issues.append(f"bottom rebar below As_min={As_min:.0f}mm2")

        As_comp = rebar.As_compression_mm2 if rebar.As_compression_mm2 > 0 else 0.0
        compression_ratio = As_comp / rebar.As_top_mm2 if rebar.As_top_mm2 > 0 else 0.0

        evaluation_level = "DESIGN_LEVEL" if source != "default" else "SCREENING"

        if compression_ratio < 0.3 and rebar.As_top_mm2 > 0 and source != "default":
            issues.append(f"As_comp/As_tension={compression_ratio:.2f} < 0.5")

        if issues:
            return BeamCheckResult(
                check_name="ductility",
                status="FAIL",
                ratio=compression_ratio,
                value=compression_ratio,
                limit=0.5,
                unit="ratio",
                message="; ".join(issues),
                tbdy_ref="TBDY 2018 7.4.2",
                evaluation_level=evaluation_level,
            )

        return BeamCheckResult(
            check_name="ductility",
            status="OK" if source != "default" else "WARNING",
            ratio=compression_ratio,
            value=compression_ratio,
            limit=0.5,
            unit="ratio",
            message=(
                f"Ductility OK: top_rebar_ratio={rebar.As_top_mm2/beam.area_mm2*100:.2f}%, "
                f"As_comp/As_tension={compression_ratio:.2f}"
            ),
            tbdy_ref="TBDY 2018 7.4.2",
            evaluation_level=evaluation_level,
        )

    def check_deflection(
        self,
        beam: BeamGeometry,
        forces: Optional[BeamForces] = None,
        mat: Optional[MaterialSet] = None,
    ) -> BeamCheckResult:
        """
        TS500 - Kiris sehim kontrolu (yaklasik yontem)

        Screening seviyesinde calisir. Tam hesap icin catlamis kesit ataleti gerekir.
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if forces is None:
            forces = self._forces.get(beam.label)

        if not mat:
            return _no_data_result("deflection", "TS500", "Malzeme verisi yok")

        if not forces:
            return _no_data_result("deflection", "TS500", "Kuvvet verisi yok")

        if beam.clear_span_m <= 0:
            return _no_data_result("deflection", "TS500", "Aciklik bilgisi yok")

        # Brut kesit ataleti (mm4)
        I_gross = beam.width_mm * (beam.depth_mm ** 3) / 12.0

        deflection_mm, limit_mm = _compute_deflection_approx(
            L_m=beam.clear_span_m,
            h_mm=beam.depth_mm,
            M_knm=max(abs(forces.M_pos_knm), forces.M_max_neg_knm),
            Ec_mpa=mat.Ec,
            I_mm4=I_gross,
        )

        ratio = deflection_mm / limit_mm if limit_mm > 0 else 0.0

        if ratio > 1.0:
            return BeamCheckResult(
                check_name="deflection",
                status="WARNING",
                ratio=ratio,
                value=deflection_mm,
                limit=limit_mm,
                unit="mm",
                message=(
                    f"Sehim sinir asimi: delta={deflection_mm:.1f}mm > L/360={limit_mm:.1f}mm "
                    f"(ratio={ratio:.2f}). Tam hesap onerilir."
                ),
                tbdy_ref="TS500",
                evaluation_level="APPROXIMATE",
            )

        return BeamCheckResult(
            check_name="deflection",
            status="OK",
            ratio=ratio,
            value=deflection_mm,
            limit=limit_mm,
            unit="mm",
            message=f"Sehim uygun: delta={deflection_mm:.1f}mm <= L/360={limit_mm:.1f}mm (yaklasik)",
            tbdy_ref="TS500",
            evaluation_level="APPROXIMATE",
        )

    def check_torsion(
        self,
        beam: BeamGeometry,
        forces: Optional[BeamForces] = None,
    ) -> BeamCheckResult:
        """
        TS500 - Burulma kontrolu (screening)

        Td <= Tcr (catlama burulma momenti) ise burulma ihmal edilebilir.
        Tcr = fctd * Acp^2 / Pcp
        """
        if forces is None:
            forces = self._forces.get(beam.label)

        if not forces:
            return _no_data_result("torsion", "TS500", "Kuvvet verisi yok")

        if abs(forces.T_max_knm) < 0.01:
            return BeamCheckResult(
                check_name="torsion",
                status="OK",
                ratio=0.0,
                value=0.0,
                limit=0.0,
                unit="kN*m",
                message="Burulma momenti ihmal edilebilir duzeyde",
                tbdy_ref="TS500",
                evaluation_level="SCREENING",
            )

        if self._materials is None:
            self.resolve_materials()

        # Catlama burulma momenti (basitlestirilmis)
        Acp = beam.width_mm * beam.depth_mm
        Pcp = 2.0 * (beam.width_mm + beam.depth_mm)
        Tcr_Nmm = self._materials.fctd * (Acp ** 2) / Pcp
        Tcr_knm = Tcr_Nmm / 1e6

        ratio = abs(forces.T_max_knm) / Tcr_knm if Tcr_knm > 0 else 0.0

        if ratio > 1.0:
            return BeamCheckResult(
                check_name="torsion",
                status="WARNING",
                ratio=ratio,
                value=abs(forces.T_max_knm),
                limit=Tcr_knm,
                unit="kN*m",
                message=f"Burulma etkisi onemli: Td={abs(forces.T_max_knm):.1f}kNm > Tcr={Tcr_knm:.1f}kNm. Detayli hesap gerekir.",
                tbdy_ref="TS500",
                evaluation_level="SCREENING",
            )

        return BeamCheckResult(
            check_name="torsion",
            status="OK",
            ratio=ratio,
            value=abs(forces.T_max_knm),
            limit=Tcr_knm,
            unit="kN*m",
            message=f"Burulma ihmal edilebilir: Td={abs(forces.T_max_knm):.1f}kNm <= Tcr={Tcr_knm:.1f}kNm",
            tbdy_ref="TS500",
            evaluation_level="SCREENING",
        )

    def check_capacity_hierarchy(self, beam: BeamGeometry) -> BeamCheckResult:
        """
        TBDY 2018 Madde 7.4.3 - Kolon-kiris birlesimi kapasite hiyerarsisi

        Screening seviyesinde. Joint modulu tam entegrasyonu bekleniyor.
        """
        raw_map = self.ctx.topology.get("beam_column_map", {})
        connected_columns = []

        if isinstance(raw_map, dict):
            connected_columns = raw_map.get(beam.label, []) or []
        elif isinstance(raw_map, list):
            for item in raw_map:
                if isinstance(item, dict):
                    beam_label = str(
                        item.get("beam") or item.get("beam_label") or item.get("Beam") or ""
                    )
                    if beam_label == beam.label:
                        cols = item.get("columns") or item.get("connected_columns") or []
                        if isinstance(cols, list):
                            connected_columns.extend(cols)
                        elif cols:
                            connected_columns.append(cols)

        if not connected_columns:
            return BeamCheckResult(
                check_name="capacity_hierarchy",
                status="WARNING",
                ratio=0.0,
                value=0.0,
                limit=1.0,
                unit="",
                message=(
                    f"{beam.label} icin bagli kolon/topoloji verisi yok. "
                    f"Kapasite hiyerarsisi DESIGN_LEVEL yapilamadi. "
                    f"Joint sprint sonrasi tekrar degerlendirilmeli."
                ),
                tbdy_ref="TBDY 2018 7.4.3",
                evaluation_level="SCREENING",
            )

        return BeamCheckResult(
            check_name="capacity_hierarchy",
            status="WARNING",
            ratio=0.0,
            value=0.0,
            limit=1.0,
            unit="",
            message=(
                f"{beam.label} icin {len(connected_columns)} bagli kolon bulundu. "
                f"Tam kapasite hiyerarsisi Joint modulu ile yapilacak."
            ),
            tbdy_ref="TBDY 2018 7.4.3",
            evaluation_level="SCREENING",
        )

    # -------------------------------------------------------------------------
    # MAIN
    # -------------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """
        Komple kiris tasarim paketi.

        Aggregate politika (Column modulu ile ayni):
        - FAIL varsa FAIL
        - WARNING varsa WARNING
        - NO_DATA varsa WARNING
        - hepsi OK ise OK
        """
        self.resolve_materials()
        self.resolve_beams()
        self.resolve_forces()
        self.resolve_rebar()

        outputs: List[BeamDesignOutput] = []

        for beam in self._beams:
            out = BeamDesignOutput(
                label=beam.label,
                story=beam.story,
                section=beam.section_name,
                materials=self._materials,
                geometry=beam,
                forces=self._forces.get(beam.label),
                rebar=self._rebar.get(beam.label),
            )

            checks: Dict[str, BeamCheckResult] = {}
            forces = out.forces
            rebar = out.rebar

            # 1. Geometri kontrolu
            checks["geometry"] = self.check_geometry(beam)

            # 2. Egilme kontrolu
            checks["flexure"] = self.check_flexure(beam, forces, rebar)

            # 3. Kesme kontrolu
            checks["shear"] = self.check_shear(beam, forces, rebar)

            # 4. Suneklik kontrolu
            checks["ductility"] = self.check_ductility(beam, rebar)

            # 5. Sehim kontrolu (screening)
            checks["deflection"] = self.check_deflection(beam, forces)

            # 6. Burulma kontrolu (screening)
            checks["torsion"] = self.check_torsion(beam, forces)

            # 7. Kapasite hiyerarsisi (screening)
            checks["capacity_hierarchy"] = self.check_capacity_hierarchy(beam)

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
            "total_beams": len(outputs),
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

    def _output_to_dict(self, out: BeamDesignOutput) -> Dict[str, Any]:
        """BeamDesignOutput → dict (JSON serializable)"""
        return {
            "label": out.label,
            "story": out.story,
            "section": out.section,
            "status": out.status,
            "geometry": {
                "width_mm": out.geometry.width_mm if out.geometry else None,
                "depth_mm": out.geometry.depth_mm if out.geometry else None,
                "clear_span_m": out.geometry.clear_span_m if out.geometry else None,
            } if out.geometry else None,
            "forces": {
                "M_pos_knm": out.forces.M_pos_knm if out.forces else None,
                "M_neg_left_knm": out.forces.M_neg_left_knm if out.forces else None,
                "M_neg_right_knm": out.forces.M_neg_right_knm if out.forces else None,
                "V_max_kn": out.forces.V_max_kn if out.forces else None,
                "T_max_knm": out.forces.T_max_knm if out.forces else None,
            } if out.forces else None,
            "rebar": {
                "As_bottom_mm2": out.rebar.As_bottom_mm2 if out.rebar else None,
                "As_top_mm2": out.rebar.As_top_mm2 if out.rebar else None,
                "Asw_per_mm": out.rebar.Asw_per_mm if out.rebar else None,
                "rho_tension_pct": out.rebar.rho_tension_pct if out.rebar else None,
                "source": getattr(out.rebar, "source", "unknown") if out.rebar else "none",
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


def _beam_section_unit_ambiguous(section_name: str) -> bool:
    import re

    s = str(section_name or "").upper()
    m = re.search(r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", s)
    if not m:
        return True

    h = _safe_float(m.group(2), 0.0)

    # 100, 130 gibi değerler mm/cm belirsizdir.
    return 100.0 <= h < 300.0



# =============================================================================
# CONVENIENCE
# =============================================================================

def run_beam_design(ctx: Any) -> Dict[str, Any]:
    """
    Convenience function: context'ten kiris tasarimini calistir.

    Args:
        ctx: ModelContext

    Returns:
        Dict: Tasarim sonuclari
    """
    module = BeamDesignModule(ctx)
    return module.run()
