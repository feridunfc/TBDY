"""Semantic factual ETABS static-linear load-case provider.

Exact LoadPatterns/StaticLinear CSI calls and positional decoding are owned by
``tbdy_engine.etabs.oapi.load_definitions``. This module retains factual naming
and semantic evidence construction only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.load_definitions import read_load_pattern_type, read_static_linear_case

LOAD_PATTERN_TYPE_BY_CODE: dict[int, str] = {
    1: "DEAD", 2: "SUPER_DEAD", 3: "LIVE", 4: "REDUCE_LIVE", 5: "QUAKE",
    6: "WIND", 7: "SNOW", 8: "OTHER", 9: "MOVE", 10: "TEMPERATURE",
    11: "ROOF_LIVE", 12: "NOTIONAL", 13: "PATTERN_LIVE", 14: "WAVE",
    15: "BRAKING", 16: "CENTRIFUGAL", 17: "FRICTION", 18: "ICE",
    19: "WIND_ON_LIVE_LOAD", 20: "HORIZONTAL_EARTH_PRESSURE",
    21: "VERTICAL_EARTH_PRESSURE", 22: "EARTH_SURCHARGE", 23: "DOWN_DRAG",
    24: "VEHICLE_COLLISION", 25: "VESSEL_COLLISION", 26: "TEMPERATURE_GRADIENT",
    27: "SETTLEMENT", 28: "SHRINKAGE", 29: "CREEP", 30: "WATERLOAD_PRESSURE",
    31: "LIVE_LOAD_SURCHARGE", 32: "LOCKED_IN_FORCES", 33: "PEDESTRIAN_LL",
    34: "PRESTRESS", 35: "HYPERSTATIC", 36: "BOUYANCY", 37: "STREAM_FLOW",
    38: "IMPACT", 39: "CONSTRUCTION", 40: "DEAD_WEARING", 41: "DEAD_WATER",
    42: "DEAD_MANUFACTURE", 43: "EARTH_HYDROSTATIC", 44: "PASSIVE_EARTH_PRESSURE",
    45: "ACTIVE_EARTH_PRESSURE", 46: "PEDESTRIAN_LL_REDUCED", 47: "SNOW_HIGH_ALTITUDE",
    48: "EURO_LM1_CHAR", 49: "EURO_LM1_FREQ", 50: "EURO_LM2", 51: "EURO_LM3",
    52: "EURO_LM4",
}


class EtabsStaticLinearCaseProviderError(RuntimeError):
    """Raised when factual OAPI facts cannot be promoted to semantic evidence."""


@dataclass(frozen=True, slots=True)
class EtabsLoadPatternTypeEvidence:
    name: str
    type_code: int
    type_name: str
    raw_get_load_type: str
    status: str = "PROVEN_FACTUAL_LOAD_PATTERN_TYPE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "type_code": self.type_code,
            "type_name": self.type_name,
            "raw_api": {"GetLoadType": self.raw_get_load_type},
        }


@dataclass(frozen=True, slots=True)
class EtabsStaticLinearLoadTermEvidence:
    index: int
    load_type: str
    load_name: str
    scale_factor: float
    load_pattern: EtabsLoadPatternTypeEvidence | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "load_type": self.load_type,
            "load_name": self.load_name,
            "scale_factor": self.scale_factor,
            "load_pattern": None if self.load_pattern is None else self.load_pattern.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class EtabsStaticLinearCaseEvidence:
    name: str
    loads: tuple[EtabsStaticLinearLoadTermEvidence, ...]
    raw_get_loads: str
    status: str = "PROVEN_FACTUAL_STATIC_LINEAR_CASE_LOADS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "loads": [item.as_dict() for item in self.loads],
            "raw_api": {"StaticLinear.GetLoads": self.raw_get_loads},
        }


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsStaticLinearCaseProviderError(f"{label} must be a nonblank canonical string")
    return value


def capture_etabs_load_pattern_type(load_patterns: Any, name: str) -> EtabsLoadPatternTypeEvidence:
    pattern_name = _text(name, "load_pattern_name")
    try:
        fact = read_load_pattern_type(load_patterns, pattern_name)
    except EtabsOAPIError as exc:
        raise EtabsStaticLinearCaseProviderError(str(exc)) from exc
    return EtabsLoadPatternTypeEvidence(
        name=fact.name,
        type_code=fact.type_code,
        type_name=LOAD_PATTERN_TYPE_BY_CODE.get(fact.type_code, f"UNKNOWN_{fact.type_code}"),
        raw_get_load_type=repr(fact.raw_response),
    )


def capture_etabs_static_linear_case(
    static_linear: Any,
    load_patterns: Any,
    name: str,
) -> EtabsStaticLinearCaseEvidence:
    case_name = _text(name, "load_case_name")
    try:
        fact = read_static_linear_case(static_linear, case_name)
    except EtabsOAPIError as exc:
        raise EtabsStaticLinearCaseProviderError(str(exc)) from exc
    rows = tuple(
        EtabsStaticLinearLoadTermEvidence(
            index=item.index,
            load_type=item.load_type,
            load_name=item.load_name,
            scale_factor=item.scale_factor,
            load_pattern=(
                capture_etabs_load_pattern_type(load_patterns, item.load_name)
                if item.load_type == "Load"
                else None
            ),
        )
        for item in fact.loads
    )
    return EtabsStaticLinearCaseEvidence(
        name=fact.name,
        loads=rows,
        raw_get_loads=repr(fact.raw_response),
    )


def capture_etabs_static_linear_cases(
    static_linear: Any,
    load_patterns: Any,
    names: Sequence[str],
) -> tuple[EtabsStaticLinearCaseEvidence, ...]:
    requested = tuple(_text(item, "load_case_name") for item in names)
    if not requested or len(requested) != len(set(requested)):
        raise EtabsStaticLinearCaseProviderError(
            "load case names must be a nonempty unique sequence"
        )
    return tuple(
        capture_etabs_static_linear_case(static_linear, load_patterns, name)
        for name in requested
    )


__all__ = [
    "EtabsLoadPatternTypeEvidence",
    "EtabsStaticLinearCaseEvidence",
    "EtabsStaticLinearCaseProviderError",
    "EtabsStaticLinearLoadTermEvidence",
    "LOAD_PATTERN_TYPE_BY_CODE",
    "capture_etabs_load_pattern_type",
    "capture_etabs_static_linear_case",
    "capture_etabs_static_linear_cases",
]
