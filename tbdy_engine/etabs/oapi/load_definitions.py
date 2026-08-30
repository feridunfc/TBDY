"""Exact factual ETABS load-definition reads for current/live consumers.

This module owns CSI invocation and positional ABI decoding for consumed
LoadPatterns and LoadCases methods.  It contains no TS500 action-role promotion
or engineering policy.  Session-bound entry points execute through the verified
safety/gateway boundary and never expose raw CSI objects.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError

LINEAR_STATIC_CASE_TYPE_CODE = 1


@dataclass(frozen=True, slots=True)
class LoadPatternTypeFact:
    name: str
    type_code: int
    raw_response: object


@dataclass(frozen=True, slots=True)
class LoadCaseTypeFact:
    name: str
    case_type_code: int
    subtype_code: int
    design_type_code: int
    design_type_option: int
    auto_flag: int
    raw_response: object

    @property
    def is_linear_static(self) -> bool:
        return self.case_type_code == LINEAR_STATIC_CASE_TYPE_CODE


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


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise EtabsOAPIError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError(f"{label} must be an integer") from exc
    if result != value and str(result) != str(value):
        raise EtabsOAPIError(f"{label} must be an exact integer")
    return result


def _read_name_list(container: Any, label: str) -> tuple[tuple[str, ...], object]:
    raw = container.GetNameList()
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise EtabsOAPIError(f"{label}.GetNameList returned unexpected result: {raw!r}")
    count_raw, names_raw, ret = tuple(raw)
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"{label}.GetNameList failed/raw={raw!r}")
    count = _integer(count_raw, f"{label}.GetNameList count")
    names = _seq(names_raw)
    if count < 0 or count != len(names):
        raise EtabsOAPIError(
            f"{label}.GetNameList count mismatch: n={count} names={len(names)}"
        )
    canonical = tuple(_text(name, f"{label}.name") for name in names)
    if len(set(canonical)) != len(canonical):
        raise EtabsOAPIError(f"{label}.GetNameList returned duplicate names")
    return canonical, raw


def read_load_pattern_type(load_patterns: Any, name: str) -> LoadPatternTypeFact:
    pattern_name = _text(name, "load_pattern_name")
    raw = load_patterns.GetLoadType(pattern_name)
    type_raw, ret = _api_sequence(raw, method="GetLoadType", name=pattern_name, expected=2)
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"GetLoadType({pattern_name!r}) failed/raw={raw!r}")
    type_code = _integer(type_raw, f"GetLoadType({pattern_name!r}) type")
    if type_code <= 0:
        raise EtabsOAPIError(f"GetLoadType({pattern_name!r}) returned invalid type code {type_code}")
    return LoadPatternTypeFact(pattern_name, type_code, raw)


def read_load_pattern_names(load_patterns: Any) -> tuple[tuple[str, ...], object]:
    return _read_name_list(load_patterns, "LoadPatterns")


def read_load_case_names(load_cases: Any) -> tuple[tuple[str, ...], object]:
    return _read_name_list(load_cases, "LoadCases")


def read_load_case_type(load_cases: Any, name: str) -> LoadCaseTypeFact:
    case_name = _text(name, "load_case_name")
    raw = load_cases.GetTypeOAPI_1(case_name)
    case_type, subtype, design_type, design_option, auto, ret = _api_sequence(
        raw,
        method="LoadCases.GetTypeOAPI_1",
        name=case_name,
        expected=6,
    )
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"LoadCases.GetTypeOAPI_1({case_name!r}) failed/raw={raw!r}")
    fact = LoadCaseTypeFact(
        name=case_name,
        case_type_code=_integer(case_type, f"{case_name}.CaseType"),
        subtype_code=_integer(subtype, f"{case_name}.SubType"),
        design_type_code=_integer(design_type, f"{case_name}.DesignType"),
        design_type_option=_integer(design_option, f"{case_name}.DesignTypeOption"),
        auto_flag=_integer(auto, f"{case_name}.Auto"),
        raw_response=raw,
    )
    if fact.case_type_code <= 0:
        raise EtabsOAPIError(f"{case_name}.CaseType must be positive")
    if fact.design_type_option not in (0, 1):
        raise EtabsOAPIError(f"{case_name}.DesignTypeOption must be 0 or 1")
    if fact.auto_flag not in (0, 1):
        raise EtabsOAPIError(f"{case_name}.Auto must be 0 or 1")
    return fact


def read_static_linear_case(static_linear: Any, name: str) -> StaticLinearCaseFact:
    case_name = _text(name, "load_case_name")
    raw = static_linear.GetLoads(case_name)
    number_raw, load_type_raw, load_name_raw, sf_raw, ret = _api_sequence(
        raw, method="StaticLinear.GetLoads", name=case_name, expected=5
    )
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"StaticLinear.GetLoads({case_name!r}) failed/raw={raw!r}")
    number = _integer(number_raw, "StaticLinear.GetLoads count")
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


def read_load_pattern_names_from_session(
    session: EtabsVerifiedSession,
) -> tuple[tuple[str, ...], object]:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_load_pattern_names(sap.LoadPatterns),
        operation="oapi_load_patterns_get_name_list",
    )


def read_load_pattern_type_from_session(
    session: EtabsVerifiedSession,
    name: str,
) -> LoadPatternTypeFact:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_load_pattern_type(sap.LoadPatterns, name),
        operation="oapi_load_patterns_get_load_type",
    )


def read_load_case_names_from_session(
    session: EtabsVerifiedSession,
) -> tuple[tuple[str, ...], object]:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_load_case_names(sap.LoadCases),
        operation="oapi_load_cases_get_name_list",
    )


def read_load_case_type_from_session(
    session: EtabsVerifiedSession,
    name: str,
) -> LoadCaseTypeFact:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_load_case_type(sap.LoadCases, name),
        operation="oapi_load_cases_get_type_oapi_1",
    )


def read_static_linear_case_from_session(
    session: EtabsVerifiedSession,
    name: str,
) -> StaticLinearCaseFact:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_static_linear_case(sap.LoadCases.StaticLinear, name),
        operation="oapi_static_linear_get_loads",
    )


__all__ = [
    "LINEAR_STATIC_CASE_TYPE_CODE",
    "LoadCaseTypeFact",
    "LoadPatternTypeFact",
    "StaticLinearCaseFact",
    "StaticLinearLoadTermFact",
    "read_load_case_names",
    "read_load_case_names_from_session",
    "read_load_case_type",
    "read_load_case_type_from_session",
    "read_load_pattern_names",
    "read_load_pattern_names_from_session",
    "read_load_pattern_type",
    "read_load_pattern_type_from_session",
    "read_static_linear_case",
    "read_static_linear_case_from_session",
]
