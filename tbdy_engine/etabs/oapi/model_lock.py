"""Typed factual ETABS model-lock ABI for owned-scratch lifecycle transitions.

This module owns only the exact SapModel.SetModelIsLocked call boundary.
It does not decide when an unlock is permitted, what the removed case universe
means, or whether any analysis result is authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from etabs_gateway.mutation_transport import (
    _B4T_MUTATION_TRANSPORT_KEY,
    _execute_bounded_model_mutation,
)

from tbdy_engine.etabs.safety import EtabsVerifiedSession

from .contracts import EtabsOAPIError


MODEL_LOCK_SET_FACT_CONTRACT = "ETABS_MODEL_LOCK_SET_FACT_V1"
MODEL_LOCK_EVIDENCE_PREFIX = "etabs-model-lock:sha256:"


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return MODEL_LOCK_EVIDENCE_PREFIX + hashlib.sha256(encoded).hexdigest()


def _return_code(value: object) -> int:
    if type(value) is int:
        return int(value)
    if isinstance(value, (tuple, list)):
        if len(value) == 1 and type(value[0]) is int:
            return int(value[0])
    raise EtabsOAPIError(
        "SapModel.SetModelIsLocked returned unsupported return-code ABI "
        f"shape: {value!r}"
    )


@dataclass(frozen=True, slots=True)
class ModelLockSetFact:
    requested_locked: bool
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = MODEL_LOCK_SET_FACT_CONTRACT

    def __post_init__(self) -> None:
        if type(self.requested_locked) is not bool:
            raise EtabsOAPIError("requested_locked must be bool")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be int")
        if self.contract != MODEL_LOCK_SET_FACT_CONTRACT:
            raise EtabsOAPIError("model-lock set fact contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "contract": self.contract,
                    "requested_locked": self.requested_locked,
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


def set_model_lock_from_session(
    session: EtabsVerifiedSession,
    *,
    locked: bool,
    timeout_seconds: float = 30.0,
) -> ModelLockSetFact:
    """Set the ETABS model lock through the existing gateway STA transport."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if type(locked) is not bool:
        raise TypeError("locked must be bool")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def mutate(model_api: Any) -> ModelLockSetFact:
        raw = model_api.SetModelIsLocked(locked)
        return ModelLockSetFact(
            requested_locked=locked,
            return_code=_return_code(raw),
        )

    return _execute_bounded_model_mutation(
        session._gateway_session,
        mutate,
        operation="oapi_set_model_is_locked",
        timeout_seconds=timeout,
        _transport_key=_B4T_MUTATION_TRANSPORT_KEY,
    )


__all__ = [
    "MODEL_LOCK_SET_FACT_CONTRACT",
    "MODEL_LOCK_EVIDENCE_PREFIX",
    "ModelLockSetFact",
    "set_model_lock_from_session",
]
