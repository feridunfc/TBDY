"""Typed factual ETABS frame modifier ABI for B4B analysis-state mutation.

This module preserves the CSI distinction between:
- FrameObj modifier assignments on named frame objects, and
- PropFrame modifier assignments on named frame section properties.

It does not claim either surface is an effective/composed stiffness modifier.
It performs no engineering policy selection and exposes no raw COM capability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import math
from typing import Any, Sequence

from etabs_gateway.mutation_transport import (
    _B4T_MUTATION_TRANSPORT_KEY,
    _execute_bounded_model_mutation,
)

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError


FRAME_MODIFIER_VECTOR_CONTRACT = "ETABS_FRAME_MODIFIER_VECTOR_V1"
FRAME_MODIFIER_READ_FACT_CONTRACT = "ETABS_FRAME_MODIFIER_READ_FACT_V1"
FRAME_MODIFIER_SET_FACT_CONTRACT = "ETABS_FRAME_MODIFIER_SET_FACT_V1"
FRAME_MODIFIER_EVIDENCE_PREFIX = "etabs-frame-modifier:sha256:"
_FRAME_OBJECT_ITEM_TYPE_OBJECTS = 0


class FrameModifierSurface(StrEnum):
    FRAME_OBJECT = "FRAME_OBJECT"
    FRAME_SECTION_PROPERTY = "FRAME_SECTION_PROPERTY"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    return result


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return FRAME_MODIFIER_EVIDENCE_PREFIX + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class FrameModifierVector:
    """The documented eight-entry frame modifier vector, preserving CSI order."""

    area: float
    shear_area_local_2: float
    shear_area_local_3: float
    torsional_constant: float
    inertia_local_2: float
    inertia_local_3: float
    mass: float
    weight: float
    contract: str = FRAME_MODIFIER_VECTOR_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != FRAME_MODIFIER_VECTOR_CONTRACT:
            raise EtabsOAPIError("frame modifier vector contract mismatch")
        for name in (
            "area",
            "shear_area_local_2",
            "shear_area_local_3",
            "torsional_constant",
            "inertia_local_2",
            "inertia_local_3",
            "mass",
            "weight",
        ):
            object.__setattr__(self, name, _number(getattr(self, name), name))

    @classmethod
    def from_sequence(cls, values: Sequence[object]) -> "FrameModifierVector":
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise EtabsOAPIError("frame modifier vector must be a sequence")
        data = tuple(values)
        if len(data) != 8:
            raise EtabsOAPIError(
                f"frame modifier vector must contain exactly 8 values; got {len(data)}"
            )
        return cls(*(_number(value, f"modifier[{index}]") for index, value in enumerate(data)))

    def as_tuple(self) -> tuple[float, ...]:
        return (
            self.area,
            self.shear_area_local_2,
            self.shear_area_local_3,
            self.torsional_constant,
            self.inertia_local_2,
            self.inertia_local_3,
            self.mass,
            self.weight,
        )

    def as_list(self) -> list[float]:
        return list(self.as_tuple())


@dataclass(frozen=True, slots=True)
class FrameModifierReadFact:
    surface: FrameModifierSurface
    target_name: str
    modifiers: FrameModifierVector
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = FRAME_MODIFIER_READ_FACT_CONTRACT

    def __post_init__(self) -> None:
        if not isinstance(self.surface, FrameModifierSurface):
            raise TypeError("surface must be FrameModifierSurface")
        object.__setattr__(self, "target_name", _text(self.target_name, "target_name"))
        if not isinstance(self.modifiers, FrameModifierVector):
            raise TypeError("modifiers must be FrameModifierVector")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be an integer")
        if self.contract != FRAME_MODIFIER_READ_FACT_CONTRACT:
            raise EtabsOAPIError("frame modifier read fact contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "contract": self.contract,
                    "surface": self.surface.value,
                    "target_name": self.target_name,
                    "modifiers": self.modifiers.as_list(),
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class FrameModifierSetFact:
    surface: FrameModifierSurface
    target_name: str
    requested_modifiers: FrameModifierVector
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = FRAME_MODIFIER_SET_FACT_CONTRACT

    def __post_init__(self) -> None:
        if not isinstance(self.surface, FrameModifierSurface):
            raise TypeError("surface must be FrameModifierSurface")
        object.__setattr__(self, "target_name", _text(self.target_name, "target_name"))
        if not isinstance(self.requested_modifiers, FrameModifierVector):
            raise TypeError("requested_modifiers must be FrameModifierVector")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be an integer")
        if self.contract != FRAME_MODIFIER_SET_FACT_CONTRACT:
            raise EtabsOAPIError("frame modifier set fact contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "contract": self.contract,
                    "surface": self.surface.value,
                    "target_name": self.target_name,
                    "requested_modifiers": self.requested_modifiers.as_list(),
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


def _vector_candidate(value: object) -> FrameModifierVector | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    try:
        return FrameModifierVector.from_sequence(value)
    except (EtabsOAPIError, TypeError, ValueError):
        return None


def _decode_get_response(raw: object, *, method: str) -> tuple[FrameModifierVector, int]:
    if not isinstance(raw, (tuple, list)):
        raise EtabsOAPIError(
            f"{method} returned unsupported Python ABI shape: {type(raw).__name__}"
        )
    items = tuple(raw)
    vector_candidates = tuple(
        candidate
        for candidate in (_vector_candidate(item) for item in items)
        if candidate is not None
    )
    ret_candidates = tuple(int(item) for item in items if type(item) is int)
    if len(vector_candidates) != 1 or len(ret_candidates) != 1:
        raise EtabsOAPIError(
            f"{method} returned ambiguous/unsupported Python ABI shape: {raw!r}"
        )
    return vector_candidates[0], ret_candidates[0]


def _decode_set_response(
    raw: object,
    *,
    method: str,
    requested: FrameModifierVector,
) -> int:
    if type(raw) is int:
        return int(raw)
    if not isinstance(raw, (tuple, list)):
        raise EtabsOAPIError(
            f"{method} returned unsupported Python ABI shape: {type(raw).__name__}"
        )
    items = tuple(raw)
    ret_candidates = tuple(int(item) for item in items if type(item) is int)
    if len(ret_candidates) != 1:
        raise EtabsOAPIError(
            f"{method} returned ambiguous/unsupported return-code shape: {raw!r}"
        )
    for item in items:
        if type(item) is int:
            continue
        candidate = _vector_candidate(item)
        if candidate is None or candidate.as_tuple() != requested.as_tuple():
            raise EtabsOAPIError(
                f"{method} returned unsupported reflected ByRef payload: {raw!r}"
            )
    return ret_candidates[0]


def _container(model_api: Any, surface: FrameModifierSurface) -> Any:
    if surface is FrameModifierSurface.FRAME_OBJECT:
        return model_api.FrameObj
    if surface is FrameModifierSurface.FRAME_SECTION_PROPERTY:
        return model_api.PropFrame
    raise TypeError("unsupported frame modifier surface")


def get_frame_modifiers_from_session(
    session: EtabsVerifiedSession,
    *,
    surface: FrameModifierSurface,
    target_name: str,
    timeout_seconds: float = 30.0,
) -> FrameModifierReadFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(surface, FrameModifierSurface):
        raise TypeError("surface must be FrameModifierSurface")
    target = _text(target_name, "target_name")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    method = (
        "FrameObj.GetModifiers"
        if surface is FrameModifierSurface.FRAME_OBJECT
        else "PropFrame.GetModifiers"
    )

    def acquire(_application: object, model_api: Any) -> FrameModifierReadFact:
        raw = _container(model_api, surface).GetModifiers(target)
        modifiers, return_code = _decode_get_response(raw, method=method)
        return FrameModifierReadFact(
            surface=surface,
            target_name=target,
            modifiers=modifiers,
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation=f"oapi_{surface.value.lower()}_get_modifiers",
        timeout_seconds=timeout,
    )


def set_frame_modifiers_from_session(
    session: EtabsVerifiedSession,
    *,
    surface: FrameModifierSurface,
    target_name: str,
    modifiers: FrameModifierVector,
    timeout_seconds: float = 30.0,
) -> FrameModifierSetFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(surface, FrameModifierSurface):
        raise TypeError("surface must be FrameModifierSurface")
    if not isinstance(modifiers, FrameModifierVector):
        raise TypeError("modifiers must be FrameModifierVector")
    target = _text(target_name, "target_name")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    method = (
        "FrameObj.SetModifiers"
        if surface is FrameModifierSurface.FRAME_OBJECT
        else "PropFrame.SetModifiers"
    )

    def mutate(model_api: Any) -> FrameModifierSetFact:
        container = _container(model_api, surface)
        payload = modifiers.as_list()
        if surface is FrameModifierSurface.FRAME_OBJECT:
            raw = container.SetModifiers(target, payload, _FRAME_OBJECT_ITEM_TYPE_OBJECTS)
        else:
            raw = container.SetModifiers(target, payload)
        return_code = _decode_set_response(raw, method=method, requested=modifiers)
        return FrameModifierSetFact(
            surface=surface,
            target_name=target,
            requested_modifiers=modifiers,
            return_code=return_code,
        )

    return _execute_bounded_model_mutation(
        session._gateway_session,  # noqa: SLF001 - trusted OAPI -> B4T boundary
        mutate,
        operation=f"oapi_{surface.value.lower()}_set_modifiers",
        timeout_seconds=timeout,
        _transport_key=_B4T_MUTATION_TRANSPORT_KEY,
    )


__all__ = [
    "FRAME_MODIFIER_EVIDENCE_PREFIX",
    "FRAME_MODIFIER_READ_FACT_CONTRACT",
    "FRAME_MODIFIER_SET_FACT_CONTRACT",
    "FRAME_MODIFIER_VECTOR_CONTRACT",
    "FrameModifierReadFact",
    "FrameModifierSetFact",
    "FrameModifierSurface",
    "FrameModifierVector",
    "get_frame_modifiers_from_session",
    "set_frame_modifiers_from_session",
]
