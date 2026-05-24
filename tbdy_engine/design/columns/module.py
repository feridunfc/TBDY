"""
tbdy/design_engine/modules/module.py

Tek kolon tasarim modulu.
Context builder (ModelContext) uzerinden calisir.
Tum TBDY 2018 Bolum 7 kolon kontrollerini icerir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import re
import logging

logger = logging.getLogger("column_design")


# =============================================================================
# YARDIMCI VERI YAPILARI
# =============================================================================

@dataclass
class MaterialSet:
    """Beton ve donati tasarim malzemeleri"""
    fck: float  # MPa
    fcd: float  # MPa
    fyk: float  # MPa
    fyd: float  # MPa
    fywd: float  # MPa
    gamma_c: float
    gamma_s: float
    ecu: float = 0.003  # beton birim kisalmasi
    esy: float = 0.002  # donati akma birim uzamasi

    @property
    def fctd(self) -> float:
        """Beton eksenel cekme dayanimi (TS500)"""
        return 0.35 * math.sqrt(self.fck) / self.gamma_c


@dataclass
class ColumnGeometry:
    """Kolon geometrisi"""
    label: str
    story: str
    section_name: str
    width_m: float  # b (m)
    depth_m: float  # h (m)
    clear_height_m: float = 0.0  # net yukseklik (m)

    @property
    def area_m2(self) -> float:
        return self.width_m * self.depth_m

    @property
    def area_mm2(self) -> float:
        return self.area_m2 * 1e6

    @property
    def b_min_mm(self) -> int:
        return int(min(self.width_m, self.depth_m) * 1000)

    @property
    def b_max_mm(self) -> int:
        return int(max(self.width_m, self.depth_m) * 1000)

    @property
    def effective_depth_m(self) -> float:
        """Kesme hesabi icin faydali yukseklik (d)"""
        return self.depth_m - 0.04  # ~40mm paspayi varsayimi


@dataclass
class ColumnForces:
    """Kolon tasarim kuvvetleri (zarftan)"""
    label: str
    N_kn: float = 0.0  # eksenel (basinc +)
    Mx_knm: float = 0.0  # major moment
    My_knm: float = 0.0  # minor moment
    Vx_kn: float = 0.0  # major yon kesme
    Vy_kn: float = 0.0  # minor yon kesme
    governing_combo: str = ""
    N_case: str = ""
    Mx_case: str = ""
    My_case: str = ""
    Vx_case: str = ""
    Vy_case: str = ""

    @property
    def N_kN(self) -> float:
        return abs(self.N_kn)

    @property
    def is_tension(self) -> bool:
        return self.N_kn < 0


@dataclass
class ColumnRebar:
    """Kolon donati detayi"""
    label: str
    n_bars_total: int = 0  # toplam boyuna donati adedi
    bar_diameter_mm: float = 0.0  # boyuna donati capi
    As_total_mm2: float = 0.0  # toplam boyuna donati alani
    rho: float = 0.0  # donati orani (%)

    # Enine donati (sargi)
    has_confinement_data: bool = False
    stirrup_diameter_mm: float = 0.0
    stirrup_spacing_mm: float = 0.0
    stirrup_legs_dir1: int = 0  # b yonu ciroz kollari
    stirrup_legs_dir2: int = 0  # h yonu ciroz kollari
    Ash_dir1_mm2: float = 0.0  # b yonu sargi donatisi alani
    Ash_dir2_mm2: float = 0.0  # h yonu sargi donatisi alani


@dataclass
class ColumnCheckResult:
    """Tek bir check sonucu"""
    check_name: str
    status: str  # OK, WARNING, FAIL, NO_DATA
    ratio: float = 0.0  # kapasite orani
    value: float = 0.0  # hesaplanan deger
    limit: float = 0.0  # limit deger
    unit: str = ""
    message: str = ""
    tbdy_ref: str = ""
    governing_combo: Optional[str] = None

@dataclass
class ColumnDesignOutput:
    """Tek kolon icin komple tasarim ciktisi"""
    label: str
    story: str
    section: str
    status: str = "NO_DATA"

    # Malzeme
    materials: Optional[MaterialSet] = None

    # Geometri
    geometry: Optional[ColumnGeometry] = None

    # Kuvvetler
    forces: Optional[ColumnForces] = None

    # Donati
    rebar: Optional[ColumnRebar] = None

    # Tum check sonuclari
    checks: Dict[str, ColumnCheckResult] = field(default_factory=dict)

    # Governing
    governing_check: str = ""
    governing_ratio: float = 0.0

    @property
    def check_list(self) -> List[ColumnCheckResult]:
        return list(self.checks.values())


# =============================================================================
# HESAP YARDIMCILARI
# =============================================================================

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
    """Pandas Series / dict satirindan alias destekli guvenli okuma."""
    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            value = None

        if value not in (None, ""):
            return value

    return default


def _choose_min_longitudinal_rebar(area_mm2: float) -> Tuple[int, float, float, float]:
    """
    Otomatik kolon minimum boyuna donati onerisi.

    Kurallar:
    - rho >= %1.0
    - n_bars >= 6
    - bar diameter >= Phi14
    """
    required_as = max(0.01 * area_mm2, 0.0)
    best: Optional[Tuple[float, int, float]] = None

    for dia in [14, 16, 18, 20, 22, 25, 28, 32]:
        area_one = math.pi * dia ** 2 / 4.0
        for n in [6, 8, 10, 12, 14, 16, 18, 20, 24]:
            as_total = n * area_one
            if as_total >= required_as:
                candidate = (as_total, n, float(dia))
                if best is None or candidate[0] < best[0]:
                    best = candidate
                break

    if best is None:
        dia = 32.0
        area_one = math.pi * dia ** 2 / 4.0
        n = max(24, int(math.ceil(required_as / area_one)))
        best = (n * area_one, n, dia)

    as_total, n, dia = best
    rho = as_total / area_mm2 * 100.0 if area_mm2 > 0 else 0.0
    return n, dia, as_total, rho


def _choose_confinement_proposal(required_ash_mm2: float) -> Tuple[float, int, float]:
    """
    Sargi icin uygulanabilir otomatik oneri.

    Bu gercek ETABS/user donatisi degildir; screening/proposal bilgisidir.
    """
    required = max(required_ash_mm2, 0.0)
    best: Optional[Tuple[float, float, int]] = None

    for dia in [8, 10, 12, 14, 16]:
        area_one = math.pi * dia ** 2 / 4.0
        for legs in [2, 4, 6, 8, 10, 12]:
            ash = area_one * legs
            if ash >= required:
                candidate = (ash, float(dia), legs)
                if best is None or candidate[0] < best[0]:
                    best = candidate
                break

    if best is None:
        dia = 16.0
        area_one = math.pi * dia ** 2 / 4.0
        legs = max(12, int(math.ceil(required / area_one)))
        best = (area_one * legs, dia, legs)

    ash, dia, legs = best
    return dia, legs, ash


def _compute_axial_capacity_ratio(Nd: float, Ac_m2: float, fcd_mpa: float) -> float:
    """
    TBDY 2018 - Madde 7.3.2
    Nd <= 0.40 * Ac * fcd  (yuksek suneklik)
    Nd <= 0.60 * Ac * fcd  (normal suneklik - burada yuksek suneklik varsayiyoruz)
    """
    Ac_mm2 = Ac_m2 * 1e6
    N_limit_kn = 0.40 * Ac_mm2 * fcd_mpa / 1000  # kN
    ratio = abs(Nd) / N_limit_kn if N_limit_kn > 0 else 999
    return ratio, N_limit_kn


def _compute_confinement_required_ash(
        s_mm: float,
        bk_mm: float,
        fck_mpa: float,
        fywk_mpa: float,
        Ac_mm2: float,
        Ack_mm2: float,
) -> float:
    """
    TBDY 2018 Denklem 7.1 - Sargi donatisi hesabi

    Ash >= 0.30 * s * bk * ((Ac/Ack) - 1) * (fck/fywk)
    """
    if Ack_mm2 <= 0 or fywk_mpa <= 0:
        return 0.0

    ratio = (Ac_mm2 / Ack_mm2) - 1.0
    if ratio < 0:
        ratio = 0.0

    return 0.30 * s_mm * bk_mm * ratio * (fck_mpa / fywk_mpa)


def _compute_confinement_min_ash(
        s_mm: float,
        bk_mm: float,
        fck_mpa: float,
        fywk_mpa: float,
) -> float:
    """
    TBDY 2018 Denklem 7.2 - Minimum sargi donatisi

    Ash >= 0.075 * s * bk * (fck/fywk)
    """
    return 0.075 * s_mm * bk_mm * (fck_mpa / fywk_mpa)


def _compute_shear_strength_concrete(
        Nd_kn: float,
        Ac_m2: float,
        fcd_mpa: float,
        fck_mpa: float,  # ← YENI: beton karakteristik dayanimi
        d_m: float,
        bw_m: float,
) -> Tuple[float, float]:
    """
    TS500 Betonarme Kesme Dayanimi (Vc)

    Vc = 0.65 * fctd * bw * d * (1 + γ * Nd / Ac)
    fctd = 0.35 * sqrt(fck)  (TS500, MPa)
    """
    # fctd hesabi (TS500)
    fctd = 0.35 * math.sqrt(abs(fck_mpa))  # MPa

    # kN biriminde
    Nd_MN = Nd_kn / 1000  # MN
    Nd_MPa = Nd_MN / Ac_m2 if Ac_m2 > 0 else 0  # MPa

    if Nd_kn >= 0:  # basinc
        factor = 1.0 + 0.07 * abs(Nd_MPa)
    else:  # cekme
        factor = max(0.0, 1.0 - 0.30 * abs(Nd_MPa))

    Vc_N = 0.65 * fctd * (bw_m * 1000) * (d_m * 1000) * factor
    Vc_max_N = 0.22 * fcd_mpa * (bw_m * 1000) * (d_m * 1000)

    return Vc_N / 1000, Vc_max_N / 1000  # kN

def _compute_shear_strength_stirrups(
        Asw_mm2: float,
        s_mm: float,
        d_m: float,
        fywd_mpa: float,
) -> float:
    """
    TS500 - Etriye kesme dayanimi

    Vw = Asw * fywd * d / s
    """
    if s_mm <= 0:
        return 0.0
    return (Asw_mm2 * fywd_mpa * d_m * 1000 / s_mm) / 1000  # kN


# =============================================================================
# ANA MODUL
# =============================================================================

class ColumnDesignModule:
    """
    Kolon Tasarim Modulu.

    ModelContext'ten okur, TBDY 2018 kontrollerini yapar,
    her kolon icin ColumnDesignOutput uretir.
    """

    def __init__(self, ctx: Any):
        """
        Args:
            ctx: app.engine.context_builder.ModelContext
        """
        self.ctx = ctx
        self._materials: Optional[MaterialSet] = None
        self._columns: List[ColumnGeometry] = []
        self._forces: Dict[str, ColumnForces] = {}
        self._rebar: Dict[str, ColumnRebar] = {}
        self._outputs: List[ColumnDesignOutput] = []

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

    def resolve_columns(self) -> List[ColumnGeometry]:
        """Topology ve geometry'den kolon geometrilerini coz"""
        columns = []

        # Topology'den kolon listesi
        topo_columns = self.ctx.topology.get("columns", [])
        section_dims = self.ctx.geometry.get("section_dims", {})
        frame_sections = self.ctx.geometry.get("column_sections", {})
        story_heights = self.ctx.story_height_map

        for col_data in topo_columns:
            label = str(col_data.get("label", ""))
            story = str(col_data.get("story", ""))

            if not label:
                continue

            # Kesit adini bul
            section_name = frame_sections.get(label, "")
            if not section_name:
                section_name = str(col_data.get("section", ""))

            # Kesit boyutlarini bul
            dims = section_dims.get(section_name, {})
            width = _safe_float(dims.get("width_m") or dims.get("b_min_m"), 0.3)
            depth = _safe_float(dims.get("depth_m") or dims.get("b_max_m"), 0.3)

            # Minimum degerler
            if width < 0.1:
                width = 0.3
            if depth < 0.1:
                depth = 0.3

            # Net yukseklik
            clear_height = story_heights.get(story, 3.0)

            col_geom = ColumnGeometry(
                label=label,
                story=story,
                section_name=section_name,
                width_m=width,
                depth_m=depth,
                clear_height_m=clear_height,
            )
            columns.append(col_geom)

        self._columns = columns
        return columns

    def resolve_forces(self) -> Dict[str, ColumnForces]:
        """Envelope'tan kolon kuvvetlerini coz"""
        forces_map = self.ctx.envelopes.get("column_forces_map", {})

        for label, env_data in forces_map.items():
            cf = ColumnForces(
                label=label,
                N_kn=_safe_float(env_data.get("P_max")),
                Mx_knm=_safe_float(env_data.get("M3_max")),  # major
                My_knm=_safe_float(env_data.get("M2_max")),  # minor
                Vx_kn=_safe_float(env_data.get("V2_max")),
                Vy_kn=_safe_float(env_data.get("V3_max")),
                governing_combo=str(env_data.get("P_case", "") or ""),
                N_case=str(env_data.get("P_case", "") or ""),
                Mx_case=str(env_data.get("M3_case", "") or ""),
                My_case=str(env_data.get("M2_case", "") or ""),
                Vx_case=str(env_data.get("V2_case", "") or ""),
                Vy_case=str(env_data.get("V3_case", "") or ""),
            )
            self._forces[label] = cf

        return self._forces

    def resolve_rebar(self) -> Dict[str, ColumnRebar]:
        """
        Resolve column rebar from ModelContext.

        Priority:
        1. ETABS column_design_summary:
           uses as/baras/designsect/vmajrebar/vminrebar where available.
        2. Section-level column_rebar_defs:
           used mainly for tie/stirrup layout and as fallback longitudinal layout.
        3. Real/provided schedule:
           real_rebar_schedule / rebar_schedule / rebar_columns / column_rebar_schedule.
        4. Auto proposal from RebarSetBuilder.

        source:
        - etabs_design_summary
        - real_rebar
        - section_rebar_defs
        - default

        source=default is not real model rebar. It is an automatic proposal and must
        be reported as WARNING by checks.
        """
        from .rebar_set import RebarSetBuilder

        try:
            from ..rebar.real_rebar import normalize_real_rebar
        except Exception:
            normalize_real_rebar = None

        self._rebar = {}

        if not self._columns:
            self.resolve_columns()

        def _m2_to_mm2(value: Any) -> float:
            v = _safe_float(value, 0.0)
            # ETABS design summary fields are usually m2. If the value is small,
            # treat it as m2 and convert to mm2.
            if 0.0 < v < 100.0:
                return v * 1_000_000.0
            return v

        def _dia_from_bar_area_mm2(area_mm2: float) -> float:
            if area_mm2 <= 0:
                return 0.0
            raw_dia = math.sqrt(4.0 * area_mm2 / math.pi)
            common = [8, 10, 12, 14, 16, 18, 20, 22, 24, 25, 26, 28, 30, 32, 36, 40]
            return float(min(common, key=lambda d: abs(d - raw_dia)))

        def _total_bars_from_rect_dirs(n3: float, n2: float) -> int:
            n3_i = int(_safe_float(n3, 0))
            n2_i = int(_safe_float(n2, 0))
            if n3_i <= 0 or n2_i <= 0:
                return 0
            # ETABS rectangular layout counts bars on each face including corners.
            return max(0, 2 * n3_i + 2 * n2_i - 4)

        # ------------------------------------------------------------------
        # Section-level column rebar definitions.
        # Example from ETABS:
        # name, numbars3dir, numbars2dir, barsizelong, barsizeconf, spacingconf,
        # numcbars3, numcbars2
        # ------------------------------------------------------------------
        section_defs: Dict[str, Dict[str, Any]] = {}
        rebar_defs = self.ctx.design_metadata.get("column_rebar_defs")
        if rebar_defs is None:
            rebar_defs = self.ctx.tables.get("column_rebar_defs")

        if rebar_defs is not None and not getattr(rebar_defs, "empty", True):
            for _, row in rebar_defs.iterrows():
                sec = str(
                    _row_get_any(
                        row,
                        ["name", "section", "section_name", "designsect", "Label", "label"],
                        "",
                    )
                ).strip()
                if not sec:
                    continue

                n3 = _safe_float(_row_get_any(row, ["numbars3dir", "num_bars_3dir"], 0), 0)
                n2 = _safe_float(_row_get_any(row, ["numbars2dir", "num_bars_2dir"], 0), 0)
                n_total = _total_bars_from_rect_dirs(n3, n2)

                long_dia = _safe_float(
                    _row_get_any(row, ["barsizelong", "bar_diameter_mm", "bardiameter", "phi"], 0),
                    0,
                )
                conf_dia = _safe_float(
                    _row_get_any(row, ["barsizeconf", "stirrupdiameter", "tie_diameter_mm", "phi_tie"], 0),
                    0,
                )
                conf_spacing_raw = _safe_float(
                    _row_get_any(row, ["spacingconf", "stirrupspacing", "tie_spacing_mm"], 0),
                    0,
                )
                conf_spacing_mm = conf_spacing_raw * 1000.0 if 0 < conf_spacing_raw < 10 else conf_spacing_raw

                legs_1 = int(_safe_float(_row_get_any(row, ["numcbars3", "stirrup_legs_dir1", "tie_legs_dir1"], 2), 2))
                legs_2 = int(_safe_float(_row_get_any(row, ["numcbars2", "stirrup_legs_dir2", "tie_legs_dir2"], 2), 2))

                section_defs[sec] = {
                    "n_total": n_total,
                    "long_dia": long_dia,
                    "conf_dia": conf_dia,
                    "conf_spacing_mm": conf_spacing_mm,
                    "legs_1": legs_1,
                    "legs_2": legs_2,
                }

        # ------------------------------------------------------------------
        # 1) ETABS column design summary: per column design reinforcement.
        # Use governing/max As per column.
        # ------------------------------------------------------------------
        design_summary = self.ctx.design_metadata.get("column_design_summary")
        if design_summary is None:
            design_summary = self.ctx.tables.get("column_design_summary")

        if design_summary is not None and not getattr(design_summary, "empty", True):
            label_col = None
            for c in ["label", "Label", "column", "Column", "element_id", "Element"]:
                if c in design_summary.columns:
                    label_col = c
                    break

            if label_col:
                for col in self._columns:
                    try:
                        rows = design_summary[
                            design_summary[label_col].astype(str).str.strip() == str(col.label)
                        ]
                    except Exception:
                        rows = None

                    if rows is None or rows.empty:
                        continue

                    best_as_mm2 = 0.0
                    best_bar_area_mm2 = 0.0
                    best_section = col.section_name
                    best_row = None

                    for _, row in rows.iterrows():
                        as_mm2 = _m2_to_mm2(row.get("as"))
                        if as_mm2 <= 0:
                            as_mm2 = _m2_to_mm2(row.get("asmin"))
                        if as_mm2 > best_as_mm2:
                            best_as_mm2 = as_mm2
                            best_bar_area_mm2 = _m2_to_mm2(row.get("baras"))
                            best_section = str(row.get("designsect") or col.section_name)
                            best_row = row

                    if best_as_mm2 <= 0:
                        continue

                    if best_bar_area_mm2 > 0:
                        n_bars = max(1, int(round(best_as_mm2 / best_bar_area_mm2)))
                        bar_dia = _dia_from_bar_area_mm2(best_bar_area_mm2)
                    else:
                        n_bars, bar_dia, best_as_mm2, _rho_tmp = _choose_min_longitudinal_rebar(col.area_mm2)

                    sec_def = section_defs.get(best_section) or section_defs.get(col.section_name) or {}

                    cr = ColumnRebar(
                        label=col.label,
                        n_bars_total=n_bars,
                        bar_diameter_mm=bar_dia,
                        As_total_mm2=best_as_mm2,
                        rho=best_as_mm2 / col.area_mm2 * 100.0 if col.area_mm2 > 0 else 0.0,
                    )
                    setattr(cr, "source", "etabs_design_summary")

                    conf_dia = _safe_float(sec_def.get("conf_dia"), 0.0)
                    conf_spacing = _safe_float(sec_def.get("conf_spacing_mm"), 0.0)
                    legs_1 = int(_safe_float(sec_def.get("legs_1"), 2))
                    legs_2 = int(_safe_float(sec_def.get("legs_2"), 2))

                    if conf_dia > 0 and conf_spacing > 0:
                        cr.has_confinement_data = True
                        cr.stirrup_diameter_mm = conf_dia
                        cr.stirrup_spacing_mm = conf_spacing
                        cr.stirrup_legs_dir1 = legs_1
                        cr.stirrup_legs_dir2 = legs_2

                        area_one_leg = math.pi * conf_dia ** 2 / 4.0
                        cr.Ash_dir1_mm2 = area_one_leg * cr.stirrup_legs_dir1
                        cr.Ash_dir2_mm2 = area_one_leg * cr.stirrup_legs_dir2

                    self._rebar[col.label] = cr

        # ------------------------------------------------------------------
        # 2) Real/provided rebar schedule, if user supplies one.
        # This can override ETABS design summary because it represents provided rebar.
        # ------------------------------------------------------------------
        real_rows = []
        if normalize_real_rebar is not None:
            try:
                real_rows = normalize_real_rebar(self.ctx).get("COLUMN", [])
            except Exception:
                real_rows = []

        for rec in real_rows:
            label = str(rec.get("element_id") or "").strip()
            if not label:
                continue

            As_total = _safe_float(rec.get("as_provided_mm2"), 0.0)
            n_bars = int(_safe_float(rec.get("n_bars_total"), 0.0))
            bar_dia = _safe_float(rec.get("bar_diameter_mm"), 0.0)

            if As_total <= 0 and n_bars > 0 and bar_dia > 0:
                As_total = n_bars * math.pi * (bar_dia ** 2) / 4.0

            if As_total <= 0:
                continue

            col = next((c for c in self._columns if c.label == label), None)
            if not col:
                continue

            cr = ColumnRebar(
                label=label,
                n_bars_total=n_bars,
                bar_diameter_mm=bar_dia,
                As_total_mm2=As_total,
                rho=As_total / col.area_mm2 * 100.0 if col.area_mm2 > 0 else 0.0,
            )
            setattr(cr, "source", "real_rebar")

            tie_dia = _safe_float(rec.get("tie_diameter_mm"), 0.0)
            tie_s = _safe_float(rec.get("tie_spacing_end_mm"), 0.0)
            if tie_s <= 0:
                tie_s = _safe_float(rec.get("tie_spacing_mid_mm"), 0.0)

            legs_1 = int(_safe_float(rec.get("tie_leg_count_dir1"), 2.0))
            legs_2 = int(_safe_float(rec.get("tie_leg_count_dir2"), 2.0))

            if tie_dia > 0 and tie_s > 0:
                cr.has_confinement_data = True
                cr.stirrup_diameter_mm = tie_dia
                cr.stirrup_spacing_mm = tie_s
                cr.stirrup_legs_dir1 = legs_1
                cr.stirrup_legs_dir2 = legs_2

                area_one_leg = math.pi * tie_dia ** 2 / 4.0
                cr.Ash_dir1_mm2 = area_one_leg * cr.stirrup_legs_dir1
                cr.Ash_dir2_mm2 = area_one_leg * cr.stirrup_legs_dir2

            self._rebar[label] = cr

        # ------------------------------------------------------------------
        # 3) Section-level fallback if no design summary row exists.
        # ------------------------------------------------------------------
        for col in self._columns:
            if col.label in self._rebar:
                continue

            sec_def = section_defs.get(col.section_name)
            if not sec_def:
                continue

            n_bars = int(_safe_float(sec_def.get("n_total"), 0))
            bar_dia = _safe_float(sec_def.get("long_dia"), 0.0)
            if n_bars <= 0 or bar_dia <= 0:
                continue

            As_total = n_bars * math.pi * (bar_dia ** 2) / 4.0

            cr = ColumnRebar(
                label=col.label,
                n_bars_total=n_bars,
                bar_diameter_mm=bar_dia,
                As_total_mm2=As_total,
                rho=As_total / col.area_mm2 * 100.0 if col.area_mm2 > 0 else 0.0,
            )
            setattr(cr, "source", "section_rebar_defs")

            conf_dia = _safe_float(sec_def.get("conf_dia"), 0.0)
            conf_spacing = _safe_float(sec_def.get("conf_spacing_mm"), 0.0)
            legs_1 = int(_safe_float(sec_def.get("legs_1"), 2))
            legs_2 = int(_safe_float(sec_def.get("legs_2"), 2))

            if conf_dia > 0 and conf_spacing > 0:
                cr.has_confinement_data = True
                cr.stirrup_diameter_mm = conf_dia
                cr.stirrup_spacing_mm = conf_spacing
                cr.stirrup_legs_dir1 = legs_1
                cr.stirrup_legs_dir2 = legs_2

                area_one_leg = math.pi * conf_dia ** 2 / 4.0
                cr.Ash_dir1_mm2 = area_one_leg * cr.stirrup_legs_dir1
                cr.Ash_dir2_mm2 = area_one_leg * cr.stirrup_legs_dir2

            self._rebar[col.label] = cr

        # ------------------------------------------------------------------
        # 4) Auto proposal for missing columns.
        # ------------------------------------------------------------------
        for col in self._columns:
            if col.label in self._rebar:
                continue

            rs = (
                RebarSetBuilder(
                    column_label=col.label,
                    section_name=col.section_name,
                    width_m=col.width_m,
                    depth_m=col.depth_m,
                )
                .build()
            )

            n_bars = rs.longitudinal.n_bars
            bar_dia = rs.longitudinal.diameter_mm
            As_total = rs.As_total_mm2
            rho = rs.rho_pct

            if n_bars < 6 or bar_dia < 14 or rho < 1.0:
                n_bars, bar_dia, As_total, rho = _choose_min_longitudinal_rebar(col.area_mm2)

            cr = ColumnRebar(
                label=col.label,
                n_bars_total=n_bars,
                bar_diameter_mm=bar_dia,
                As_total_mm2=As_total,
                rho=rho,
                has_confinement_data=True,
                stirrup_diameter_mm=rs.confinement.stirrup_diameter_mm,
                stirrup_spacing_mm=rs.confinement.stirrup_spacing_mm,
                stirrup_legs_dir1=rs.confinement.stirrup_legs_dir1,
                stirrup_legs_dir2=rs.confinement.stirrup_legs_dir2,
                Ash_dir1_mm2=rs.confinement.Ash_dir1_mm2,
                Ash_dir2_mm2=rs.confinement.Ash_dir2_mm2,
            )
            setattr(cr, "source", "default")
            self._rebar[col.label] = cr

        return self._rebar

    # -------------------------------------------------------------------------
    # CHECKS
    # -------------------------------------------------------------------------

    def check_geometry(self, col: ColumnGeometry) -> ColumnCheckResult:
        """
        TBDY 2018 Madde 7.3.1 - Kolon minimum boyut kontrolu

        Yuksek suneklikli kolonlar:
        - Minimum kenar: 300 mm
        - Kesit alani: en az 75000 mm2
        - b/h orani: en az 0.4
        """
        b_min = col.b_min_mm
        area = col.area_mm2
        ratio = min(col.width_m, col.depth_m) / max(col.width_m, col.depth_m)

        issues = []

        if b_min < 300:
            issues.append(f"min kenar {b_min}mm < 300mm")

        if area < 75000:
            issues.append(f"alan {area:.0f}mm2 < 75000mm2")

        if ratio < 0.4:
            issues.append(f"b/h={ratio:.2f} < 0.4")

        if issues:
            return ColumnCheckResult(
                check_name="geometry",
                status="FAIL",
                ratio=0.0,
                value=b_min,
                limit=300,
                unit="mm",
                message="; ".join(issues),
                tbdy_ref="TBDY 2018 7.3.1",
            )

        return ColumnCheckResult(
            check_name="geometry",
            status="OK",
            ratio=1.0,
            value=b_min,
            limit=300,
            unit="mm",
            message=f"Geometri uygun (b_min={b_min}mm, A={area:.0f}mm2)",
            tbdy_ref="TBDY 2018 7.3.1",
        )

    def check_axial(self, col: ColumnGeometry, forces: ColumnForces,
                    mat: MaterialSet) -> ColumnCheckResult:
        """
        TBDY 2018 Madde 7.3.2 - Eksenel yuk limiti

        Nd <= 0.40 * Ac * fcd (yuksek suneklik)
        Nd <= 0.60 * Ac * fcd (normal suneklik - burada 0.40 kullaniyoruz)
        """
        if mat is None:
            return ColumnCheckResult(
                check_name="axial",
                status="NO_DATA",
                message="Malzeme bilgisi yok",
                tbdy_ref="TBDY 2018 7.3.2",
            )

        ratio, N_limit = _compute_axial_capacity_ratio(
            forces.N_kn, col.area_m2, mat.fcd
        )

        if ratio > 1.0:
            return ColumnCheckResult(
                check_name="axial",
                status="FAIL",
                ratio=ratio,
                value=abs(forces.N_kn),
                limit=N_limit,
                unit="kN",
                message=f"Nd={abs(forces.N_kn):.0f}kN > 0.40*Ac*fcd={N_limit:.0f}kN (ratio={ratio:.2f})",
                tbdy_ref="TBDY 2018 7.3.2",
            )

        return ColumnCheckResult(
            check_name="axial",
            status="OK",
            ratio=ratio,
            value=abs(forces.N_kn),
            limit=N_limit,
            unit="kN",
            message=f"Nd={abs(forces.N_kn):.0f}kN <= 0.40*Ac*fcd={N_limit:.0f}kN (ratio={ratio:.2f})",
            tbdy_ref="TBDY 2018 7.3.2",
        )

    def check_pmm(
            self,
            col: ColumnGeometry,
            forces: Optional[ColumnForces] = None,
            rebar: Optional[ColumnRebar] = None,
            mat: Optional[MaterialSet] = None,
    ) -> ColumnCheckResult:
        """
        TBDY 2018 Â§7.3.3 - Kolon PMM kontrolu.

        Oncelik:
        1. ETABS column_design_summary PMM ratio.
        2. Kuvvet + malzeme + donati varsa PMMChecker ile bagimsiz yaklasik hesap.
        3. Otomatik oneri donati kullanilmissa OK yerine WARNING.
        4. Veri eksikse NO_DATA.
        """
        from .pmm_check import PMMChecker

        design_summary = self.ctx.design_metadata.get("column_design_summary")

        if design_summary is not None and not getattr(design_summary, "empty", True):
            label_cols = ["label", "Label", "UniqueName", "Unique Name", "Frame", "Column", "Element"]
            ratio_cols = ["pm_ratio", "pmm_ratio", "PMM Ratio", "PMRatio", "Ratio", "DC Ratio"]
            case_cols = ["case", "combo", "design_case", "DesignCase", "OutputCase", "PMMCombo"]

            col_rows = None
            for label_col in label_cols:
                if label_col in design_summary.columns:
                    col_rows = design_summary[
                        design_summary.apply(lambda r: str(r.get(label_col, "")).strip() == col.label, axis=1)
                    ]
                    if col_rows is not None and not col_rows.empty:
                        break

            if col_rows is not None and not col_rows.empty:
                row = col_rows.iloc[0]
                ratio = _safe_float(_row_get_any(row, ratio_cols, 0.0), 0.0)
                if ratio > 0:
                    status = "OK" if ratio <= 1.0 else "FAIL"
                    case = str(_row_get_any(row, case_cols, "") or "").strip()
                    return ColumnCheckResult(
                        check_name="pmm",
                        status=status,
                        ratio=ratio,
                        value=ratio,
                        limit=1.0,
                        unit="ratio",
                        message=f"PMM ratio={ratio:.3f} (ETABS design summary, case={case})",
                        tbdy_ref="TBDY 2018 7.3.3",
                        governing_combo=case or None,
                    )

        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if not self._columns:
            self.resolve_columns()

        if forces is None:
            if not self._forces:
                self.resolve_forces()
            forces = self._forces.get(col.label)

        if rebar is None:
            if not self._rebar:
                self.resolve_rebar()
            rebar = self._rebar.get(col.label)

        if not forces:
            return ColumnCheckResult(
                check_name="pmm",
                status="NO_DATA",
                ratio=0.0,
                message="PMM icin kuvvet zarfi yok",
                tbdy_ref="TBDY 2018 7.3.3",
            )

        if not mat:
            return ColumnCheckResult(
                check_name="pmm",
                status="NO_DATA",
                ratio=0.0,
                message="PMM icin malzeme verisi yok",
                tbdy_ref="TBDY 2018 7.3.3",
            )

        if not rebar or rebar.As_total_mm2 <= 0 or rebar.n_bars_total <= 0:
            return ColumnCheckResult(
                check_name="pmm",
                status="NO_DATA",
                ratio=0.0,
                message="PMM icin boyuna donati verisi yok",
                tbdy_ref="TBDY 2018 7.3.3",
            )

        pmm = PMMChecker().check(
            column_label=col.label,
            Nd_kn=forces.N_kn,
            Mxd_knm=forces.Mx_knm,
            Myd_knm=forces.My_knm,
            width_m=col.width_m,
            depth_m=col.depth_m,
            fcd_mpa=mat.fcd,
            fyd_mpa=mat.fyd,
            As_total_mm2=rebar.As_total_mm2,
            n_bars=rebar.n_bars_total,
        )

        status = pmm.status
        source = getattr(rebar, "source", "unknown")

        if source == "default" and status == "OK":
            status = "WARNING"

        source_msg = (
            "minimum oneri donatisi ile yaklasik PMM"
            if source == "default"
            else "mevcut donati ile bagimsiz PMM"
        )

        return ColumnCheckResult(
            check_name="pmm",
            status=status,
            ratio=pmm.governing_ratio,
            value=pmm.governing_ratio,
            limit=1.0,
            unit="ratio",
            message=f"{pmm.message} | {source_msg} | source={pmm.source}",
            tbdy_ref="TBDY 2018 7.3.3 / TS500 PMM",
        )

    def check_shear(self, col: ColumnGeometry, forces: ColumnForces,
                    mat: MaterialSet, rebar: ColumnRebar) -> ColumnCheckResult:
        """
        TBDY 2018 Madde 7.3.7 - Kolon kesme guvenligi

        Ve <= Vr
        Vr = Vc + Vw
        """
        if mat is None:
            return ColumnCheckResult(
                check_name="shear",
                status="NO_DATA",
                message="Malzeme bilgisi yok",
                tbdy_ref="TBDY 2018 7.3.7",
            )

        # Maksimum kesme kuvveti
        Ve = max(abs(forces.Vx_kn), abs(forces.Vy_kn))

        # Beton katkisi
        Vc, Vc_max = _compute_shear_strength_concrete(
            forces.N_kn, col.area_m2, mat.fcd, mat.fck,  # fck_mpa eklendi
            col.effective_depth_m, col.width_m
        )

        # Etriye katkisi
        Vw = 0.0
        if rebar and rebar.has_confinement_data and rebar.stirrup_spacing_mm > 0:
            Asw = rebar.Ash_dir1_mm2  # kesme yonundeki etriye alani
            Vw = _compute_shear_strength_stirrups(
                Asw, rebar.stirrup_spacing_mm, col.effective_depth_m, mat.fywd
            )

        Vr = Vc + Vw
        Vr = min(Vr, Vc_max)  # ust sinir

        ratio = Ve / Vr if Vr > 0 else 999

        if ratio > 1.0:
            return ColumnCheckResult(
                check_name="shear",
                status="FAIL",
                ratio=ratio,
                value=Ve,
                limit=Vr,
                unit="kN",
                message=f"Ve={Ve:.0f}kN > Vr={Vr:.0f}kN (Vc={Vc:.0f}, Vw={Vw:.0f})",
                tbdy_ref="TBDY 2018 7.3.7",
            )

        return ColumnCheckResult(
            check_name="shear",
            status="OK",
            ratio=ratio,
            value=Ve,
            limit=Vr,
            unit="kN",
            message=f"Ve={Ve:.0f}kN <= Vr={Vr:.0f}kN (Vc={Vc:.0f}, Vw={Vw:.0f})",
            tbdy_ref="TBDY 2018 7.3.7",
        )

    def check_confinement(
            self,
            col: ColumnGeometry,
            mat: Optional[MaterialSet] = None,
            rebar: Optional[ColumnRebar] = None,
    ) -> ColumnCheckResult:
        """
        TBDY 2018 7.3.4 - Column confinement transverse reinforcement check.

        Real ETABS/user tie data:
          OK / FAIL

        Auto/default proposal:
          WARNING, because it is not real model reinforcement.
        """
        if mat is None:
            if self._materials is None:
                self.resolve_materials()
            mat = self._materials

        if rebar is None:
            if not self._rebar:
                self.resolve_rebar()
            rebar = self._rebar.get(col.label)

        if not mat:
            return ColumnCheckResult(
                "confinement",
                "NO_DATA",
                message="Material data is missing",
                tbdy_ref="TBDY 2018 7.3.4",
            )

        if not rebar:
            return ColumnCheckResult(
                "confinement",
                "NO_DATA",
                message="Confinement rebar data is missing",
                tbdy_ref="TBDY 2018 7.3.4",
            )

        if not rebar.has_confinement_data:
            return ColumnCheckResult(
                "confinement",
                "NO_DATA",
                message="Confinement tie/stirrup data is missing",
                tbdy_ref="TBDY 2018 7.3.4",
            )

        b_mm = col.width_m * 1000.0
        h_mm = col.depth_m * 1000.0
        cover_mm = 40.0

        bk_mm = min(b_mm, h_mm) - 2.0 * cover_mm
        Ack_mm2 = max((b_mm - 2.0 * cover_mm) * (h_mm - 2.0 * cover_mm), 0.0)

        s_mm = rebar.stirrup_spacing_mm if rebar.stirrup_spacing_mm > 0 else 100.0

        Ash_req_1 = _compute_confinement_required_ash(
            s_mm=s_mm,
            bk_mm=bk_mm,
            fck_mpa=mat.fck,
            fywk_mpa=mat.fyk,
            Ac_mm2=col.area_mm2,
            Ack_mm2=Ack_mm2,
        )
        Ash_req_2 = _compute_confinement_min_ash(
            s_mm=s_mm,
            bk_mm=bk_mm,
            fck_mpa=mat.fck,
            fywk_mpa=mat.fyk,
        )

        Ash_req = max(Ash_req_1, Ash_req_2)
        Ash_prov = min(rebar.Ash_dir1_mm2, rebar.Ash_dir2_mm2)
        ratio = Ash_req / Ash_prov if Ash_prov > 0 else 999.0

        source = str(getattr(rebar, "source", "unknown"))

        if source == "default":
            dia, legs, ash = _choose_confinement_proposal(Ash_req)
            return ColumnCheckResult(
                check_name="confinement",
                status="WARNING",
                ratio=ratio,
                value=ash,
                limit=Ash_req,
                unit="mm2",
                message=(
                    f"Confinement tie data is not real ETABS/user rebar. "
                    f"Auto proposal: {legs} legs Phi{int(dia)}, "
                    f"Ash~{ash:.0f}mm2, required~{Ash_req:.0f}mm2. "
                    f"source=auto_confinement"
                ),
                tbdy_ref="TBDY 2018 7.3.4 / 7.3.5",
            )

        if Ash_prov >= Ash_req:
            return ColumnCheckResult(
                check_name="confinement",
                status="OK",
                ratio=ratio,
                value=Ash_prov,
                limit=Ash_req,
                unit="mm2",
                message=(
                    f"Confinement OK: Ash={Ash_prov:.0f}mm2 >= required={Ash_req:.0f}mm2. "
                    f"ties=Phi{int(round(rebar.stirrup_diameter_mm))}@{s_mm:.0f}mm, "
                    f"legs={rebar.stirrup_legs_dir1}/{rebar.stirrup_legs_dir2}, source={source}"
                ),
                tbdy_ref="TBDY 2018 7.3.4",
            )

        dia, legs, ash = _choose_confinement_proposal(Ash_req)

        return ColumnCheckResult(
            check_name="confinement",
            status="FAIL",
            ratio=ratio,
            value=Ash_prov,
            limit=Ash_req,
            unit="mm2",
            message=(
                f"Confinement FAIL: Ash={Ash_prov:.0f}mm2 < required={Ash_req:.0f}mm2. "
                f"provided=Phi{int(round(rebar.stirrup_diameter_mm))}@{s_mm:.0f}mm, "
                f"legs={rebar.stirrup_legs_dir1}/{rebar.stirrup_legs_dir2}, source={source}. "
                f"Proposal: use at least {legs} legs Phi{int(dia)} "
                f"or revise spacing/tie layout to provide Ash>={Ash_req:.0f}mm2."
            ),
            tbdy_ref="TBDY 2018 7.3.4",
        )

    def check_capacity_hierarchy(self, col: ColumnGeometry) -> ColumnCheckResult:
        """
        TBDY 2018 §7.3.5 - Guclu kolon / zayif kiris kontrolu.

        Topoloji formati farkli gelebilir:
        - dict: {"C1": ["B1", "B2"]}
        - list: [{"column": "C1", "beams": [...]}, ...]
        - list: [("C1", "B1"), ...]
        Format cozulemezse DESIGN_LEVEL yapilamaz ve WARNING doner.
        """
        raw_map = self.ctx.topology.get("column_beam_map", {})
        connected_beams = []

        if isinstance(raw_map, dict):
            connected_beams = raw_map.get(col.label, []) or []
        elif isinstance(raw_map, list):
            for item in raw_map:
                if isinstance(item, dict):
                    column_label = (
                        item.get("column")
                        or item.get("column_label")
                        or item.get("Column")
                        or item.get("frame")
                        or item.get("Frame")
                    )
                    if str(column_label) == col.label:
                        beams = (
                            item.get("beams")
                            or item.get("connected_beams")
                            or item.get("beam_labels")
                            or item.get("Beam")
                            or []
                        )
                        if isinstance(beams, list):
                            connected_beams.extend(beams)
                        elif beams:
                            connected_beams.append(beams)
                elif isinstance(item, (tuple, list)) and len(item) >= 2:
                    if str(item[0]) == col.label:
                        connected_beams.append(item[1])

        if not connected_beams:
            return ColumnCheckResult(
                check_name="capacity_hierarchy",
                status="WARNING",
                ratio=0.0,
                value=0.0,
                limit=1.0,
                unit="",
                message=(
                    f"{col.label} icin bagli kiris/topoloji verisi yok veya cozulemedi. "
                    f"Guclu kolon-zayif kiris kontrolu DESIGN_LEVEL yapilamadi; "
                    f"Beam/Topology sprint sonrasi tekrar degerlendirilmeli. "
                    f"source=screening_fallback"
                ),
                tbdy_ref="TBDY 2018 7.3.5 / 7.4.3",
            )

        return ColumnCheckResult(
            check_name="capacity_hierarchy",
            status="WARNING",
            ratio=0.0,
            value=0.0,
            limit=1.0,
            unit="",
            message=(
                f"{col.label} icin bagli kiris bulundu ({len(connected_beams)} adet) ancak "
                f"kiris/kolon moment kapasitesi henuz resolver seviyesinde hazir degil. "
                f"source=screening_fallback"
            ),
            tbdy_ref="TBDY 2018 7.3.5",
        )

    # -------------------------------------------------------------------------
    # MAIN
    # -------------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """
        Komple kolon tasarim paketi.

        Aggregate politika:
        - FAIL varsa FAIL
        - WARNING varsa WARNING
        - NO_DATA varsa WARNING
        - hepsi OK ise OK
        """
        self.resolve_materials()
        self.resolve_columns()
        self.resolve_forces()
        self.resolve_rebar()

        outputs: List[ColumnDesignOutput] = []

        for col in self._columns:
            out = ColumnDesignOutput(
                label=col.label,
                story=col.story,
                section=col.section_name,
                materials=self._materials,
                geometry=col,
                forces=self._forces.get(col.label),
                rebar=self._rebar.get(col.label),
            )

            checks: Dict[str, ColumnCheckResult] = {}

            checks["geometry"] = self.check_geometry(col)

            if out.forces:
                checks["axial"] = self.check_axial(col, out.forces, self._materials)
            else:
                checks["axial"] = ColumnCheckResult(
                    "axial",
                    "NO_DATA",
                    message="Kuvvet verisi yok",
                    tbdy_ref="TBDY 2018 7.3.2",
                )

            checks["pmm"] = self.check_pmm(col, out.forces, out.rebar, self._materials)

            if out.forces and self._materials:
                checks["shear"] = self.check_shear(col, out.forces, self._materials, out.rebar)
            else:
                checks["shear"] = ColumnCheckResult(
                    "shear",
                    "NO_DATA",
                    message="Kuvvet/malzeme verisi yok",
                    tbdy_ref="TBDY 2018 7.3.7",
                )

            checks["confinement"] = self.check_confinement(col, self._materials, out.rebar)
            checks["capacity_hierarchy"] = self.check_capacity_hierarchy(col)

            out.checks = checks

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

            ratios = [
                (name, c.ratio)
                for name, c in checks.items()
                if c.ratio > 0
            ]
            if ratios:
                out.governing_check, out.governing_ratio = max(ratios, key=lambda x: x[1])

            outputs.append(out)

        self._outputs = outputs

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
            "total_columns": len(outputs),
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
    def _output_to_dict(self, out: ColumnDesignOutput) -> Dict[str, Any]:
        """ColumnDesignOutput → dict"""

        def _check_to_dict(name: str, c: Any) -> Dict[str, Any]:
            payload: Dict[str, Any] = {
                "status": c.status,
                "ratio": c.ratio,
                "value": c.value,
                "limit": c.limit,
                "unit": c.unit,
                "message": c.message,
                "tbdy_ref": c.tbdy_ref,
            }


            if name == "axial":
                governing_combo = (
                    getattr(out.forces, "N_case", None)
                    or out.forces.governing_combo
                    if out.forces
                    else None
                )
                payload["governing_combo"] = governing_combo or None
                payload["combo_family"] = None
                payload["evidence"] = {
                    "force": "N_kn",
                    "N_kn": out.forces.N_kn if out.forces else None,
                    "limit": c.limit,
                    "ratio": c.ratio,
                    "governing_combo": governing_combo or None,
                    "component_case": governing_combo or None,
                }


            elif name == "pmm":
                governing_combo = getattr(c, "governing_combo", None)
                payload["governing_combo"] = governing_combo or None
                payload["combo_family"] = None
                payload["evidence"] = {
                    "ratio": c.ratio,
                    "value": c.value,
                    "limit": c.limit,
                    "source": "column_pmm",
                    "note": "PMM governing case preserved when explicitly provided",
                    "governing_combo": governing_combo or None,
                }

            elif name == "shear":
                payload["governing_combo"] = None
                payload["combo_family"] = None
                payload["evidence"] = {
                    "force": "max(abs(Vx_kn), abs(Vy_kn))",
                    "Vx_kn": out.forces.Vx_kn if out.forces else None,
                    "Vy_kn": out.forces.Vy_kn if out.forces else None,
                    "Vx_case": getattr(out.forces, "Vx_case", None) if out.forces else None,
                    "Vy_case": getattr(out.forces, "Vy_case", None) if out.forces else None,
                    "value": c.value,
                    "limit": c.limit,
                    "ratio": c.ratio,
                }

            return payload

        return {
            "label": out.label,
            "story": out.story,
            "section": out.section,
            "status": out.status,
            "geometry": {
                "width_m": out.geometry.width_m if out.geometry else None,
                "depth_m": out.geometry.depth_m if out.geometry else None,
                "area_m2": out.geometry.area_m2 if out.geometry else None,
            } if out.geometry else None,
            "forces": {
                "N_kn": out.forces.N_kn if out.forces else None,
                "Mx_knm": out.forces.Mx_knm if out.forces else None,
                "My_knm": out.forces.My_knm if out.forces else None,
                "Vx_kn": out.forces.Vx_kn if out.forces else None,
                "Vy_kn": out.forces.Vy_kn if out.forces else None,
            } if out.forces else None,
            "rebar": {
                "rho_pct": out.rebar.rho if out.rebar else None,
                "As_total_mm2": out.rebar.As_total_mm2 if out.rebar else None,
                "has_confinement_data": out.rebar.has_confinement_data if out.rebar else False,
            } if out.rebar else None,
            "checks": {
                name: _check_to_dict(name, c)
                for name, c in out.checks.items()
            },
            "governing_check": out.governing_check,
            "governing_ratio": out.governing_ratio,
        }

# =============================================================================
# CONVENIENCE
# =============================================================================

def run_column_design(ctx: Any) -> Dict[str, Any]:
    """
    Convenience function: context'ten kolon tasarimini calistir.

    Args:
        ctx: ModelContext

    Returns:
        Dict: Tasarim sonuclari
    """
    module = ColumnDesignModule(ctx)
    return module.run()

# === SPRINT32_COLUMN_PROVIDED_REBAR_BEGIN ===
# Provided/final column rebar priority layer.
#
# Priority:
#   1. ctx.tables["provided_rebar"] / user_rebar_schedule COLUMN records
#   2. existing ColumnDesignModule.resolve_rebar() fallback
#
# This wrapper does not connect to ETABS. It only reads ModelContext.
# It is fail-safe: if provided rebar is missing or malformed, original behavior remains.

def _sprint32_col_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        v = float(str(value).replace(",", "."))
        if v != v:
            return default
        return v
    except Exception:
        return default


def _sprint32_col_safe_int(value, default=0):
    try:
        return int(round(_sprint32_col_safe_float(value, float(default))))
    except Exception:
        return default


def _sprint32_col_key(story, label):
    return f"{str(story or '').strip()}|{str(label or '').strip()}"


def _sprint32_bar_area_mm2(dia_mm):
    import math
    d = _sprint32_col_safe_float(dia_mm, 0.0)
    if d <= 0:
        return 0.0
    return math.pi * d * d / 4.0


def _sprint32_make_column_rebar_object(rec):
    """
    Build a ColumnRebar-compatible object without assuming exact constructor fields.
    """
    import inspect
    from types import SimpleNamespace

    label = str(getattr(rec, "label", "") or "").strip()
    story = str(getattr(rec, "story", "") or "").strip()
    source = str(getattr(rec, "source", "") or "provided_rebar")

    as_total = _sprint32_col_safe_float(getattr(rec, "as_total_mm2", None), 0.0)
    bar_count = _sprint32_col_safe_int(getattr(rec, "bar_count", None), 0)
    bar_dia = _sprint32_col_safe_float(getattr(rec, "bar_diameter_mm", None), 0.0)

    if as_total <= 0 and bar_count > 0 and bar_dia > 0:
        as_total = bar_count * _sprint32_bar_area_mm2(bar_dia)

    tie_dia = _sprint32_col_safe_float(getattr(rec, "stirrup_diameter_mm", None), 0.0)
    spacing = _sprint32_col_safe_float(getattr(rec, "stirrup_spacing_mm", None), 0.0)

    legs_x = _sprint32_col_safe_int(
        getattr(rec, "stirrup_legs_x", None)
        or getattr(rec, "stirrup_legs", None),
        0,
    )
    legs_y = _sprint32_col_safe_int(
        getattr(rec, "stirrup_legs_y", None)
        or getattr(rec, "stirrup_legs", None),
        0,
    )

    ash_x = _sprint32_col_safe_float(getattr(rec, "ash_x_mm2", None), 0.0)
    ash_y = _sprint32_col_safe_float(getattr(rec, "ash_y_mm2", None), 0.0)

    # If Ash is not explicitly provided, calculate from tie diameter and leg count.
    # Existing confinement output previously used Ash ~= legs * area(phi).
    if ash_x <= 0 and legs_x > 0 and tie_dia > 0:
        ash_x = legs_x * _sprint32_bar_area_mm2(tie_dia)
    if ash_y <= 0 and legs_y > 0 and tie_dia > 0:
        ash_y = legs_y * _sprint32_bar_area_mm2(tie_dia)

    missing = []
    if as_total <= 0:
        missing.append("longitudinal As")
    if bar_count <= 0:
        missing.append("bar count")
    if bar_dia <= 0:
        missing.append("bar diameter")
    if tie_dia <= 0:
        missing.append("tie diameter")
    if spacing <= 0:
        missing.append("tie spacing")
    if legs_x <= 0 and legs_y <= 0:
        missing.append("tie legs")

    status = "OK" if not missing else "WARNING"
    note = "final provided column rebar" if not missing else "provided column rebar missing: " + ", ".join(missing)

    values = {
        "label": label,
        "element_id": label,
        "story": story,

        "As_total_mm2": as_total,
        "as_total_mm2": as_total,
        "longitudinal_area_mm2": as_total,
        "As_longitudinal_mm2": as_total,

        "bar_count": bar_count,
        "n_bars": bar_count,
        "bar_diameter_mm": bar_dia,
        "main_bar_diameter_mm": bar_dia,

        "stirrup_diameter_mm": tie_dia,
        "tie_diameter_mm": tie_dia,
        "stirrup_spacing_mm": spacing,
        "tie_spacing_mm": spacing,

        "stirrup_legs": max(legs_x, legs_y),
        "stirrup_leg_count": max(legs_x, legs_y),
        "stirrup_legs_x": legs_x,
        "stirrup_legs_y": legs_y,
        "stirrup_legs_dir1": legs_x,
        "stirrup_legs_dir2": legs_y,

        "Ash_x_mm2": ash_x,
        "Ash_y_mm2": ash_y,
        "ash_x_mm2": ash_x,
        "ash_y_mm2": ash_y,
        "Ash_dir1_mm2": ash_x,
        "Ash_dir2_mm2": ash_y,

        "has_stirrup_data": tie_dia > 0 and spacing > 0 and (legs_x > 0 or legs_y > 0),
        "source": source,
        "status": status,
        "note": note,
    }

    cls = globals().get("ColumnRebar")

    obj = None

    if cls is not None:
        try:
            sig = inspect.signature(cls)
            kwargs = {}

            for name, param in sig.parameters.items():
                if name == "self":
                    continue

                if name in values:
                    kwargs[name] = values[name]
                elif param.default is inspect._empty:
                    lname = name.lower()

                    if "label" in lname or "element" in lname:
                        kwargs[name] = label
                    elif "story" in lname:
                        kwargs[name] = story
                    elif "source" in lname:
                        kwargs[name] = source
                    elif "status" in lname:
                        kwargs[name] = status
                    elif "note" in lname or "message" in lname:
                        kwargs[name] = note
                    elif "count" in lname or "legs" in lname or lname.startswith("n"):
                        kwargs[name] = 0
                    else:
                        kwargs[name] = 0.0

            obj = cls(**kwargs)
        except Exception:
            obj = None

    if obj is None:
        obj = SimpleNamespace()

    for k, v in values.items():
        try:
            setattr(obj, k, v)
        except Exception:
            pass

    return obj


def _sprint32_apply_provided_column_rebar(self):
    try:
        from tbdy_engine.design.rebar.provided_rebar import ProvidedRebarResolver
    except Exception:
        return

    try:
        provided = ProvidedRebarResolver(self.ctx).resolve_columns()
    except Exception:
        return

    if not provided:
        return

    if not hasattr(self, "_rebar") or self._rebar is None:
        self._rebar = {}

    seen = set()

    for _, rec in provided.items():
        label = str(getattr(rec, "label", "") or "").strip()
        story = str(getattr(rec, "story", "") or "").strip()

        if not label:
            continue

        key = _sprint32_col_key(story, label)

        # Avoid processing story|label record and label alias twice.
        if key in seen:
            continue
        seen.add(key)

        item = _sprint32_make_column_rebar_object(rec)

        # Provided/final rebar must override fallback/default/design-summary data.
        self._rebar[key] = item
        self._rebar[label] = item


try:
    _sprint32_original_column_resolve_rebar = ColumnDesignModule.resolve_rebar

    def _sprint32_column_resolve_rebar_with_provided(self, *args, **kwargs):
        result = _sprint32_original_column_resolve_rebar(self, *args, **kwargs)

        try:
            _sprint32_apply_provided_column_rebar(self)
        except Exception:
            # Fail-safe: never break original column design because of provided layer.
            pass

        return getattr(self, "_rebar", result)

    ColumnDesignModule.resolve_rebar = _sprint32_column_resolve_rebar_with_provided
except Exception:
    pass
# === SPRINT32_COLUMN_PROVIDED_REBAR_END ===
