"""Typed factual contracts for exact CSI ETABS OAPI decoding.

These values describe only what the ETABS API returned. They contain no TBDY,
TS500, governing-selection, reinforcement-selection, or PASS/FAIL authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EtabsOAPIError(RuntimeError):
    """Raised when an exact CSI call fails or its positional ABI is malformed."""


@dataclass(frozen=True, slots=True)
class PointRestraintFact:
    point_name: str
    dofs: tuple[bool, bool, bool, bool, bool, bool]
    raw_response: object


@dataclass(frozen=True, slots=True)
class RebarColumnFact:
    section_name: str
    mat_prop_long: str
    mat_prop_confine: str
    pattern: int
    confine_type: int
    cover: float
    number_c_bars: int
    number_r3_bars: int
    number_r2_bars: int
    rebar_size_name: str
    tie_size_name: str
    tie_spacing_longit: float
    number_2_dir_tie_bars: int
    number_3_dir_tie_bars: int
    to_be_designed: bool
    raw_response: object


@dataclass(frozen=True, slots=True)
class ResponseComboConstituentFact:
    index: int
    cname_type_code: int
    name: str
    scale_factor: float


@dataclass(frozen=True, slots=True)
class ResponseComboFact:
    name: str
    combo_type_code: int
    constituents: tuple[ResponseComboConstituentFact, ...]
    raw_get_type_combo: object
    raw_get_case_list: object


@dataclass(frozen=True, slots=True)
class ConcreteDesignSectionFact:
    frame_name: str
    section_name: str
    raw_response: object


@dataclass(frozen=True, slots=True)
class ConcreteColumnSummaryFact:
    frame_name: str
    number_items: int
    frame_names: tuple[str, ...]
    combo_names: tuple[str, ...]
    station_names: tuple[str, ...]
    pmm_area: tuple[float, ...]
    pmm_ratio: tuple[float, ...]
    pmm_combo: tuple[str, ...]
    av_major: tuple[float, ...]
    av_minor: tuple[float, ...]
    error_summary: tuple[str, ...]
    warning_summary: tuple[str, ...]
    raw_response: object


@dataclass(frozen=True, slots=True)
class AreaPropertyAssignmentFact:
    area_name: str
    property_name: str
    raw_response: object


@dataclass(frozen=True, slots=True)
class WallPropertyFact:
    property_name: str
    wall_type: int
    shell_type: int
    material_name: str
    thickness: float
    color: int
    notes: str
    guid: str
    raw_response: object


__all__ = [
    "AreaPropertyAssignmentFact",
    "ConcreteColumnSummaryFact",
    "ConcreteDesignSectionFact",
    "EtabsOAPIError",
    "PointRestraintFact",
    "RebarColumnFact",
    "ResponseComboConstituentFact",
    "ResponseComboFact",
    "WallPropertyFact",
]
