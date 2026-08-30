"""Exact factual CSI response-combination reads.

This module owns ``RespCombo.GetNameList``, ``GetTypeCombo`` and ``GetCaseList``
positional decoding. It does not decide whether a combination is expected,
acceptable, governing, or regulatory. Session-bound entry points keep raw
RespCombo capability inside the verified gateway STA boundary.
"""
from __future__ import annotations

import math
from typing import Any

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import (
    EtabsOAPIError,
    ResponseComboConstituentFact,
    ResponseComboFact,
)

_VALID_COMBO_TYPES = frozenset({0, 1, 2, 3, 4})
_VALID_CNAME_TYPES = frozenset({0, 1})


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _sequence(raw: Any, *, method: str, name: str, length: int) -> tuple[Any, ...]:
    if not isinstance(raw, (tuple, list)):
        raise EtabsOAPIError(f"{method}({name!r}) returned unexpected scalar: {raw!r}")
    values = tuple(raw)
    if len(values) != length:
        raise EtabsOAPIError(
            f"{method}({name!r}) returned {len(values)} values; expected {length}: {raw!r}"
        )
    return values


def _items(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(value)
    return (value,)


def read_response_combo_names(resp_combo: Any) -> tuple[tuple[str, ...], object]:
    raw = resp_combo.GetNameList()
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise EtabsOAPIError(f"RespCombo.GetNameList returned unexpected result: {raw!r}")
    count_raw, names_raw, ret = tuple(raw)
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"RespCombo.GetNameList failed/raw={raw!r}")
    if isinstance(count_raw, bool):
        raise EtabsOAPIError("RespCombo.GetNameList count must be integer")
    try:
        count = int(count_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError("RespCombo.GetNameList count must be integer") from exc
    names = _items(names_raw)
    if count < 0 or count != len(names):
        raise EtabsOAPIError(
            f"RespCombo.GetNameList count mismatch: n={count} names={len(names)}"
        )
    canonical = tuple(_text(name, "combo_name") for name in names)
    if len(set(canonical)) != len(canonical):
        raise EtabsOAPIError("RespCombo.GetNameList returned duplicate names")
    return canonical, raw


def read_response_combo(resp_combo: Any, name: str) -> ResponseComboFact:
    """Read one exact ETABS response-combination definition."""
    combo_name = _text(name, "combo_name")

    raw_type = resp_combo.GetTypeCombo(combo_name)
    combo_type_raw, type_ret = _sequence(
        raw_type, method="GetTypeCombo", name=combo_name, length=2
    )
    if not isinstance(type_ret, int) or isinstance(type_ret, bool) or type_ret != 0:
        raise EtabsOAPIError(f"GetTypeCombo({combo_name!r}) failed/raw={raw_type!r}")
    try:
        combo_type = int(combo_type_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError(
            f"GetTypeCombo({combo_name!r}) returned non-integer type/raw={raw_type!r}"
        ) from exc
    if combo_type not in _VALID_COMBO_TYPES:
        raise EtabsOAPIError(
            f"GetTypeCombo({combo_name!r}) returned unknown type code {combo_type}"
        )

    raw_cases = resp_combo.GetCaseList(combo_name)
    number_raw, cname_type_raw, cname_raw, scale_raw, case_ret = _sequence(
        raw_cases, method="GetCaseList", name=combo_name, length=5
    )
    if not isinstance(case_ret, int) or isinstance(case_ret, bool) or case_ret != 0:
        raise EtabsOAPIError(f"GetCaseList({combo_name!r}) failed/raw={raw_cases!r}")
    try:
        number_items = int(number_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError(
            f"GetCaseList({combo_name!r}) returned non-integer item count"
        ) from exc
    if number_items < 0:
        raise EtabsOAPIError(f"GetCaseList({combo_name!r}) returned negative item count")

    kinds = _items(cname_type_raw)
    names = _items(cname_raw)
    factors = _items(scale_raw)
    if not (number_items == len(kinds) == len(names) == len(factors)):
        raise EtabsOAPIError(
            f"GetCaseList({combo_name!r}) count mismatch: n={number_items} "
            f"types={len(kinds)} names={len(names)} sf={len(factors)}"
        )

    rows: list[ResponseComboConstituentFact] = []
    for index, (kind_raw, child_raw, factor_raw) in enumerate(zip(kinds, names, factors)):
        try:
            kind = int(kind_raw)
        except (TypeError, ValueError) as exc:
            raise EtabsOAPIError(f"GetCaseList CNameType[{index}] is not integer") from exc
        if kind not in _VALID_CNAME_TYPES:
            raise EtabsOAPIError(f"GetCaseList returned unknown CNameType={kind}")
        child = _text(child_raw, f"GetCaseList({combo_name!r}).name[{index}]")
        try:
            factor = float(factor_raw)
        except (TypeError, ValueError) as exc:
            raise EtabsOAPIError(f"GetCaseList scale factor[{index}] is not numeric") from exc
        if not math.isfinite(factor):
            raise EtabsOAPIError(f"GetCaseList scale factor[{index}] is not finite")
        rows.append(
            ResponseComboConstituentFact(
                index=index,
                cname_type_code=kind,
                name=child,
                scale_factor=factor,
            )
        )

    return ResponseComboFact(
        name=combo_name,
        combo_type_code=combo_type,
        constituents=tuple(rows),
        raw_get_type_combo=raw_type,
        raw_get_case_list=raw_cases,
    )


def read_response_combo_names_from_session(
    session: EtabsVerifiedSession,
) -> tuple[tuple[str, ...], object]:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_response_combo_names(sap.RespCombo),
        operation="oapi_resp_combo_get_name_list",
    )


def read_response_combo_from_session(
    session: EtabsVerifiedSession,
    name: str,
) -> ResponseComboFact:
    return _execute_verified_read(
        session,
        lambda _app, sap: read_response_combo(sap.RespCombo, name),
        operation="oapi_resp_combo_definition",
    )


__all__ = [
    "read_response_combo",
    "read_response_combo_from_session",
    "read_response_combo_names",
    "read_response_combo_names_from_session",
]
