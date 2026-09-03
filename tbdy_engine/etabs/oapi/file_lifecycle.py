"""Bounded factual ETABS file-lifecycle ABI.

This module owns only factual CSI ABI decoding.  It does not decide scratch
ownership, source integrity, engineering state, analysis qualification, or
design qualification.  The only write-state operation exposed here is the
typed ``SapModel.File.OpenFile(exact_path)`` primitive, executed through the
private B4T gateway mutation transport on the already-owned STA worker.

No raw SapModel, application object, child COM proxy, or generic mutation
callback is exposed.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from os import PathLike
from typing import Any

from etabs_gateway.mutation_transport import (
    _B4T_MUTATION_TRANSPORT_KEY,
    _execute_bounded_model_mutation,
)

from tbdy_engine.etabs.safety import EtabsVerifiedSession


OPEN_FILE_FACT_CONTRACT = "ETABS_OAPI_FILE_OPEN_FACT_V1"


class FileLifecycleABIError(RuntimeError):
    """Fail-closed malformed/unsupported ETABS file-lifecycle ABI response."""


def _canonical_absolute_path(value: str | PathLike[str], *, label: str) -> str:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise TypeError(f"{label} must be a filesystem path") from exc
    if not isinstance(raw, str):
        raise TypeError(f"{label} must resolve to a text filesystem path")
    if not raw or raw != raw.strip():
        raise ValueError(f"{label} must be a nonblank canonical path")
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        raise ValueError(f"{label} must be absolute")
    return os.path.normcase(os.path.normpath(os.path.abspath(expanded)))


def _decode_open_file_return(raw: object) -> int:
    # CSI File.OpenFile(FileName) has one input argument and one integer return
    # code.  Any tuple/list/object projection is an unknown ABI shape and must
    # fail closed rather than being guessed.
    if type(raw) is not int:
        raise FileLifecycleABIError(
            "SapModel.File.OpenFile returned an unsupported factual ABI shape: "
            f"{type(raw).__name__}"
        )
    return raw


@dataclass(frozen=True, slots=True)
class OpenFileFact:
    """Immutable factual result of one exact ETABS File.OpenFile call."""

    canonical_requested_path: str
    return_code: int
    contract: str = OPEN_FILE_FACT_CONTRACT

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_requested_path, str) or not self.canonical_requested_path:
            raise FileLifecycleABIError("canonical_requested_path must be nonblank")
        if type(self.return_code) is not int:
            raise FileLifecycleABIError("return_code must be an integer")
        if self.contract != OPEN_FILE_FACT_CONTRACT:
            raise FileLifecycleABIError("OpenFile fact contract mismatch")

    @property
    def success(self) -> bool:
        return self.return_code == 0


def open_file_from_session(
    session: EtabsVerifiedSession,
    exact_path: str | PathLike[str],
    *,
    timeout_seconds: float = 30.0,
) -> OpenFileFact:
    """Call ``SapModel.File.OpenFile`` and return factual success/code only.

    ``OpenFileFact.success`` is an ETABS ABI fact.  It is explicitly not proof
    of owned scratch, source immutability, or causal lifecycle qualification.
    """
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    canonical_path = _canonical_absolute_path(exact_path, label="exact_path")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    raw = _execute_bounded_model_mutation(
        session._gateway_session,  # noqa: SLF001 - trusted OAPI -> B4T boundary
        lambda model_api: model_api.File.OpenFile(canonical_path),
        operation="oapi_file_open_exact_path",
        timeout_seconds=timeout,
        _transport_key=_B4T_MUTATION_TRANSPORT_KEY,
    )
    return OpenFileFact(
        canonical_requested_path=canonical_path,
        return_code=_decode_open_file_return(raw),
    )


__all__ = [
    "FileLifecycleABIError",
    "OPEN_FILE_FACT_CONTRACT",
    "OpenFileFact",
    "open_file_from_session",
]
