"""Typed factual ETABS Area modifier ABI for B4B section-stiffness mutation.

This module preserves the CSI distinction between:
- AreaObj modifier assignments on named Area objects, and
- PropArea modifier assignments on named Area properties.

The vector is preserved as an exact ten-value indexed factual payload. CSI
documents the PropArea slot meanings, but A5-I0 intentionally does not promote
those property-level slot names into AreaObj slot semantics.

This module owns no engineering participation policy and exposes no raw COM
capability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
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


AREA_MODIFIER_VECTOR_CONTRACT = "ETABS_AREA_MODIFIER_VECTOR_V1"
AREA_MODIFIER_READ_FACT_CONTRACT = "ETABS_AREA_MODIFIER_READ_FACT_V1"
AREA_MODIFIER_SET_FACT_CONTRACT = "ETABS_AREA_MODIFIER_SET_FACT_V1"
AREA_MODIFIER_EVIDENCE_PREFIX = "etabs-area-modifier:sha256:"
_AREA_OBJECT_ITEM_TYPE_OBJECTS = 0


class AreaModifierSurface(StrEnum):
    AREA_OBJECT = "AREA_OBJECT"
    AREA_PROPERTY = "AREA_PROPERTY"


class AreaPropertyModifierSlot(IntEnum):
    """CSI-documented PropArea modifier indices only.

    This enum MUST NOT be interpreted as proving AreaObj slot semantics.
    """

    MEMBRANE_F11 = 0
    MEMBRANE_F22 = 1
    MEMBRANE_F12 = 2
    BENDING_M11 = 3
    BENDING_M22 = 4
    BENDING_M12 = 5
    SHEAR_V13 = 6
    SHEAR_V23 = 7
    MASS = 8
    WEIGHT = 9


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
    return AREA_MODIFIER_EVIDENCE_PREFIX + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class AreaModifierVector:
    """Exact ten-value indexed Area modifier payload with no engineering policy."""

    values: tuple[float, ...]
    contract: str

    def __init__(
        self,
        values: Sequence[object],
        *,
        contract: str = AREA_MODIFIER_VECTOR_CONTRACT,
    ) -> None:
        if contract != AREA_MODIFIER_VECTOR_CONTRACT:
            raise EtabsOAPIError("area modifier vector contract mismatch")
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise EtabsOAPIError("area modifier vector must be a sequence")
        data = tuple(values)
        if len(data) != 10:
            raise EtabsOAPIError(
                f"area modifier vector must contain exactly 10 values; got {len(data)}"
            )
        normalized = tuple(
            _number(value, f"modifier[{index}]")
            for index, value in enumerate(data)
        )
        object.__setattr__(self, "values", normalized)
        object.__setattr__(self, "contract", contract)

    @classmethod
    def from_sequence(cls, values: Sequence[object]) -> "AreaModifierVector":
        return cls(values)

    def as_tuple(self) -> tuple[float, ...]:
        return self.values

    def as_list(self) -> list[float]:
        return list(self.values)

    def property_slot(self, slot: AreaPropertyModifierSlot) -> float:
        """Read one CSI-documented PropArea slot by index.

        The caller remains responsible for ensuring that the vector came from
        AreaModifierSurface.AREA_PROPERTY.
        """
        if not isinstance(slot, AreaPropertyModifierSlot):
            raise TypeError("slot must be AreaPropertyModifierSlot")
        return self.values[int(slot)]


@dataclass(frozen=True, slots=True)
class AreaModifierReadFact:
    surface: AreaModifierSurface
    target_name: str
    modifiers: AreaModifierVector
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = AREA_MODIFIER_READ_FACT_CONTRACT

    def __post_init__(self) -> None:
        if not isinstance(self.surface, AreaModifierSurface):
            raise TypeError("surface must be AreaModifierSurface")
        object.__setattr__(
            self, "target_name", _text(self.target_name, "target_name")
        )
        if not isinstance(self.modifiers, AreaModifierVector):
            raise TypeError("modifiers must be AreaModifierVector")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be an integer")
        if self.contract != AREA_MODIFIER_READ_FACT_CONTRACT:
            raise EtabsOAPIError("area modifier read fact contract mismatch")
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
class AreaModifierSetFact:
    surface: AreaModifierSurface
    target_name: str
    requested_modifiers: AreaModifierVector
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = AREA_MODIFIER_SET_FACT_CONTRACT

    def __post_init__(self) -> None:
        if not isinstance(self.surface, AreaModifierSurface):
            raise TypeError("surface must be AreaModifierSurface")
        object.__setattr__(
            self, "target_name", _text(self.target_name, "target_name")
        )
        if not isinstance(self.requested_modifiers, AreaModifierVector):
            raise TypeError("requested_modifiers must be AreaModifierVector")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be an integer")
        if self.contract != AREA_MODIFIER_SET_FACT_CONTRACT:
            raise EtabsOAPIError("area modifier set fact contract mismatch")
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


def _vector_candidate(value: object) -> AreaModifierVector | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    try:
        return AreaModifierVector.from_sequence(value)
    except (EtabsOAPIError, TypeError, ValueError):
        return None


def _decode_get_response(
    raw: object,
    *,
    method: str,
) -> tuple[AreaModifierVector, int]:
    if not isinstance(raw, (tuple, list)):
        raise EtabsOAPIError(
            f"{method} returned unsupported Python ABI shape: "
            f"{type(raw).__name__}"
        )
    items = tuple(raw)
    vector_candidates = tuple(
        candidate
        for candidate in (_vector_candidate(item) for item in items)
        if candidate is not None
    )
    ret_candidates = tuple(
        int(item) for item in items if type(item) is int
    )
    if len(vector_candidates) != 1 or len(ret_candidates) != 1:
        raise EtabsOAPIError(
            f"{method} returned ambiguous/unsupported Python ABI shape: {raw!r}"
        )
    return vector_candidates[0], ret_candidates[0]


def _decode_set_response(
    raw: object,
    *,
    method: str,
    requested: AreaModifierVector,
) -> int:
    if type(raw) is int:
        return int(raw)
    if not isinstance(raw, (tuple, list)):
        raise EtabsOAPIError(
            f"{method} returned unsupported Python ABI shape: "
            f"{type(raw).__name__}"
        )

    items = tuple(raw)
    ret_candidates = tuple(
        int(item) for item in items if type(item) is int
    )
    if len(ret_candidates) != 1:
        raise EtabsOAPIError(
            f"{method} returned ambiguous/unsupported return-code shape: {raw!r}"
        )

    reflected: list[AreaModifierVector] = []
    for item in items:
        if type(item) is int:
            continue
        candidate = _vector_candidate(item)
        if candidate is None:
            raise EtabsOAPIError(
                f"{method} returned unsupported reflected ByRef payload: {raw!r}"
            )
        reflected.append(candidate)

    if len(reflected) > 1:
        raise EtabsOAPIError(
            f"{method} returned ambiguous reflected ByRef vectors: {raw!r}"
        )
    if reflected and reflected[0].as_tuple() != requested.as_tuple():
        raise EtabsOAPIError(
            f"{method} returned mismatched reflected ByRef payload: {raw!r}"
        )
    return ret_candidates[0]


def _container(model_api: Any, surface: AreaModifierSurface) -> Any:
    if surface is AreaModifierSurface.AREA_OBJECT:
        return model_api.AreaObj
    if surface is AreaModifierSurface.AREA_PROPERTY:
        return model_api.PropArea
    raise TypeError("unsupported area modifier surface")


def get_area_modifiers_from_session(
    session: EtabsVerifiedSession,
    *,
    surface: AreaModifierSurface,
    target_name: str,
    timeout_seconds: float = 30.0,
) -> AreaModifierReadFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(surface, AreaModifierSurface):
        raise TypeError("surface must be AreaModifierSurface")
    target = _text(target_name, "target_name")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    method = (
        "AreaObj.GetModifiers"
        if surface is AreaModifierSurface.AREA_OBJECT
        else "PropArea.GetModifiers"
    )

    def acquire(
        _application: object,
        model_api: Any,
    ) -> AreaModifierReadFact:
        raw = _container(model_api, surface).GetModifiers(target)
        modifiers, return_code = _decode_get_response(raw, method=method)
        return AreaModifierReadFact(
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


def set_area_modifiers_from_session(
    session: EtabsVerifiedSession,
    *,
    surface: AreaModifierSurface,
    target_name: str,
    modifiers: AreaModifierVector,
    timeout_seconds: float = 30.0,
) -> AreaModifierSetFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(surface, AreaModifierSurface):
        raise TypeError("surface must be AreaModifierSurface")
    if not isinstance(modifiers, AreaModifierVector):
        raise TypeError("modifiers must be AreaModifierVector")
    target = _text(target_name, "target_name")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    method = (
        "AreaObj.SetModifiers"
        if surface is AreaModifierSurface.AREA_OBJECT
        else "PropArea.SetModifiers"
    )

    def mutate(model_api: Any) -> AreaModifierSetFact:
        container = _container(model_api, surface)
        payload = modifiers.as_list()
        if surface is AreaModifierSurface.AREA_OBJECT:
            raw = container.SetModifiers(
                target,
                payload,
                _AREA_OBJECT_ITEM_TYPE_OBJECTS,
            )
        else:
            raw = container.SetModifiers(target, payload)
        return_code = _decode_set_response(
            raw,
            method=method,
            requested=modifiers,
        )
        return AreaModifierSetFact(
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
    "AREA_MODIFIER_EVIDENCE_PREFIX",
    "AREA_MODIFIER_READ_FACT_CONTRACT",
    "AREA_MODIFIER_SET_FACT_CONTRACT",
    "AREA_MODIFIER_VECTOR_CONTRACT",
    "AreaModifierReadFact",
    "AreaModifierSetFact",
    "AreaModifierSurface",
    "AreaModifierVector",
    "AreaPropertyModifierSlot",
    "get_area_modifiers_from_session",
    "set_area_modifiers_from_session",
]
