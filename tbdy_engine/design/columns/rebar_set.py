"""
tbdy/design_engine/modules/rebar_set.py

Kolon donati seti tanimlama ve cozumleme modulu.
Minimum donati default degerleri TBDY 2018'e gore.
Genisletilebilir: kullanici override, ETABS okuma, optimizasyon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import json

# =============================================================================
# DONATI CAPI KUTUPHANESI
# =============================================================================

# Standart donati caplari (mm) ve alanlari
BAR_LIBRARY: Dict[int, float] = {
    8: 50.3,
    10: 78.5,
    12: 113.1,
    14: 153.9,
    16: 201.1,
    18: 254.5,
    20: 314.2,
    22: 380.1,
    24: 452.4,
    26: 530.9,
    28: 615.8,
    30: 706.9,
    32: 804.2,
    36: 1017.9,
    40: 1256.6,
}

# Standart etriye caplari
STIRRUP_DIAMETERS = [8, 10, 12, 14, 16]


def get_bar_area(diameter_mm: float) -> float:
    """Donati alani (mm2)"""
    return math.pi * (diameter_mm ** 2) / 4


def find_nearest_bar(target_area_mm2: float) -> Tuple[int, float, float]:
    """
    Hedef alana en yakin standart donatiyi bul.

    Returns:
        (cap, alan, fark_yuzdesi)
    """
    best_dia = 12
    best_area = BAR_LIBRARY[12]
    best_diff = abs(best_area - target_area_mm2)

    for dia, area in BAR_LIBRARY.items():
        diff = abs(area - target_area_mm2)
        if diff < best_diff:
            best_diff = diff
            best_dia = dia
            best_area = area

    diff_pct = best_diff / target_area_mm2 * 100 if target_area_mm2 > 0 else 0
    return best_dia, best_area, diff_pct


# =============================================================================
# TBDY 2018 MINIMUM DONATI KURALLARI
# =============================================================================

@dataclass
class RebarRequirements:
    """
    TBDY 2018 kolon minimum donati gereksinimleri.

    Kaynak: TBDY 2018 Madde 7.3.2, 7.3.4
    """
    # Boyuna donati
    min_rho_pct: float = 1.0  # minimum donati orani (%)
    max_rho_pct: float = 4.0  # maksimum donati orani (%)
    min_bar_diameter_mm: int = 14  # minimum donati capi
    min_n_bars: int = 6  # dikdortgen kesitte minimum bar sayisi (4 kose + 2 ara)
    max_bar_spacing_mm: int = 300  # maksimum donati araligi

    # Etriye / Sargi donatisi
    min_stirrup_diameter_mm: int = 8  # minimum etriye capi
    max_stirrup_spacing_mm: int = 150  # maksimum etriye araligi (sargi bolgesi)
    stirrup_spacing_mid_mm: int = 200  # orta bolge etriye araligi
    sargi_zone_length_m: float = 0.5  # sargi bolgesi uzunlugu (m) - tipik lc

    # Ciroz
    min_cross_tie_diameter_mm: int = 8
    max_cross_tie_spacing_mm: int = 300

    # Paspayi
    clear_cover_mm: int = 40  # net paspayi (ic mekan)


# =============================================================================
# DONATI SETI
# =============================================================================

@dataclass
class LongitudinalRebar:
    """Boyuna donati tanimi"""
    diameter_mm: float
    n_bars: int
    arrangement: str = "uniform"  # uniform, bundled, custom

    @property
    def area_one_bar_mm2(self) -> float:
        return get_bar_area(self.diameter_mm)

    @property
    def area_total_mm2(self) -> float:
        return self.area_one_bar_mm2 * self.n_bars

    @property
    def label(self) -> str:
        return f"{self.n_bars}Phi{int(self.diameter_mm)}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diameter_mm": self.diameter_mm,
            "n_bars": self.n_bars,
            "arrangement": self.arrangement,
            "area_one_bar_mm2": round(self.area_one_bar_mm2, 1),
            "area_total_mm2": round(self.area_total_mm2, 1),
            "label": self.label,
        }


@dataclass
class ConfinementRebar:
    """Sargi donatisi tanimi (etriye + ciroz)"""
    stirrup_diameter_mm: float
    stirrup_spacing_mm: float
    stirrup_legs_dir1: int = 2  # b yonu etriye kollari
    stirrup_legs_dir2: int = 2  # h yonu etriye kollari
    cross_tie_diameter_mm: Optional[float] = None
    sargi_zone_spacing_mm: Optional[float] = None
    mid_zone_spacing_mm: Optional[float] = None

    @property
    def area_one_leg_mm2(self) -> float:
        return get_bar_area(self.stirrup_diameter_mm)

    @property
    def Ash_dir1_mm2(self) -> float:
        """b yonu sargi donatisi alani (tum kollar)"""
        return self.area_one_leg_mm2 * self.stirrup_legs_dir1

    @property
    def Ash_dir2_mm2(self) -> float:
        """h yonu sargi donatisi alani (tum kollar)"""
        return self.area_one_leg_mm2 * self.stirrup_legs_dir2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stirrup_diameter_mm": self.stirrup_diameter_mm,
            "stirrup_spacing_mm": self.stirrup_spacing_mm,
            "stirrup_legs_dir1": self.stirrup_legs_dir1,
            "stirrup_legs_dir2": self.stirrup_legs_dir2,
            "cross_tie_diameter_mm": self.cross_tie_diameter_mm,
            "sargi_zone_spacing_mm": self.sargi_zone_spacing_mm,
            "mid_zone_spacing_mm": self.mid_zone_spacing_mm,
            "area_one_leg_mm2": round(self.area_one_leg_mm2, 1),
            "Ash_dir1_mm2": round(self.Ash_dir1_mm2, 1),
            "Ash_dir2_mm2": round(self.Ash_dir2_mm2, 1),
        }


@dataclass
class RebarSet:
    """
    Tam kolon donati seti.

    Boyuna donati + sargi donatisi + minimum gereksinimler.
    """
    # Kimlik
    column_label: str
    section_name: str

    # Geometri referansi (hesaplama icin)
    width_m: float
    depth_m: float

    # Boyuna donati
    longitudinal: LongitudinalRebar

    # Sargi donatisi
    confinement: ConfinementRebar

    # Hesaplanan degerler
    rho_pct: float = 0.0  # donati orani (%)
    As_total_mm2: float = 0.0  # toplam donati alani

    # Gereksinimler
    requirements: RebarRequirements = field(default_factory=RebarRequirements)

    # Metadata
    source: str = "default"  # default, etabs, user, optimized
    notes: str = ""

    def __post_init__(self):
        self._compute_derived()

    def _compute_derived(self):
        """Turetilmis degerleri hesapla"""
        area_mm2 = self.width_m * self.depth_m * 1e6
        self.As_total_mm2 = self.longitudinal.area_total_mm2
        self.rho_pct = self.As_total_mm2 / area_mm2 * 100 if area_mm2 > 0 else 0

    @property
    def is_minimum_satisfied(self) -> bool:
        """Minimum donati kosullari saglaniyor mu?"""
        req = self.requirements

        return (
                self.rho_pct >= req.min_rho_pct
                and self.rho_pct <= req.max_rho_pct
                and self.longitudinal.diameter_mm >= req.min_bar_diameter_mm
                and self.longitudinal.n_bars >= req.min_n_bars
                and self.confinement.stirrup_diameter_mm >= req.min_stirrup_diameter_mm
        )

    @property
    def violations(self) -> List[str]:
        """Ihlal edilen minimum kosullar"""
        req = self.requirements
        viols = []

        if self.rho_pct < req.min_rho_pct:
            viols.append(f"rho={self.rho_pct:.2f}% < min {req.min_rho_pct}%")
        if self.rho_pct > req.max_rho_pct:
            viols.append(f"rho={self.rho_pct:.2f}% > max {req.max_rho_pct}%")
        if self.longitudinal.diameter_mm < req.min_bar_diameter_mm:
            viols.append(f"Phi{int(self.longitudinal.diameter_mm)} < min Phi{req.min_bar_diameter_mm}")
        if self.longitudinal.n_bars < req.min_n_bars:
            viols.append(f"{self.longitudinal.n_bars} bar < min {req.min_n_bars}")
        if self.confinement.stirrup_diameter_mm < req.min_stirrup_diameter_mm:
            viols.append(f"etriye Phi{int(self.confinement.stirrup_diameter_mm)} < min Phi{req.min_stirrup_diameter_mm}")

        return viols

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable dict"""
        return {
            "column_label": self.column_label,
            "section_name": self.section_name,
            "geometry": {
                "width_m": self.width_m,
                "depth_m": self.depth_m,
                "area_mm2": round(self.width_m * self.depth_m * 1e6, 0),
            },
            "longitudinal": self.longitudinal.to_dict(),
            "confinement": self.confinement.to_dict(),
            "computed": {
                "rho_pct": round(self.rho_pct, 3),
                "As_total_mm2": round(self.As_total_mm2, 1),
                "is_minimum_satisfied": self.is_minimum_satisfied,
                "violations": self.violations,
            },
            "requirements": {
                "min_rho_pct": self.requirements.min_rho_pct,
                "max_rho_pct": self.requirements.max_rho_pct,
                "min_bar_diameter_mm": self.requirements.min_bar_diameter_mm,
                "min_n_bars": self.requirements.min_n_bars,
                "min_stirrup_diameter_mm": self.requirements.min_stirrup_diameter_mm,
                "max_stirrup_spacing_mm": self.requirements.max_stirrup_spacing_mm,
            },
            "metadata": {
                "source": self.source,
                "notes": self.notes,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON string"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# =============================================================================
# REBAR SET BUILDER (GENISLETILEBILIR)
# =============================================================================

class RebarSetBuilder:
    """
    Donati seti olusturucu.

    Kullanim:
        # Minimum default
        rebar = RebarSetBuilder(column_label="C1", section_name="C50x50",
                                width_m=0.5, depth_m=0.5).build()

        # Override
        rebar = (RebarSetBuilder("C1", "C50x50", 0.5, 0.5)
                 .with_longitudinal(diameter_mm=20, n_bars=8)
                 .with_confinement(stirrup_dia_mm=10, spacing_mm=100)
                 .build())

        # ETABS'tan
        rebar = (RebarSetBuilder("C1", "C50x50", 0.5, 0.5)
                 .from_etabs(etabs_rebar_row)
                 .build())
    """

    def __init__(
            self,
            column_label: str,
            section_name: str,
            width_m: float,
            depth_m: float,
            requirements: Optional[RebarRequirements] = None,
    ):
        self.column_label = column_label
        self.section_name = section_name
        self.width_m = width_m
        self.depth_m = depth_m
        self.requirements = requirements or RebarRequirements()

        # Default degerler
        self._longitudinal = self._default_longitudinal()
        self._confinement = self._default_confinement()
        self._source = "default"
        self._notes = "Minimum default donati seti"

    def _default_longitudinal(self) -> LongitudinalRebar:
        """
        Minimum default boyuna donati uret.

        Kural:
        - TBDY 7.3.2: min rho = %1, min 6Phi14
        - Otomatik secim: kesit alanina gore
        """
        area_mm2 = self.width_m * self.depth_m * 1e6
        min_As = max(
            self.requirements.min_rho_pct / 100 * area_mm2,  # %1
            6 * get_bar_area(self.requirements.min_bar_diameter_mm),  # 6Phi14
        )

        # En az 6 bar olacak sekilde donati capi sec
        best_dia = self.requirements.min_bar_diameter_mm
        best_n = self.requirements.min_n_bars

        for dia in sorted(BAR_LIBRARY.keys()):
            n_bars = math.ceil(min_As / BAR_LIBRARY[dia])
            n_bars = max(n_bars, self.requirements.min_n_bars)
            # Cift sayiya yuvarla (simetri)
            if n_bars % 2 == 1:
                n_bars += 1

            area = n_bars * BAR_LIBRARY[dia]
            rho = area / area_mm2 * 100

            if rho >= self.requirements.min_rho_pct:
                best_dia = dia
                best_n = n_bars
                break
            else:
                # En buyuk capa kadar dene
                best_dia = dia
                best_n = n_bars

        return LongitudinalRebar(
            diameter_mm=float(best_dia),
            n_bars=best_n,
            arrangement="uniform",
        )

    def _default_confinement(self) -> ConfinementRebar:
        """Minimum default sargi donatisi"""
        return ConfinementRebar(
            stirrup_diameter_mm=float(self.requirements.min_stirrup_diameter_mm),
            stirrup_spacing_mm=float(self.requirements.max_stirrup_spacing_mm),
            stirrup_legs_dir1=2,
            stirrup_legs_dir2=2,
            cross_tie_diameter_mm=float(self.requirements.min_cross_tie_diameter_mm),
            sargi_zone_spacing_mm=float(self.requirements.max_stirrup_spacing_mm),
            mid_zone_spacing_mm=float(self.requirements.stirrup_spacing_mid_mm),
        )

    # -------------------------------------------------------------------------
    # FLUENT API
    # -------------------------------------------------------------------------

    def with_longitudinal(
            self,
            diameter_mm: float,
            n_bars: int,
            arrangement: str = "uniform",
    ) -> "RebarSetBuilder":
        """Boyuna donatiyi override et"""
        self._longitudinal = LongitudinalRebar(
            diameter_mm=diameter_mm,
            n_bars=n_bars,
            arrangement=arrangement,
        )
        self._source = "user"
        self._notes = "Kullanici tanimli donati"
        return self

    def with_longitudinal_area(
            self,
            As_total_mm2: float,
            n_bars: Optional[int] = None,
    ) -> "RebarSetBuilder":
        """
        Toplam donati alanindan donati seti olustur.

        n_bars verilmezse minimum 6 bar ile optimize eder.
        """
        if n_bars is None:
            n_bars = self.requirements.min_n_bars

        area_per_bar = As_total_mm2 / n_bars
        dia, area, _ = find_nearest_bar(area_per_bar)

        return self.with_longitudinal(
            diameter_mm=float(dia),
            n_bars=n_bars,
        )

    def with_confinement(
            self,
            stirrup_dia_mm: float,
            spacing_mm: float,
            legs_dir1: int = 2,
            legs_dir2: int = 2,
            sargi_zone_spacing_mm: Optional[float] = None,
            mid_zone_spacing_mm: Optional[float] = None,
    ) -> "RebarSetBuilder":
        """Sargi donatisini override et"""
        self._confinement = ConfinementRebar(
            stirrup_diameter_mm=stirrup_dia_mm,
            stirrup_spacing_mm=spacing_mm,
            stirrup_legs_dir1=legs_dir1,
            stirrup_legs_dir2=legs_dir2,
            cross_tie_diameter_mm=float(self.requirements.min_cross_tie_diameter_mm),
            sargi_zone_spacing_mm=sargi_zone_spacing_mm or spacing_mm,
            mid_zone_spacing_mm=mid_zone_spacing_mm or self.requirements.stirrup_spacing_mid_mm,
        )
        if self._source == "default":
            self._source = "user"
            self._notes = "Kullanici tanimli sargi"
        return self

    def from_etabs(self, etabs_row: Dict[str, Any]) -> "RebarSetBuilder":
        """
        ETABS column_rebar_defs satirindan donati oku.

        Beklenen kolonlar:
        - nbarstotal, bardiameter
        - stirrupdiameter, stirrupspacing, stirrup_legs_dir1, stirrup_legs_dir2
        """
        # Boyuna donati
        n_bars = int(etabs_row.get("nbarstotal", etabs_row.get("n_bars_total", 6)))
        bar_dia = float(etabs_row.get("bardiameter", etabs_row.get("bar_diameter_mm", 14)))

        self._longitudinal = LongitudinalRebar(
            diameter_mm=bar_dia,
            n_bars=n_bars,
            arrangement="uniform",
        )

        # Sargi donatisi
        stirrup_dia = float(etabs_row.get("stirrupdiameter", etabs_row.get("stirrup_diameter_mm", 8)))
        stirrup_spacing = float(etabs_row.get("stirrupspacing", etabs_row.get("stirrup_spacing_mm", 150)))
        legs_d1 = int(etabs_row.get("stirrup_legs_dir1", 2))
        legs_d2 = int(etabs_row.get("stirrup_legs_dir2", 2))

        self._confinement = ConfinementRebar(
            stirrup_diameter_mm=stirrup_dia,
            stirrup_spacing_mm=stirrup_spacing,
            stirrup_legs_dir1=legs_d1,
            stirrup_legs_dir2=legs_d2,
        )

        self._source = "etabs"
        self._notes = "ETABS donati verisi"
        return self

    def from_dict(self, data: Dict[str, Any]) -> "RebarSetBuilder":
        """Dict'ten donati oku"""
        long_data = data.get("longitudinal", {})
        conf_data = data.get("confinement", {})

        if long_data:
            self._longitudinal = LongitudinalRebar(
                diameter_mm=float(long_data.get("diameter_mm", 14)),
                n_bars=int(long_data.get("n_bars", 6)),
                arrangement=str(long_data.get("arrangement", "uniform")),
            )

        if conf_data:
            self._confinement = ConfinementRebar(
                stirrup_diameter_mm=float(conf_data.get("stirrup_diameter_mm", 8)),
                stirrup_spacing_mm=float(conf_data.get("stirrup_spacing_mm", 150)),
                stirrup_legs_dir1=int(conf_data.get("stirrup_legs_dir1", 2)),
                stirrup_legs_dir2=int(conf_data.get("stirrup_legs_dir2", 2)),
            )

        self._source = data.get("metadata", {}).get("source", "imported")
        self._notes = data.get("metadata", {}).get("notes", "Ice aktarildi")
        return self

    # -------------------------------------------------------------------------
    # BUILD
    # -------------------------------------------------------------------------

    def build(self) -> RebarSet:
        """RebarSet objesini olustur"""
        return RebarSet(
            column_label=self.column_label,
            section_name=self.section_name,
            width_m=self.width_m,
            depth_m=self.depth_m,
            longitudinal=self._longitudinal,
            confinement=self._confinement,
            requirements=self.requirements,
            source=self._source,
            notes=self._notes,
        )


# =============================================================================
# TOPLU REBAR SET COZUMLEYICI (CONTEXT UZERINDEN)
# =============================================================================

class RebarSetResolver:
    """
    ModelContext + topology + geometry + ETABS verisi uzerinden
    tum kolonlar icin RebarSet uretir.

    Oncelik sirasi:
    1. ETABS column_rebar_defs (varsa)
    2. Minimum default
    """

    def __init__(self, ctx: Any):
        self.ctx = ctx

    def resolve_all(self) -> Dict[str, RebarSet]:
        """
        Tum kolonlar icin RebarSet dondur.

        Returns:
            {column_label: RebarSet}
        """
        rebar_sets = {}

        # Context'ten verileri al
        topo_columns = self.ctx.topology.get("columns", [])
        section_dims = self.ctx.geometry.get("section_dims", {})
        frame_sections = self.ctx.geometry.get("column_sections", {})
        etabs_rebar = self.ctx.design_metadata.get("column_rebar_defs")

        # ETABS rebar varsa index'le
        etabs_index = {}
        if etabs_rebar is not None and not getattr(etabs_rebar, "empty", True):
            for _, row in etabs_rebar.iterrows():
                label = str(row.get("label", ""))
                if label:
                    etabs_index[label] = row.to_dict()

        # Her kolon icin RebarSet olustur
        for col_data in topo_columns:
            label = str(col_data.get("label", ""))
            if not label:
                continue

            # Kesit bilgisi
            section_name = frame_sections.get(label, str(col_data.get("section", "")))
            dims = section_dims.get(section_name, {})
            width = float(dims.get("width_m") or dims.get("b_min_m") or 0.3)
            depth = float(dims.get("depth_m") or dims.get("b_max_m") or 0.3)

            # Builder baslat
            builder = RebarSetBuilder(
                column_label=label,
                section_name=section_name,
                width_m=width,
                depth_m=depth,
            )

            # ETABS verisi varsa kullan
            if label in etabs_index:
                builder.from_etabs(etabs_index[label])

            rebar_sets[label] = builder.build()

        return rebar_sets

    def to_json(self, indent: int = 2) -> str:
        """Tum setleri JSON olarak dondur"""
        sets = self.resolve_all()
        data = {label: rs.to_dict() for label, rs in sets.items()}
        return json.dumps(data, indent=indent, ensure_ascii=False)


# =============================================================================
# CONVENIENCE
# =============================================================================

def create_default_rebar(
        column_label: str,
        width_m: float,
        depth_m: float,
        section_name: str = "",
) -> RebarSet:
    """
    Hizli default donati seti olustur.

    Args:
        column_label: Kolon etiketi (C1, C2, ...)
        width_m: Kesit genisligi (m)
        depth_m: Kesit yuksekligi (m)
        section_name: Kesit adi (opsiyonel)

    Returns:
        RebarSet: Minimum default donati seti
    """
    return (
        RebarSetBuilder(
            column_label=column_label,
            section_name=section_name or f"{width_m * 1000:.0f}x{depth_m * 1000:.0f}",
            width_m=width_m,
            depth_m=depth_m,
        )
        .build()
    )


def create_rebar_from_area(
        column_label: str,
        width_m: float,
        depth_m: float,
        As_mm2: float,
        n_bars: int = 8,
) -> RebarSet:
    """
    Toplam donati alanindan donati seti olustur.

    Args:
        column_label: Kolon etiketi
        width_m: Genislik (m)
        depth_m: Yukseklik (m)
        As_mm2: Toplam boyuna donati alani (mm2)
        n_bars: Bar sayisi
    """
    return (
        RebarSetBuilder(column_label, "", width_m, depth_m)
        .with_longitudinal_area(As_mm2, n_bars)
        .build()
    )