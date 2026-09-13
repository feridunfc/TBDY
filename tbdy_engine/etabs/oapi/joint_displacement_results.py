"""Exact factual CSI ``Results.JointDispl`` boundary.

This module owns only the documented CSI invocation/tuple decoding and the
reversible Results.Setup selection needed to read one exact point-object result
for one already-existing case or combo. It does not run analysis, aggregate
storey translations, or assign TS500 engineering meaning.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from tbdy_engine.etabs.safety import (
    EtabsVerifiedSession,
    ResultsSetupReadTransaction,
    _execute_verified_read,
)

from .contracts import EtabsOAPIError


CSI_ITEM_TYPE_ELM_OBJECT = 0


@dataclass(frozen=True, slots=True)
class JointDisplacementResultRow:
    point_object: str
    element_name: str
    load_case: str
    step_type: str
    step_number: float
    u1: float
    u2: float
    u3: float
    r1: float
    r2: float
    r3: float


@dataclass(frozen=True, slots=True)
class JointDisplacementResultFact:
    point_object: str
    output_name: str
    output_kind: str
    rows: tuple[JointDisplacementResultRow, ...]
    return_code: int
    source_api: str = "Results.JointDispl"
    item_type_elm: int = CSI_ITEM_TYPE_ELM_OBJECT

    @property
    def evidence_ref(self) -> str:
        return (
            f"ETABS:Results.JointDispl:{self.output_kind}:{self.output_name}:"
            f"point={self.point_object}:rows={len(self.rows)}"
        )


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise EtabsOAPIError(f"{label} must be a string")
    result = value.strip()
    if not result and not allow_empty:
        raise EtabsOAPIError(f"{label} must be nonblank")
    return result


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EtabsOAPIError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite")
    return result


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EtabsOAPIError("JointDispl.NumberResults must be a nonnegative integer")
    return int(value)


def _array(value: object, label: str, count: int) -> tuple[object, ...]:
    if not isinstance(value, (tuple, list)) or len(value) < count:
        raise EtabsOAPIError(f"{label} must contain at least {count} values")
    return tuple(value[:count])


def decode_joint_displ_response(
    raw: object,
    *,
    point_object: str,
    output_name: str,
    output_kind: str,
) -> JointDisplacementResultFact:
    """Decode the documented Python ``Results.JointDispl`` ABI.

    The supported CSI Python return shape is::

        NumberResults, Obj, Elm, LoadCase, StepType, StepNum,
        U1, U2, U3, R1, R2, R3, ret

    Only exact ObjectElm acquisition is promoted by this boundary.
    """
    point = _text(point_object, "point_object")
    name = _text(output_name, "output_name")
    kind = _text(output_kind, "output_kind")
    if kind not in {"case", "combo"}:
        raise EtabsOAPIError("output_kind must be case or combo")
    if not isinstance(raw, (tuple, list)) or len(raw) != 13:
        raise EtabsOAPIError(f"Results.JointDispl returned unexpected ABI shape: {raw!r}")

    values = tuple(raw)
    count = _count(values[0])
    arrays = tuple(
        _array(values[index], f"JointDispl[{index}]", count)
        for index in range(1, 12)
    )
    ret = values[12]
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"Results.JointDispl returned nonzero code {ret!r}")

    rows: list[JointDisplacementResultRow] = []
    for index in range(count):
        obj = _text(arrays[0][index], f"JointDispl.Obj[{index}]")
        if obj != point:
            raise EtabsOAPIError(
                f"JointDispl point binding mismatch at row {index}: Obj={obj!r}, expected={point!r}"
            )
        load_case = _text(arrays[2][index], f"JointDispl.LoadCase[{index}]")
        if load_case != name:
            raise EtabsOAPIError(
                f"JointDispl output binding mismatch at row {index}: "
                f"LoadCase={load_case!r}, expected={name!r}"
            )
        rows.append(
            JointDisplacementResultRow(
                point_object=obj,
                element_name=_text(arrays[1][index], f"JointDispl.Elm[{index}]"),
                load_case=load_case,
                step_type=_text(
                    str(arrays[3][index] or ""),
                    f"JointDispl.StepType[{index}]",
                    allow_empty=True,
                ),
                step_number=_finite(arrays[4][index], f"JointDispl.StepNum[{index}]"),
                u1=_finite(arrays[5][index], f"JointDispl.U1[{index}]"),
                u2=_finite(arrays[6][index], f"JointDispl.U2[{index}]"),
                u3=_finite(arrays[7][index], f"JointDispl.U3[{index}]"),
                r1=_finite(arrays[8][index], f"JointDispl.R1[{index}]"),
                r2=_finite(arrays[9][index], f"JointDispl.R2[{index}]"),
                r3=_finite(arrays[10][index], f"JointDispl.R3[{index}]"),
            )
        )
    if not rows:
        raise EtabsOAPIError(
            f"Results.JointDispl returned no rows for {kind} {name!r}, point {point!r}"
        )
    return JointDisplacementResultFact(
        point_object=point,
        output_name=name,
        output_kind=kind,
        rows=tuple(rows),
        return_code=0,
    )


def read_joint_displ_from_session(
    session: EtabsVerifiedSession,
    *,
    point_object: str,
    output_name: str,
    output_kind: str,
    timeout_seconds: float = 30.0,
) -> JointDisplacementResultFact:
    """Read one point object's displacement under one exact selected output."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    point = _text(point_object, "point_object")
    name = _text(output_name, "output_name")
    kind = _text(output_kind, "output_kind")
    if kind not in {"case", "combo"}:
        raise EtabsOAPIError("output_kind must be case or combo")

    def acquire(_etabs_object: object, sap_model: Any) -> JointDisplacementResultFact:
        results = getattr(sap_model, "Results", None)
        method = getattr(results, "JointDispl", None)
        if not callable(method):
            raise EtabsOAPIError("Results.JointDispl is unavailable")
        with ResultsSetupReadTransaction(sap_model) as transaction:
            if kind == "combo":
                transaction.select_combo(name)
            else:
                transaction.select_case(name)
            raw = method(point, CSI_ITEM_TYPE_ELM_OBJECT)
        return decode_joint_displ_response(
            raw,
            point_object=point,
            output_name=name,
            output_kind=kind,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation=f"joint_displ:{kind}:{name}:{point}",
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "CSI_ITEM_TYPE_ELM_OBJECT",
    "JointDisplacementResultFact",
    "JointDisplacementResultRow",
    "decode_joint_displ_response",
    "read_joint_displ_from_session",
]
