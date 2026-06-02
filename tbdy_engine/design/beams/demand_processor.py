"""
BeamDemandProcessor — raw demand rows → BeamDemandSet.
Envelope kurallarıyla governing demand seçimi yapar.
Design calculation yapmaz.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

from .demand import (
    RawFrameForceRow,
    BeamDemandSet,
    BeamDemandEvidence,
    DemandCombinationMetadata,
)


# =============================================================================
# Custom Exception
# =============================================================================

class BeamDemandProcessorError(ValueError):
    """Demand processor hatası — stage bilgisi taşır"""
    stage: str

    def __init__(self, stage: str, message: str = ""):
        super().__init__(message)
        self.stage = stage


# =============================================================================
# Zone Logic (FIX: station origin normalization)
# =============================================================================

def _zone(relative_station: float, length_mm: float) -> str:
    """Normalize edilmiş istasyona göre bölge belirleme (0-L aralığında)."""
    ratio = relative_station / length_mm if length_mm > 0 else -1.0

    if ratio < 0.0 or ratio > 1.0:
        raise BeamDemandProcessorError(
            "demand_station_range",
            f"Relative station {relative_station} is outside [0, {length_mm}]",
        )

    if ratio <= 0.25:
        return "left"
    elif ratio >= 0.75:
        return "right"
    else:
        return "mid"


# =============================================================================
# Demand Selection Helpers
# =============================================================================

def _select_abs_max(
    rows: list[RawFrameForceRow],
    attr: str,
) -> tuple[float, RawFrameForceRow | None]:
    """Mutlak değerce en büyük değeri ve satırı döndür."""
    best_val = 0.0
    best_row: RawFrameForceRow | None = None

    for row in rows:
        val = abs(getattr(row, attr, 0.0))
        if val > best_val:
            best_val = val
            best_row = row

    return best_val, best_row


def _select_positive_max(
    rows: list[RawFrameForceRow],
    attr: str,
) -> tuple[float, RawFrameForceRow | None]:
    """En büyük pozitif değeri ve satırı döndür."""
    best_val = 0.0
    best_row: RawFrameForceRow | None = None

    for row in rows:
        val = getattr(row, attr, 0.0)
        if val > best_val:
            best_val = val
            best_row = row

    return best_val, best_row


def _select_signed_max_abs(
    rows: list[RawFrameForceRow],
    attr: str,
) -> tuple[float, RawFrameForceRow | None]:
    """Mutlak değerce en büyük değeri orijinal işaretiyle döndürür."""
    best_abs = 0.0
    best_val = 0.0
    best_row: RawFrameForceRow | None = None

    for row in rows:
        val = getattr(row, attr, 0.0)
        if abs(val) > best_abs:
            best_abs = abs(val)
            best_val = val
            best_row = row

    return best_val, best_row


# =============================================================================
# Evidence Builder
# =============================================================================

def _make_evidence(
    demand_name: str,
    row: RawFrameForceRow | None,
    raw_value: float,
    rule: str,
) -> BeamDemandEvidence:
    """BeamDemandEvidence oluşturur."""
    if row is None:
        return BeamDemandEvidence(
            demand_name=demand_name,
            combo=None,
            station=None,
            raw_value=raw_value,
            rule=rule,
        )

    return BeamDemandEvidence(
        demand_name=demand_name,
        combo=row.combo,
        station=row.station,
        raw_value=raw_value,
        rule=rule,
    )


# =============================================================================
# Main Processor
# =============================================================================

def process_frameforce_rows_to_demand_set(
    rows: Sequence[RawFrameForceRow],
    *,
    beam_id: str,
    label: str,
    selected_combos: Sequence[str] = (),
    length_mm: float | None = None,
    source: str = "etabs_frameforce",
) -> BeamDemandSet:
    """
    raw demand rows → BeamDemandSet.

    Args:
        rows: Ham kuvvet satırları.
        beam_id: Benzersiz kiriş kimliği.
        label: Kullanıcı etiketi.
        selected_combos: Filtrelenecek kombinasyonlar (boşsa tümü, sıra korunur).
        length_mm: Kiriş boyu (mm). Verilmezse station max-min kullanılır.
        source: Kaynak etiketi.

    Returns:
        BeamDemandSet — governing demand'ler ve evidence ile.

    Raises:
        BeamDemandProcessorError: Boş rows, geçersiz station, eksik combo.
    """
    # -----------------------------------------------------------------
    # 1. Girdi kontrolü
    # -----------------------------------------------------------------
    if not rows:
        raise BeamDemandProcessorError(
            "demand_input_empty",
            f"No demand rows for beam_id={beam_id}",
        )

    # -----------------------------------------------------------------
    # 2. Combo filtresi — sıra korunur
    # -----------------------------------------------------------------
    if selected_combos:
        selected_list = list(selected_combos)
        filtered = [r for r in rows if r.combo in selected_list]
        if not filtered:
            raise BeamDemandProcessorError(
                "demand_no_selected_combos",
                f"No rows match selected_combos={list(selected_combos)}",
            )
        # Seçilen sırayı koru
        actual_combos = tuple(
            c for c in selected_list
            if any(r.combo == c for r in filtered)
        )
    else:
        filtered = list(rows)
        actual_combos = tuple(sorted({r.combo for r in filtered}))

    envelope_mode = "single_combo" if len(actual_combos) == 1 else "multi_combo"

    # -----------------------------------------------------------------
    # 3. Length + station origin (FIX: normalize station)
    # -----------------------------------------------------------------
    stations = [r.station for r in filtered]

    if length_mm is None:
        station_origin = min(stations)
        length_mm = max(stations) - station_origin
        if length_mm <= 0:
            raise BeamDemandProcessorError(
                "demand_units",
                f"Cannot determine beam length from stations: {stations}",
            )
        length_source = "station_range"
    else:
        station_origin = 0.0
        length_source = "explicit"

    # -----------------------------------------------------------------
    # 4. Zone'lara ayır (normalize edilmiş istasyonla)
    # -----------------------------------------------------------------
    left_rows: list[RawFrameForceRow] = []
    mid_rows: list[RawFrameForceRow] = []
    right_rows: list[RawFrameForceRow] = []

    for row in filtered:
        relative_station = row.station - station_origin
        zone = _zone(relative_station, length_mm)
        if zone == "left":
            left_rows.append(row)
        elif zone == "mid":
            mid_rows.append(row)
        else:
            right_rows.append(row)

    if not left_rows:
        raise BeamDemandProcessorError(
            "demand_zone_missing",
            "No rows in left zone",
        )
    if not right_rows:
        raise BeamDemandProcessorError(
            "demand_zone_missing",
            "No rows in right zone",
        )

    # -----------------------------------------------------------------
    # 5. Demand seçimleri
    # -----------------------------------------------------------------
    governing: dict[str, BeamDemandEvidence] = {}

    # Md_left_neg — left zone'daki negatif M3'lerin mutlak en büyüğü
    left_neg = [r for r in left_rows if r.m3_kNm < 0]
    if left_neg:
        md_left, left_row = _select_abs_max(left_neg, "m3_kNm")
        governing["Md_left_neg_kNm"] = _make_evidence(
            "Md_left_neg_kNm", left_row,
            left_row.m3_kNm if left_row else 0.0,
            "max_abs_negative_left_zone",
        )
    else:
        md_left = 0.0
        governing["Md_left_neg_kNm"] = _make_evidence(
            "Md_left_neg_kNm", None, 0.0, "no_negative_moment_in_left_zone",
        )

    # Md_mid_pos — mid zone'daki pozitif M3'lerin en büyüğü
    mid_pos = [r for r in mid_rows if r.m3_kNm > 0]
    if mid_pos:
        md_mid, mid_row = _select_positive_max(mid_pos, "m3_kNm")
        governing["Md_mid_pos_kNm"] = _make_evidence(
            "Md_mid_pos_kNm", mid_row,
            mid_row.m3_kNm if mid_row else 0.0,
            "max_positive_mid_zone",
        )
        md_mid = md_mid if md_mid > 0 else None
    else:
        md_mid = None
        governing["Md_mid_pos_kNm"] = _make_evidence(
            "Md_mid_pos_kNm", None, 0.0, "no_positive_moment_in_mid_zone",
        )

    # Md_right_neg — right zone'daki negatif M3'lerin mutlak en büyüğü
    right_neg = [r for r in right_rows if r.m3_kNm < 0]
    if right_neg:
        md_right, right_row = _select_abs_max(right_neg, "m3_kNm")
        governing["Md_right_neg_kNm"] = _make_evidence(
            "Md_right_neg_kNm", right_row,
            right_row.m3_kNm if right_row else 0.0,
            "max_abs_negative_right_zone",
        )
    else:
        md_right = 0.0
        governing["Md_right_neg_kNm"] = _make_evidence(
            "Md_right_neg_kNm", None, 0.0, "no_negative_moment_in_right_zone",
        )

    # Vd_left — left zone/end abs(V2) max
    vd_left, v_left_row = _select_abs_max(left_rows, "v2_kN")
    governing["Vd_left_kN"] = _make_evidence(
        "Vd_left_kN", v_left_row,
        v_left_row.v2_kN if v_left_row else 0.0,
        "max_abs_shear_left",
    )

    # Vd_right — right zone/end abs(V2) max
    vd_right, v_right_row = _select_abs_max(right_rows, "v2_kN")
    governing["Vd_right_kN"] = _make_evidence(
        "Vd_right_kN", v_right_row,
        v_right_row.v2_kN if v_right_row else 0.0,
        "max_abs_shear_right",
    )

    # N — tüm zone'larda abs(p_kN) en büyük (işaret korunur)
    n_val, n_row = _select_signed_max_abs(filtered, "p_kN")
    governing["N_kN"] = _make_evidence(
        "N_kN", n_row,
        n_row.p_kN if n_row else 0.0,
        "max_abs_axial_all_zones",
    )

    # Torsion — tüm zone'larda abs(t_kNm) en büyük
    t_val, t_row = _select_abs_max(filtered, "t_kNm")
    if t_val > 0 and t_row:
        governing["torsion_Td_kNm"] = _make_evidence(
            "torsion_Td_kNm", t_row,
            t_row.t_kNm,
            "max_abs_torsion_all_zones",
        )
        torsion = t_val
    else:
        torsion = None

    # -----------------------------------------------------------------
    # 6. BeamDemandSet oluştur
    # -----------------------------------------------------------------
    return BeamDemandSet(
        beam_id=beam_id,
        label=label,
        source=source,
        Md_left_neg_kNm=md_left,
        Md_mid_pos_kNm=md_mid,
        Md_right_neg_kNm=md_right,
        Vd_left_kN=vd_left,
        Vd_right_kN=vd_right,
        N_kN=n_val,
        torsion_Td_kNm=torsion,
        governing=governing,
        combination_metadata=DemandCombinationMetadata(
            selected_combos=actual_combos,
            envelope_mode=envelope_mode,
        ),
    )
