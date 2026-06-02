"""
BeamDemandSet — Kiriş tasarım talepleri.
Combo/station envelope sonucu, governing evidence ile birlikte.
Birim standardı: kN, kNm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RawFrameForceRow:
    """Provider'dan gelen ham kuvvet satırı (sadece demand.py içinde serbest)"""
    beam_id: str
    label: str
    combo: str
    station: float
    p_kN: float = 0.0
    v2_kN: float = 0.0
    m3_kNm: float = 0.0
    t_kNm: float = 0.0


@dataclass(frozen=True)
class BeamDemandEvidence:
    """Tek bir demand değerinin kaynak kanıtı"""
    demand_name: str = ""
    combo: str | None = None
    station: float | None = None
    raw_value: float = 0.0
    rule: str = ""
    combo_family: str | None = None


@dataclass(frozen=True)
class DemandCombinationMetadata:
    """Seçilen kombinasyonlara ait metadata"""
    selected_combos: tuple[str, ...] = ()
    envelope_mode: str = "single_combo"


@dataclass(frozen=True)
class BeamDemandSet:
    """
    Kiriş tasarım talepleri.
    Birim standardı: kN, kNm.

    Demand Processor tarafından üretilir, Design Engine tarafından tüketilir.
    """
    beam_id: str
    label: str
    source: str = "unknown"

    # Moment talepleri — kNm
    Md_left_neg_kNm: float = 0.0
    Md_mid_pos_kNm: float | None = None
    Md_right_neg_kNm: float | None = None

    # Kesme talepleri — kN
    Vd_left_kN: float = 0.0
    Vd_right_kN: float = 0.0

    # Eksenel kuvvet — kN (basınç +)
    N_kN: float = 0.0

    # Burulma — kNm (future design/verification; torsion design not yet implemented)
    torsion_Td_kNm: float | None = None

    # Governing evidence
    governing: dict[str, BeamDemandEvidence] = field(default_factory=dict)

    # Combination metadata
    combination_metadata: DemandCombinationMetadata = field(
        default_factory=DemandCombinationMetadata
    )


def validate_beam_demand_set(demand: BeamDemandSet) -> tuple[str, ...]:
    """BeamDemandSet alanlarını doğrula"""
    invalid: list[str] = []

    if not demand.beam_id:
        invalid.append("beam_id")
    if not demand.label:
        invalid.append("label")
    if demand.source == "unknown":
        invalid.append("source")

    return tuple(invalid)
