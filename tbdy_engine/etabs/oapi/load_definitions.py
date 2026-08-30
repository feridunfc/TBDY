"""Exact factual ETABS load-definition reads for current production consumers.

This module owns CSI invocation and raw positional ABI decoding for the
currently consumed LoadPatterns and LoadCases.StaticLinear methods only. It
contains no TS500 action-role promotion or engineering policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .contracts import EtabsOAPIError


@dataclass(frozen=True, slots=True)
class LoadPatternTypeFact:
    name: str
    type_code: int
    raw_response: object


@dataclass(frozen=True, slots=True)
class StaticLinearLoadTermFact:
    index: int
    load_type: str
    load_name: str
    scale_factor: float


@dataclass(frozen=True, slots=True)
class StaticLinearCaseFact:
    name: str
    loads: tuple[StaticLinearLoadTermFact, ...]
    raw_response: object


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _seq(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(value)
    return (value,)


def _api_sequence(raw: Any, *, method: str, name: str, expected: int) -> tuple[Any, ...]:
    if not isinstance(raw, (tuple, list)):
        raise EtabsOAPIError(f"{method}({name!r}) returned unexpected scalar: {raw!r}")
    values = tuple(raw)
    if len(values) != expected:
        raise EtabsOAPIError(
            f"{method}({name!r}) returned {len(values)} values; expected {expected}: {raw!r}"
        )
    return values


def read_load_pattern_type(load_patterns: Any, name: str) -> LoadPatternTypeFact:
    pattern_name = _text(name, "load_pattern_name")
    raw = load_patterns.GetLoadType(pattern_name)
    type_raw, ret = _api_sequence(raw, method="GetLoadType", name=pattern_name, expected=2)
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"GetLoadType({pattern_name!r}) failed/raw={raw!r}")
    try:
        type_code = int(type_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError(f"GetLoadType({pattern_name!r}) returned non-integer type") from exc
    if type_code <= 0:
        raise EtabsOAPIError(f"GetLoadType({pattern_name!r}) returned invalid type code {type_code}")
    return LoadPatternTypeFact(pattern_name, type_code, raw)


def read_load_pattern_names(load_patterns: Any) -> tuple[tuple[str, ...], object]:
    raw = load_patterns.GetNameList()
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise EtabsOAPIError(f"LoadPatterns.GetNameList returned unexpected result: {raw!r}")
    count_raw, names_raw, ret = tuple(raw)
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"LoadPatterns.GetNameList failed/raw={raw!r}")
    try:
        count = int(count_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError("LoadPatterns.GetNameList returned non-integer count") from exc
    names = _seq(names_raw)
    if count < 0 or count != len(names):
        raise EtabsOAPIError(
            f"LoadPatterns.GetNameList count mismatch: n={count} names={len(names)}"
        )
    canonical = tuple(_text(str(name), "load_pattern_name") for name in names)
    if len(set(canonical)) != len(canonical):
        raise EtabsOAPIError("LoadPatterns.GetNameList returned duplicate names")
    return canonical, raw


def read_static_linear_case(static_linear: Any, name: str) -> StaticLinearCaseFact:
    case_name = _text(name, "load_case_name")
    raw = static_linear.GetLoads(case_name)
    number_raw, load_type_raw, load_name_raw, sf_raw, ret = _api_sequence(
        raw, method="StaticLinear.GetLoads", name=case_name, expected=5
    )
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"StaticLinear.GetLoads({case_name!r}) failed/raw={raw!r}")
    try:
        number = int(number_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError("StaticLinear.GetLoads returned non-integer count") from exc
    if number < 0:
        raise EtabsOAPIError("StaticLinear.GetLoads returned negative count")
    load_types = _seq(load_type_raw)
    load_names = _seq(load_name_raw)
    scale_factors = _seq(sf_raw)
    if not (number == len(load_types) == len(load_names) == len(scale_factors)):
        raise EtabsOAPIError(
            f"StaticLinear.GetLoads({case_name!r}) count mismatch: n={number} "
            f"types={len(load_types)} names={len(load_names)} sf={len(scale_factors)}"
        )
    rows: list[StaticLinearLoadTermFact] = []
    for index, (type_value, name_value, factor_value) in enumerate(
        zip(load_types, load_names, scale_factors)
    ):
        load_type = _text(type_value, f"{case_name}.load_type[{index}]")
        if load_type not in {"Load", "Accel"}:
            raise EtabsOAPIError(f"{case_name}.load_type[{index}] must be Load or Accel")
        load_name = _text(name_value, f"{case_name}.load_name[{index}]")
        try:
            factor = float(factor_value)
        except (TypeError, ValueError) as exc:
            raise EtabsOAPIError(f"{case_name}.scale_factor[{index}] must be numeric") from exc
        if not math.isfinite(factor):
            raise EtabsOAPIError(f"{case_name}.scale_factor[{index}] must be finite")
        rows.append(StaticLinearLoadTermFact(index, load_type, load_name, factor))
    return StaticLinearCaseFact(case_name, tuple(rows), raw)


__all__ = [
    "LoadPatternTypeFact",
    "StaticLinearCaseFact",
    "StaticLinearLoadTermFact",
    "read_load_pattern_names",
    "read_load_pattern_type",
    "read_static_linear_case",
]
