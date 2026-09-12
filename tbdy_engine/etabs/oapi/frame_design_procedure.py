"""Exact CSI FrameObj.GetDesignProcedure ABI for Column-R1 factual acquisition.

This module owns only CSI invocation, positional return decoding, return-code
validation, and typed factual transport. Column-R1 interpretation of procedure
codes belongs to the factual provider above this layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError

FRAME_DESIGN_PROCEDURE_API = "FrameObj.GetDesignProcedure"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _names(values: Sequence[str]) -> tuple[str, ...]:
    names = tuple(_text(item, "frame_name") for item in values)
    if not names or len(names) != len(set(names)):
        raise EtabsOAPIError("frame_names must be a nonempty unique sequence")
    return names


@dataclass(frozen=True, slots=True)
class FrameDesignProcedureFact:
    frame_name: str
    procedure_code: int
    raw_response: tuple[object, object]
    source_api: str = FRAME_DESIGN_PROCEDURE_API

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_name", _text(self.frame_name, "frame_name"))
        if isinstance(self.procedure_code, bool) or not isinstance(self.procedure_code, int):
            raise EtabsOAPIError("FrameObj.GetDesignProcedure procedure code must be exact int")
        if not isinstance(self.raw_response, tuple) or len(self.raw_response) != 2:
            raise EtabsOAPIError(
                "FrameObj.GetDesignProcedure raw response must preserve the exact 2-tuple"
            )
        if self.source_api != FRAME_DESIGN_PROCEDURE_API:
            raise EtabsOAPIError("frame design-procedure source API mismatch")


def decode_frame_design_procedure_response(
    raw: object,
    *,
    frame_name: str,
) -> FrameDesignProcedureFact:
    """Decode ``FrameObj.GetDesignProcedure(Name, ref MyType) -> int`` exactly.

    The supported Python COM ABI is the two-member tuple
    ``(MyType, return_code)``. Semantic meaning of ``MyType`` is not decided in
    OAPI; the caller receives the exact integer factual value.
    """
    requested = _text(frame_name, "frame_name")
    if not isinstance(raw, tuple) or len(raw) != 2:
        raise EtabsOAPIError(
            "FrameObj.GetDesignProcedure returned unsupported Python COM shape; "
            "expected exact (MyType, return_code) tuple"
        )
    procedure_raw, ret = raw
    if isinstance(procedure_raw, bool) or not isinstance(procedure_raw, int):
        raise EtabsOAPIError(
            "FrameObj.GetDesignProcedure MyType must be an exact integer"
        )
    if isinstance(ret, bool) or not isinstance(ret, int) or ret != 0:
        raise EtabsOAPIError(
            f"FrameObj.GetDesignProcedure({requested!r}) returned nonzero/invalid code {ret!r}"
        )
    return FrameDesignProcedureFact(
        frame_name=requested,
        procedure_code=int(procedure_raw),
        raw_response=raw,
    )


def read_frame_design_procedure(
    frame_obj: Any,
    frame_name: str,
) -> FrameDesignProcedureFact:
    requested = _text(frame_name, "frame_name")
    getter = getattr(frame_obj, "GetDesignProcedure", None)
    if not callable(getter):
        raise EtabsOAPIError("FrameObj.GetDesignProcedure is unavailable")
    try:
        raw = getter(requested)
    except Exception as exc:
        raise EtabsOAPIError(
            f"FrameObj.GetDesignProcedure({requested!r}) raised {type(exc).__name__}: {exc}"
        ) from exc
    return decode_frame_design_procedure_response(raw, frame_name=requested)


def read_frame_design_procedures_from_session(
    session: EtabsVerifiedSession,
    frame_names: Sequence[str],
    *,
    timeout_seconds: float = 30.0,
) -> tuple[FrameDesignProcedureFact, ...]:
    """Read one factual design procedure for every requested frame via safety."""
    names = _names(frame_names)
    return _execute_verified_read(
        session,
        lambda _app, sap: tuple(
            read_frame_design_procedure(sap.FrameObj, name) for name in names
        ),
        operation="oapi_frame_get_design_procedures",
        timeout_seconds=float(timeout_seconds),
    )


__all__ = [
    "FRAME_DESIGN_PROCEDURE_API",
    "FrameDesignProcedureFact",
    "decode_frame_design_procedure_response",
    "read_frame_design_procedure",
    "read_frame_design_procedures_from_session",
]
