"""Legacy ETABS attach compatibility surface.

Production COM/STA/session/attach ownership has moved to ``etabs_gateway``.
This module intentionally contains no COM discovery implementation. The legacy
``attach_to_running_etabs`` name remains only as a diagnostic compatibility
delegation: it invokes the gateway owner, captures plain attach diagnostics,
closes the gateway session, and returns no usable application/SapModel
capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from etabs_gateway import ConnectionRequest, ETABSGatewaySession
from etabs_gateway.errors import ETABSGatewayError

ATTACH_STATUS_ATTACHED = "ATTACHED"
ATTACH_STATUS_FAILED = "FAILED"
ATTEMPT_STATUS_SUCCESS = "SUCCESS"
ATTEMPT_STATUS_FAILED = "FAILED"
ATTEMPT_STATUS_SKIPPED = "SKIPPED"

STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS = "comtypes_create_helper_get_object_process"
ATTACH_STRATEGIES: tuple[str, ...] = (
    STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS,
    "comtypes_get_active_object_etabs_api_object",
    "comtypes_create_helper_get_object",
    "win32com_get_active_object_etabs_api_object",
)
CANDIDATE_PROG_IDS: tuple[str, ...] = (
    "CSI.ETABS.API.ETABSObject",
    "CSI.ETABS.API.ETABSObject.1",
    "ETABSv1.Helper",
)
LEGACY_COMPATIBILITY_ONLY = True

_ALLOWED_ATTACH_STATUSES = frozenset({ATTACH_STATUS_ATTACHED, ATTACH_STATUS_FAILED})
_ALLOWED_ATTEMPT_STATUSES = frozenset(
    {ATTEMPT_STATUS_SUCCESS, ATTEMPT_STATUS_FAILED, ATTEMPT_STATUS_SKIPPED}
)


@dataclass(frozen=True, slots=True)
class EtabsAttachAttempt:
    strategy: str
    status: str
    message: str
    exception_type: str | None = None
    hresult: str | None = None
    prog_id: str | None = None
    pid: int | None = None

    def __post_init__(self) -> None:
        if self.strategy not in ATTACH_STRATEGIES:
            raise ValueError("Unsupported ETABS attach strategy")
        if self.status not in _ALLOWED_ATTEMPT_STATUSES:
            raise ValueError("Unsupported ETABS attach attempt status")
        if not self.message:
            raise ValueError("EtabsAttachAttempt.message is required")

    def as_dict(self) -> dict[str, object]:
        return {
            "exception_type": self.exception_type,
            "hresult": self.hresult,
            "message": self.message,
            "pid": self.pid,
            "prog_id": self.prog_id,
            "status": self.status,
            "strategy": self.strategy,
        }


@dataclass(frozen=True, slots=True)
class EtabsAttachResult:
    """Legacy diagnostic DTO; raw capability fields are permanently empty."""

    status: str
    strategy: str | None
    etabs_object: Any | None
    sap_model: Any | None
    attempts: tuple[EtabsAttachAttempt, ...]

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_ATTACH_STATUSES:
            raise ValueError("Unsupported ETABS attach result status")
        if self.status == ATTACH_STATUS_ATTACHED and self.strategy not in ATTACH_STRATEGIES:
            raise ValueError("Attached ETABS result requires a successful strategy")
        if self.status == ATTACH_STATUS_FAILED and self.strategy is not None:
            raise ValueError("Failed ETABS attach result must not name a successful strategy")
        if self.etabs_object is not None or self.sap_model is not None:
            raise ValueError(
                "legacy compatibility result must not expose ETABS application/SapModel capability"
            )
        object.__setattr__(self, "attempts", tuple(self.attempts))

    def as_diagnostic_dict(self) -> dict[str, object]:
        return {
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "status": self.status,
            "strategy": self.strategy,
            "legacy_compatibility_only": True,
            "raw_capability_exposed": False,
        }


class EtabsAttachFailure(RuntimeError):
    """Compatibility error carrying only non-COM diagnostics."""

    def __init__(self, attach_result: EtabsAttachResult) -> None:
        super().__init__("No ETABS gateway attach strategy succeeded.")
        self.attach_result = attach_result


class _InjectedCOMApartmentModule:
    COINIT_APARTMENTTHREADED = 2

    def CoInitializeEx(self, flags: int) -> None:
        del flags

    def CoUninitialize(self) -> None:
        return None


def _injected_apartment_loader() -> object:
    return _InjectedCOMApartmentModule()


def _attempts_from_diagnostics(value: object) -> tuple[EtabsAttachAttempt, ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    attempts: list[EtabsAttachAttempt] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        strategy = str(raw.get("strategy") or "")
        if strategy not in ATTACH_STRATEGIES:
            continue
        status = str(raw.get("status") or ATTEMPT_STATUS_FAILED)
        if status not in _ALLOWED_ATTEMPT_STATUSES:
            status = ATTEMPT_STATUS_FAILED
        attempts.append(
            EtabsAttachAttempt(
                strategy=strategy,
                status=status,
                message=str(raw.get("message") or "gateway attach attempt"),
                exception_type=(
                    None if raw.get("exception_type") is None else str(raw.get("exception_type"))
                ),
                hresult=None if raw.get("hresult") is None else str(raw.get("hresult")),
                prog_id=None if raw.get("prog_id") is None else str(raw.get("prog_id")),
                pid=(
                    int(raw["pid"])
                    if isinstance(raw.get("pid"), int) and not isinstance(raw.get("pid"), bool)
                    else None
                ),
            )
        )
    return tuple(attempts)


def attach_to_running_etabs(
    *,
    pid: int | None = None,
    allow_pid_fallback: bool = True,
    comtypes_client: Any | None = None,
    win32com_client: Any | None = None,
) -> EtabsAttachResult:
    """Delegate attach diagnostics to the sole gateway owner and return no COM.

    This compatibility API is not a supported acquisition path. New production
    code must use ``tbdy_engine.etabs.safety.attach_verified_to_running_etabs``.
    """
    injected = comtypes_client is not None or win32com_client is not None
    runtime_loader = (
        (lambda: win32com_client)
        if win32com_client is not None and comtypes_client is None
        else None
    )
    comtypes_loader = (lambda: comtypes_client) if comtypes_client is not None else None
    session = ETABSGatewaySession(
        com_module_loader=_injected_apartment_loader if injected else None,
        runtime_loader=runtime_loader,
        comtypes_loader=comtypes_loader,
    )
    request = ConnectionRequest(
        target_process_id=pid,
        require_exact_process_match=(not allow_pid_fallback if pid is not None else True),
    )
    status = ATTACH_STATUS_FAILED
    strategy: str | None = None
    diagnostics: dict[str, object] = {}
    try:
        session.start(request)
        diagnostics = dict(session.attach_diagnostics)
        candidate = diagnostics.get("strategy")
        strategy = str(candidate) if candidate in ATTACH_STRATEGIES else None
        status = ATTACH_STATUS_ATTACHED if strategy is not None else ATTACH_STATUS_FAILED
    except ETABSGatewayError:
        diagnostics = dict(session.attach_diagnostics)
    finally:
        try:
            session.close()
        except Exception:
            pass
    return EtabsAttachResult(
        status=status,
        strategy=strategy if status == ATTACH_STATUS_ATTACHED else None,
        etabs_object=None,
        sap_model=None,
        attempts=_attempts_from_diagnostics(diagnostics.get("attempts")),
    )


__all__ = [
    "ATTACH_STATUS_ATTACHED",
    "ATTACH_STATUS_FAILED",
    "ATTACH_STRATEGIES",
    "ATTEMPT_STATUS_FAILED",
    "ATTEMPT_STATUS_SKIPPED",
    "ATTEMPT_STATUS_SUCCESS",
    "CANDIDATE_PROG_IDS",
    "EtabsAttachAttempt",
    "EtabsAttachFailure",
    "EtabsAttachResult",
    "LEGACY_COMPATIBILITY_ONLY",
    "STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS",
    "attach_to_running_etabs",
]
