"""Typed CSI result ABI used only as factual evidence for TS500 Eq.7.13 mode participation.

This module owns exact Results.FrameForce / Results.AreaForceShell /
Results.AreaStrainShell invocation, Python COM tuple decoding, exact object/case
binding, and reversible Results.Setup selection. It does not decide TS500
applicability, participation, modifier targets, or PASS/FAIL.
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

_OBJECT_ELM = 0


@dataclass(frozen=True, slots=True)
class FrameForceResponseRow:
    object_name: str
    object_station: float
    element_name: str
    element_station: float
    load_case: str
    step_type: str
    step_number: float
    p: float
    v2: float
    v3: float
    t: float
    m2: float
    m3: float


@dataclass(frozen=True, slots=True)
class FrameForceResponseFact:
    frame_name: str
    case_name: str
    rows: tuple[FrameForceResponseRow, ...]
    return_code: int
    source_api: str = "Results.FrameForce"

    @property
    def evidence_ref(self) -> str:
        return f"ETABS:Results.FrameForce:{self.frame_name}:{self.case_name}:rows={len(self.rows)}"


@dataclass(frozen=True, slots=True)
class AreaForceShellResponseRow:
    object_name: str
    element_name: str
    point_element_name: str
    load_case: str
    step_type: str
    step_number: float
    f11: float
    f22: float
    f12: float
    m11: float
    m22: float
    m12: float
    v13: float
    v23: float


@dataclass(frozen=True, slots=True)
class AreaForceShellResponseFact:
    area_name: str
    case_name: str
    rows: tuple[AreaForceShellResponseRow, ...]
    return_code: int
    source_api: str = "Results.AreaForceShell"

    @property
    def evidence_ref(self) -> str:
        return f"ETABS:Results.AreaForceShell:{self.area_name}:{self.case_name}:rows={len(self.rows)}"


@dataclass(frozen=True, slots=True)
class AreaStrainShellResponseRow:
    object_name: str
    element_name: str
    point_element_name: str
    load_case: str
    step_type: str
    step_number: float
    e11_top: float
    e22_top: float
    g12_top: float
    emax_top: float
    emin_top: float
    eangle_top: float
    evm_top: float
    e11_bottom: float
    e22_bottom: float
    g12_bottom: float
    emax_bottom: float
    emin_bottom: float
    eangle_bottom: float
    evm_bottom: float
    g13_avg: float
    g23_avg: float
    gmax_avg: float
    gangle_avg: float


@dataclass(frozen=True, slots=True)
class AreaStrainShellResponseFact:
    area_name: str
    case_name: str
    rows: tuple[AreaStrainShellResponseRow, ...]
    return_code: int
    source_api: str = "Results.AreaStrainShell"

    @property
    def evidence_ref(self) -> str:
        return f"ETABS:Results.AreaStrainShell:{self.area_name}:{self.case_name}:rows={len(self.rows)}"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank string")
    return value.strip()


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EtabsOAPIError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite")
    return result


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EtabsOAPIError(f"{label} must be a nonnegative integer")
    return int(value)


def _seq(value: object, label: str, count: int) -> tuple[object, ...]:
    if not isinstance(value, (tuple, list)) or len(value) < count:
        raise EtabsOAPIError(f"{label} must contain at least {count} values")
    return tuple(value[:count])


def _ret(value: object, method: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EtabsOAPIError(f"{method} return code must be an integer")
    if value != 0:
        raise EtabsOAPIError(f"{method} returned nonzero code {value}")
    return int(value)


def decode_frame_force_response(raw: object, *, frame_name: str, case_name: str) -> FrameForceResponseFact:
    frame = _text(frame_name, "frame_name")
    case = _text(case_name, "case_name")
    if not isinstance(raw, (tuple, list)) or len(raw) != 15:
        raise EtabsOAPIError(f"Results.FrameForce returned unexpected ABI shape: {raw!r}")
    count = _count(raw[0], "FrameForce.NumberResults")
    arrays = tuple(_seq(raw[index], f"FrameForce[{index}]", count) for index in range(1, 14))
    ret = _ret(raw[14], "Results.FrameForce")
    rows: list[FrameForceResponseRow] = []
    for index in range(count):
        obj = _text(arrays[0][index], "FrameForce.Obj")
        load_case = _text(arrays[4][index], "FrameForce.LoadCase")
        if obj != frame or load_case != case:
            raise EtabsOAPIError(
                f"Results.FrameForce binding mismatch at row {index}: object={obj!r}, case={load_case!r}"
            )
        rows.append(
            FrameForceResponseRow(
                object_name=obj,
                object_station=_finite(arrays[1][index], "FrameForce.ObjSta"),
                element_name=_text(arrays[2][index], "FrameForce.Elm"),
                element_station=_finite(arrays[3][index], "FrameForce.ElmSta"),
                load_case=load_case,
                step_type=str(arrays[5][index] or ""),
                step_number=_finite(arrays[6][index], "FrameForce.StepNum"),
                p=_finite(arrays[7][index], "FrameForce.P"),
                v2=_finite(arrays[8][index], "FrameForce.V2"),
                v3=_finite(arrays[9][index], "FrameForce.V3"),
                t=_finite(arrays[10][index], "FrameForce.T"),
                m2=_finite(arrays[11][index], "FrameForce.M2"),
                m3=_finite(arrays[12][index], "FrameForce.M3"),
            )
        )
    if not rows:
        raise EtabsOAPIError(f"Results.FrameForce returned no rows for {frame!r}/{case!r}")
    return FrameForceResponseFact(frame, case, tuple(rows), ret)


def decode_area_force_shell_response(raw: object, *, area_name: str, case_name: str) -> AreaForceShellResponseFact:
    area = _text(area_name, "area_name")
    case = _text(case_name, "case_name")
    if not isinstance(raw, (tuple, list)) or len(raw) != 25:
        raise EtabsOAPIError(f"Results.AreaForceShell returned unexpected ABI shape: {raw!r}")
    count = _count(raw[0], "AreaForceShell.NumberResults")
    arrays = tuple(_seq(raw[index], f"AreaForceShell[{index}]", count) for index in range(1, 24))
    ret = _ret(raw[24], "Results.AreaForceShell")
    rows: list[AreaForceShellResponseRow] = []
    for index in range(count):
        obj = _text(arrays[0][index], "AreaForceShell.Obj")
        load_case = _text(arrays[3][index], "AreaForceShell.LoadCase")
        if obj != area or load_case != case:
            raise EtabsOAPIError(
                f"Results.AreaForceShell binding mismatch at row {index}: object={obj!r}, case={load_case!r}"
            )
        rows.append(
            AreaForceShellResponseRow(
                object_name=obj,
                element_name=_text(arrays[1][index], "AreaForceShell.Elm"),
                point_element_name=_text(arrays[2][index], "AreaForceShell.PointElm"),
                load_case=load_case,
                step_type=str(arrays[4][index] or ""),
                step_number=_finite(arrays[5][index], "AreaForceShell.StepNum"),
                f11=_finite(arrays[6][index], "AreaForceShell.F11"),
                f22=_finite(arrays[7][index], "AreaForceShell.F22"),
                f12=_finite(arrays[8][index], "AreaForceShell.F12"),
                m11=_finite(arrays[13][index], "AreaForceShell.M11"),
                m22=_finite(arrays[14][index], "AreaForceShell.M22"),
                m12=_finite(arrays[15][index], "AreaForceShell.M12"),
                v13=_finite(arrays[19][index], "AreaForceShell.V13"),
                v23=_finite(arrays[20][index], "AreaForceShell.V23"),
            )
        )
    if not rows:
        raise EtabsOAPIError(f"Results.AreaForceShell returned no rows for {area!r}/{case!r}")
    return AreaForceShellResponseFact(area, case, tuple(rows), ret)


def decode_area_strain_shell_response(raw: object, *, area_name: str, case_name: str) -> AreaStrainShellResponseFact:
    """Decode only the documented AreaStrainShell ABI; no shell mechanics are inferred here."""
    area = _text(area_name, "area_name")
    case = _text(case_name, "case_name")
    if not isinstance(raw, (tuple, list)) or len(raw) != 26:
        raise EtabsOAPIError(f"Results.AreaStrainShell returned unexpected ABI shape: {raw!r}")
    count = _count(raw[0], "AreaStrainShell.NumberResults")
    arrays = tuple(_seq(raw[index], f"AreaStrainShell[{index}]", count) for index in range(1, 25))
    ret = _ret(raw[25], "Results.AreaStrainShell")
    rows: list[AreaStrainShellResponseRow] = []
    for index in range(count):
        obj = _text(arrays[0][index], "AreaStrainShell.Obj")
        load_case = _text(arrays[3][index], "AreaStrainShell.LoadCase")
        if obj != area or load_case != case:
            raise EtabsOAPIError(
                f"Results.AreaStrainShell binding mismatch at row {index}: object={obj!r}, case={load_case!r}"
            )
        rows.append(
            AreaStrainShellResponseRow(
                object_name=obj,
                element_name=_text(arrays[1][index], "AreaStrainShell.Elm"),
                point_element_name=_text(arrays[2][index], "AreaStrainShell.PointElm"),
                load_case=load_case,
                step_type=str(arrays[4][index] or ""),
                step_number=_finite(arrays[5][index], "AreaStrainShell.StepNum"),
                e11_top=_finite(arrays[6][index], "AreaStrainShell.e11top"),
                e22_top=_finite(arrays[7][index], "AreaStrainShell.e22top"),
                g12_top=_finite(arrays[8][index], "AreaStrainShell.g12top"),
                emax_top=_finite(arrays[9][index], "AreaStrainShell.emaxtop"),
                emin_top=_finite(arrays[10][index], "AreaStrainShell.emintop"),
                eangle_top=_finite(arrays[11][index], "AreaStrainShell.eangletop"),
                evm_top=_finite(arrays[12][index], "AreaStrainShell.evmtop"),
                e11_bottom=_finite(arrays[13][index], "AreaStrainShell.e11bot"),
                e22_bottom=_finite(arrays[14][index], "AreaStrainShell.e22bot"),
                g12_bottom=_finite(arrays[15][index], "AreaStrainShell.g12bot"),
                emax_bottom=_finite(arrays[16][index], "AreaStrainShell.emaxbot"),
                emin_bottom=_finite(arrays[17][index], "AreaStrainShell.eminbot"),
                eangle_bottom=_finite(arrays[18][index], "AreaStrainShell.eanglebot"),
                evm_bottom=_finite(arrays[19][index], "AreaStrainShell.evmbot"),
                g13_avg=_finite(arrays[20][index], "AreaStrainShell.g13avg"),
                g23_avg=_finite(arrays[21][index], "AreaStrainShell.g23avg"),
                gmax_avg=_finite(arrays[22][index], "AreaStrainShell.gmaxavg"),
                gangle_avg=_finite(arrays[23][index], "AreaStrainShell.gangleavg"),
            )
        )
    if not rows:
        raise EtabsOAPIError(f"Results.AreaStrainShell returned no rows for {area!r}/{case!r}")
    return AreaStrainShellResponseFact(area, case, tuple(rows), ret)


def probe_eq713_response_results_capability_from_session(
    session: EtabsVerifiedSession,
    *,
    require_frame: bool,
    require_area: bool,
    timeout_seconds: float = 30.0,
) -> tuple[str, ...]:
    """Prove required Results methods and reversible Results.Setup surface exist."""
    def acquire(_etabs_object: object, sap_model: Any) -> tuple[str, ...]:
        results = getattr(sap_model, "Results", None)
        if results is None:
            raise EtabsOAPIError("SapModel.Results is unavailable")
        required = []
        if require_frame:
            required.append("FrameForce")
        if require_area:
            required.append("AreaStrainShell")
        for name in required:
            if not callable(getattr(results, name, None)):
                raise EtabsOAPIError(f"Results.{name} is unavailable")
        with ResultsSetupReadTransaction(sap_model):
            pass
        return tuple(f"ETABS:Results.{name}:AVAILABLE" for name in required)

    return _execute_verified_read(
        session,
        acquire,
        operation="eq713_response_results_capability_probe",
        timeout_seconds=timeout_seconds,
    )


def read_frame_force_response_from_session(
    session: EtabsVerifiedSession,
    *,
    frame_name: str,
    case_name: str,
    timeout_seconds: float = 30.0,
) -> FrameForceResponseFact:
    frame = _text(frame_name, "frame_name")
    case = _text(case_name, "case_name")

    def acquire(_etabs_object: object, sap_model: Any) -> FrameForceResponseFact:
        results = getattr(sap_model, "Results", None)
        method = getattr(results, "FrameForce", None)
        if not callable(method):
            raise EtabsOAPIError("Results.FrameForce is unavailable")
        with ResultsSetupReadTransaction(sap_model) as transaction:
            transaction.select_case(case)
            raw = method(frame, _OBJECT_ELM)
        return decode_frame_force_response(raw, frame_name=frame, case_name=case)

    return _execute_verified_read(
        session,
        acquire,
        operation=f"eq713_frame_force_response:{frame}:{case}",
        timeout_seconds=timeout_seconds,
    )


def read_area_force_shell_response_from_session(
    session: EtabsVerifiedSession,
    *,
    area_name: str,
    case_name: str,
    timeout_seconds: float = 30.0,
) -> AreaForceShellResponseFact:
    area = _text(area_name, "area_name")
    case = _text(case_name, "case_name")

    def acquire(_etabs_object: object, sap_model: Any) -> AreaForceShellResponseFact:
        results = getattr(sap_model, "Results", None)
        method = getattr(results, "AreaForceShell", None)
        if not callable(method):
            raise EtabsOAPIError("Results.AreaForceShell is unavailable")
        with ResultsSetupReadTransaction(sap_model) as transaction:
            transaction.select_case(case)
            raw = method(area, _OBJECT_ELM)
        return decode_area_force_shell_response(raw, area_name=area, case_name=case)

    return _execute_verified_read(
        session,
        acquire,
        operation=f"eq713_area_force_shell_response:{area}:{case}",
        timeout_seconds=timeout_seconds,
    )


def read_area_strain_shell_response_from_session(
    session: EtabsVerifiedSession,
    *,
    area_name: str,
    case_name: str,
    timeout_seconds: float = 30.0,
) -> AreaStrainShellResponseFact:
    area = _text(area_name, "area_name")
    case = _text(case_name, "case_name")

    def acquire(_etabs_object: object, sap_model: Any) -> AreaStrainShellResponseFact:
        results = getattr(sap_model, "Results", None)
        method = getattr(results, "AreaStrainShell", None)
        if not callable(method):
            raise EtabsOAPIError("Results.AreaStrainShell is unavailable")
        with ResultsSetupReadTransaction(sap_model) as transaction:
            transaction.select_case(case)
            raw = method(area, _OBJECT_ELM)
        return decode_area_strain_shell_response(raw, area_name=area, case_name=case)

    return _execute_verified_read(
        session,
        acquire,
        operation=f"eq713_area_strain_shell_response:{area}:{case}",
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "AreaForceShellResponseFact",
    "AreaForceShellResponseRow",
    "AreaStrainShellResponseFact",
    "AreaStrainShellResponseRow",
    "FrameForceResponseFact",
    "FrameForceResponseRow",
    "decode_area_force_shell_response",
    "decode_area_strain_shell_response",
    "decode_frame_force_response",
    "probe_eq713_response_results_capability_from_session",
    "read_area_force_shell_response_from_session",
    "read_area_strain_shell_response_from_session",
    "read_frame_force_response_from_session",
]
