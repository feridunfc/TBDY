"""Read-only factual ETABS static-linear load-case acquisition.

This provider decodes ``LoadCases.StaticLinear.GetLoads`` and
``LoadPatterns.GetLoadType`` only.  It does not decide which cases satisfy a
TS500 G/Q/E/W load basis and does not perform any structural or regulatory
calculation.

The module is import-safe without ETABS/comtypes; callers pass already-attached
COM objects.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence


# CSI eLoadPatternType values documented by the public ETABS API.  Unknown newer
# codes are preserved factually rather than guessed.
LOAD_PATTERN_TYPE_BY_CODE: dict[int, str] = {
    1: "DEAD",
    2: "SUPER_DEAD",
    3: "LIVE",
    4: "REDUCE_LIVE",
    5: "QUAKE",
    6: "WIND",
    7: "SNOW",
    8: "OTHER",
    9: "MOVE",
    10: "TEMPERATURE",
    11: "ROOF_LIVE",
    12: "NOTIONAL",
    13: "PATTERN_LIVE",
    14: "WAVE",
    15: "BRAKING",
    16: "CENTRIFUGAL",
    17: "FRICTION",
    18: "ICE",
    19: "WIND_ON_LIVE_LOAD",
    20: "HORIZONTAL_EARTH_PRESSURE",
    21: "VERTICAL_EARTH_PRESSURE",
    22: "EARTH_SURCHARGE",
    23: "DOWN_DRAG",
    24: "VEHICLE_COLLISION",
    25: "VESSEL_COLLISION",
    26: "TEMPERATURE_GRADIENT",
    27: "SETTLEMENT",
    28: "SHRINKAGE",
    29: "CREEP",
    30: "WATERLOAD_PRESSURE",
    31: "LIVE_LOAD_SURCHARGE",
    32: "LOCKED_IN_FORCES",
    33: "PEDESTRIAN_LL",
    34: "PRESTRESS",
    35: "HYPERSTATIC",
    36: "BOUYANCY",
    37: "STREAM_FLOW",
    38: "IMPACT",
    39: "CONSTRUCTION",
    40: "DEAD_WEARING",
    41: "DEAD_WATER",
    42: "DEAD_MANUFACTURE",
    43: "EARTH_HYDROSTATIC",
    44: "PASSIVE_EARTH_PRESSURE",
    45: "ACTIVE_EARTH_PRESSURE",
    46: "PEDESTRIAN_LL_REDUCED",
    47: "SNOW_HIGH_ALTITUDE",
    48: "EURO_LM1_CHAR",
    49: "EURO_LM1_FREQ",
    50: "EURO_LM2",
    51: "EURO_LM3",
    52: "EURO_LM4",
}


class EtabsStaticLinearCaseProviderError(RuntimeError):
    """Raised when factual ETABS static-linear source data is malformed."""


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


def _seq(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(value)
    return (value,)


def _api_sequence(raw: Any, *, method: str, name: str, expected_len: int) -> tuple[Any, ...]:
    if not isinstance(raw, (tuple, list)):
        raise EtabsStaticLinearCaseProviderError(
            f"{method}({name!r}) returned unexpected scalar: {raw!r}"
        )
    values = tuple(raw)
    if len(values) != expected_len:
        raise EtabsStaticLinearCaseProviderError(
            f"{method}({name!r}) returned unexpected sequence length "
            f"{len(values)} (expected {expected_len}): {raw!r}"
        )
    return values


def capture_etabs_load_pattern_type(load_patterns: Any, name: str) -> EtabsLoadPatternTypeEvidence:
    pattern_name = _text(name, "load_pattern_name")
    raw = load_patterns.GetLoadType(pattern_name)
    type_raw, ret = _api_sequence(raw, method="GetLoadType", name=pattern_name, expected_len=2)
    if not isinstance(ret, int) or ret != 0:
        raise EtabsStaticLinearCaseProviderError(f"GetLoadType({pattern_name!r}) failed/raw={raw!r}")
    try:
        type_code = int(type_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsStaticLinearCaseProviderError(
            f"GetLoadType({pattern_name!r}) returned non-integer type/raw={raw!r}"
        ) from exc
    if type_code <= 0:
        raise EtabsStaticLinearCaseProviderError(
            f"GetLoadType({pattern_name!r}) returned invalid type code {type_code}"
        )
    return EtabsLoadPatternTypeEvidence(
        name=pattern_name,
        type_code=type_code,
        type_name=LOAD_PATTERN_TYPE_BY_CODE.get(type_code, f"UNKNOWN_{type_code}"),
        raw_get_load_type=repr(raw),
    )


def capture_etabs_static_linear_case(
    static_linear: Any,
    load_patterns: Any,
    name: str,
) -> EtabsStaticLinearCaseEvidence:
    case_name = _text(name, "load_case_name")
    raw = static_linear.GetLoads(case_name)
    number_raw, load_type_raw, load_name_raw, sf_raw, ret = _api_sequence(
        raw,
        method="StaticLinear.GetLoads",
        name=case_name,
        expected_len=5,
    )
    if not isinstance(ret, int) or ret != 0:
        raise EtabsStaticLinearCaseProviderError(
            f"StaticLinear.GetLoads({case_name!r}) failed/raw={raw!r}"
        )
    try:
        number = int(number_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsStaticLinearCaseProviderError(
            f"StaticLinear.GetLoads({case_name!r}) returned non-integer load count/raw={raw!r}"
        ) from exc
    if number < 0:
        raise EtabsStaticLinearCaseProviderError(
            f"StaticLinear.GetLoads({case_name!r}) returned negative load count"
        )

    load_types = _seq(load_type_raw)
    load_names = _seq(load_name_raw)
    scale_factors = _seq(sf_raw)
    if not (number == len(load_types) == len(load_names) == len(scale_factors)):
        raise EtabsStaticLinearCaseProviderError(
            f"StaticLinear.GetLoads({case_name!r}) count mismatch: n={number} "
            f"types={len(load_types)} names={len(load_names)} sf={len(scale_factors)}"
        )

    rows: list[EtabsStaticLinearLoadTermEvidence] = []
    for index, (type_value, name_value, factor_value) in enumerate(
        zip(load_types, load_names, scale_factors)
    ):
        load_type = _text(type_value, f"{case_name}.load_type[{index}]")
        if load_type not in {"Load", "Accel"}:
            raise EtabsStaticLinearCaseProviderError(
                f"{case_name}.load_type[{index}] must be Load or Accel, got {load_type!r}"
            )
        load_name = _text(name_value, f"{case_name}.load_name[{index}]")
        try:
            factor = float(factor_value)
        except (TypeError, ValueError) as exc:
            raise EtabsStaticLinearCaseProviderError(
                f"{case_name}.scale_factor[{index}] must be numeric"
            ) from exc
        if not math.isfinite(factor):
            raise EtabsStaticLinearCaseProviderError(
                f"{case_name}.scale_factor[{index}] must be finite"
            )
        pattern = (
            capture_etabs_load_pattern_type(load_patterns, load_name)
            if load_type == "Load"
            else None
        )
        rows.append(
            EtabsStaticLinearLoadTermEvidence(
                index=index,
                load_type=load_type,
                load_name=load_name,
                scale_factor=factor,
                load_pattern=pattern,
            )
        )

    return EtabsStaticLinearCaseEvidence(
        name=case_name,
        loads=tuple(rows),
        raw_get_loads=repr(raw),
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
