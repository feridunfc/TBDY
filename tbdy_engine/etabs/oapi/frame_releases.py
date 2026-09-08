"""Typed factual ``FrameObj.GetReleases`` read boundary.

ETABS API fact discipline for COLUMN-R1 A3:

``DOCUMENTED FACT``
    ``FrameObj.GetReleases`` retrieves four six-entry arrays named ``II``,
    ``JJ``, ``StartValue`` and ``EndValue`` for a named frame object.

``INFERENCE``
    The paired ``FrameObj.SetReleases`` documentation assigns the six release
    positions to P/V2/V3/T/M2/M3.  The supplied ``GetReleases`` page does not
    itself restate those slot meanings.  This factual module therefore does
    *not* expose named release-DOF attributes and does not promote the paired
    setter mapping into a documented getter fact.

No engineering participation or TS500 Eq. 7.13 qualification is owned here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Sequence

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError


FRAME_RELEASE_FACT_CONTRACT = "ETABS_FRAME_RELEASE_FACT_V1"
FRAME_RELEASE_EVIDENCE_PREFIX = "etabs-frame-release:sha256:"
FRAME_RELEASE_SLOT_SEMANTICS = "NOT_PROVEN_FROM_GETRELEASES_DOCUMENTATION"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _bool_vector(value: object, label: str) -> tuple[bool, bool, bool, bool, bool, bool]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EtabsOAPIError(f"{label} must be a six-entry boolean sequence")
    data = tuple(value)
    if len(data) != 6:
        raise EtabsOAPIError(f"{label} must contain exactly 6 boolean values")
    if any(type(item) is not bool for item in data):
        raise EtabsOAPIError(f"{label} must contain boolean values only")
    return data  # type: ignore[return-value]


def _numeric_vector(value: object, label: str) -> tuple[float, float, float, float, float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EtabsOAPIError(f"{label} must be a six-entry finite numeric sequence")
    data = tuple(value)
    if len(data) != 6:
        raise EtabsOAPIError(f"{label} must contain exactly 6 finite numeric values")
    result: list[float] = []
    for index, item in enumerate(data):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise EtabsOAPIError(f"{label}[{index}] must be finite numeric")
        number = float(item)
        if not math.isfinite(number):
            raise EtabsOAPIError(f"{label}[{index}] must be finite numeric")
        result.append(number)
    return tuple(result)  # type: ignore[return-value]


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return FRAME_RELEASE_EVIDENCE_PREFIX + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class FrameReleaseFact:
    """Exact getter arrays with deliberately unnamed slot positions."""

    frame_name: str
    i_end_released: tuple[bool, bool, bool, bool, bool, bool]
    j_end_released: tuple[bool, bool, bool, bool, bool, bool]
    i_end_partial_fixity: tuple[float, float, float, float, float, float]
    j_end_partial_fixity: tuple[float, float, float, float, float, float]
    return_code: int
    evidence_ref: str = field(init=False)
    slot_semantics: str = FRAME_RELEASE_SLOT_SEMANTICS
    contract: str = FRAME_RELEASE_FACT_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_name", _text(self.frame_name, "frame_name"))
        object.__setattr__(
            self,
            "i_end_released",
            _bool_vector(self.i_end_released, "i_end_released"),
        )
        object.__setattr__(
            self,
            "j_end_released",
            _bool_vector(self.j_end_released, "j_end_released"),
        )
        object.__setattr__(
            self,
            "i_end_partial_fixity",
            _numeric_vector(self.i_end_partial_fixity, "i_end_partial_fixity"),
        )
        object.__setattr__(
            self,
            "j_end_partial_fixity",
            _numeric_vector(self.j_end_partial_fixity, "j_end_partial_fixity"),
        )
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be an integer")
        if self.slot_semantics != FRAME_RELEASE_SLOT_SEMANTICS:
            raise EtabsOAPIError("frame release slot-semantic classification mismatch")
        if self.contract != FRAME_RELEASE_FACT_CONTRACT:
            raise EtabsOAPIError("frame release fact contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "contract": self.contract,
                    "frame_name": self.frame_name,
                    "i_end_released": self.i_end_released,
                    "j_end_released": self.j_end_released,
                    "i_end_partial_fixity": self.i_end_partial_fixity,
                    "j_end_partial_fixity": self.j_end_partial_fixity,
                    "return_code": self.return_code,
                    "slot_semantics": self.slot_semantics,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


def _decode_get_releases(raw: object) -> tuple[
    tuple[bool, bool, bool, bool, bool, bool],
    tuple[bool, bool, bool, bool, bool, bool],
    tuple[float, float, float, float, float, float],
    tuple[float, float, float, float, float, float],
    int,
]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 5:
        raise EtabsOAPIError(
            f"FrameObj.GetReleases returned unsupported Python ABI shape: {raw!r}"
        )
    i_release, j_release, start_value, end_value, return_code = tuple(raw)
    if type(return_code) is not int:
        raise EtabsOAPIError(
            f"FrameObj.GetReleases returned unsupported Python ABI shape: {raw!r}"
        )
    try:
        return (
            _bool_vector(i_release, "FrameObj.GetReleases.II"),
            _bool_vector(j_release, "FrameObj.GetReleases.JJ"),
            _numeric_vector(start_value, "FrameObj.GetReleases.StartValue"),
            _numeric_vector(end_value, "FrameObj.GetReleases.EndValue"),
            int(return_code),
        )
    except EtabsOAPIError as exc:
        raise EtabsOAPIError(
            f"FrameObj.GetReleases returned unsupported Python ABI shape: {raw!r}; {exc}"
        ) from exc


def get_frame_releases_from_session(
    session: EtabsVerifiedSession,
    *,
    frame_name: str,
    timeout_seconds: float = 30.0,
) -> FrameReleaseFact:
    """Retrieve a frame object's factual release arrays through the verified boundary."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(frame_name, "frame_name")
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError("timeout_seconds must be finite and greater than zero")

    def acquire(_application: object, model_api: Any) -> FrameReleaseFact:
        raw = model_api.FrameObj.GetReleases(name)
        i_release, j_release, start_value, end_value, return_code = _decode_get_releases(raw)
        return FrameReleaseFact(
            frame_name=name,
            i_end_released=i_release,
            j_end_released=j_release,
            i_end_partial_fixity=start_value,
            j_end_partial_fixity=end_value,
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_frame_obj_get_releases",
        timeout_seconds=timeout,
    )


__all__ = [
    "FRAME_RELEASE_EVIDENCE_PREFIX",
    "FRAME_RELEASE_FACT_CONTRACT",
    "FRAME_RELEASE_SLOT_SEMANTICS",
    "FrameReleaseFact",
    "get_frame_releases_from_session",
]
