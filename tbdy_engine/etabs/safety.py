"""Canonical factual ETABS safety boundary.

This public module preserves the accepted unit/state/transaction implementation
while moving verified-session ownership onto ``packages/etabs_gateway``. Raw
ETABS application/SapModel references never appear in ``EtabsVerifiedSession``
or any public return value.

The pre-migration implementation is retained privately in ``_safety_legacy``
only so the already-reviewed state-transaction code can be reused byte-for-byte
until normal regression validation permits physical retirement.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, TypeVar

from etabs_gateway import ConnectionRequest, ETABSGatewaySession
from etabs_gateway.errors import ETABSGatewayError

from ._safety_legacy import (
    AnalysisCaseReadiness,
    AnalysisReadiness,
    CapabilityState,
    DatabaseTablesReadTransaction,
    DatabaseTablesSelectionSnapshot,
    EtabsCapabilityError,
    EtabsCapabilitySnapshot,
    EtabsIdentityMismatchError,
    EtabsSafetyError,
    EtabsSafetyErrorCode,
    EtabsSessionIdentity,
    EtabsStateMutationKind,
    EtabsStateRestoreError,
    EtabsStateVerificationError,
    EtabsUnitSnapshot,
    ResultsSetupReadTransaction,
    ResultsSetupSelectionSnapshot,
    RuntimeCaptureStatus,
    _decode_database_selected_names,
    classify_capture_status,
    process_local_acquisition_lock,
    read_analysis_readiness,
    read_capability_snapshot,
    read_etabs_unit_snapshot,
    read_session_identity,
    verify_target_model,
)

T = TypeVar("T")

_GATEWAY_PID_STRATEGY = "comtypes_create_helper_get_object_process"


class _InjectedCOMApartmentModule:
    """No-op apartment shim for explicit injected test/runtime clients only."""

    COINIT_APARTMENTTHREADED = 2

    def CoInitializeEx(self, flags: int) -> None:
        del flags

    def CoUninitialize(self) -> None:
        return None


def _injected_apartment_loader() -> object:
    return _InjectedCOMApartmentModule()


def _as_attempts(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _gateway_pid_capability(diagnostics: Mapping[str, object]) -> CapabilityState:
    strategy = diagnostics.get("strategy")
    if strategy == _GATEWAY_PID_STRATEGY:
        return CapabilityState.SUPPORTED

    attempts = tuple(
        item
        for item in _as_attempts(diagnostics.get("attempts"))
        if item.get("strategy") == _GATEWAY_PID_STRATEGY
    )
    if not attempts:
        return CapabilityState.UNKNOWN
    if any(item.get("status") == "SUCCESS" for item in attempts):
        return CapabilityState.SUPPORTED

    for item in attempts:
        exception_type = str(item.get("exception_type") or "")
        message = str(item.get("message") or "")
        if exception_type == "AttributeError" and "GetObjectProcess" in message:
            return CapabilityState.UNSUPPORTED
        if "does not expose callable GetObjectProcess" in message:
            return CapabilityState.UNSUPPORTED

    # A concrete GetObjectProcess invocation that failed with another runtime
    # error proves that the method exists even though the requested attach did
    # not succeed.
    if any(item.get("pid") is not None for item in attempts):
        return CapabilityState.SUPPORTED
    return CapabilityState.UNKNOWN


def _gateway_error_code(
    exc: ETABSGatewayError,
    *,
    requested_pid: int | None,
) -> EtabsSafetyErrorCode:
    details = dict(getattr(exc, "details", {}) or {})
    stage = details.get("stage")
    if requested_pid is not None and stage == "pid_attach":
        return EtabsSafetyErrorCode.PID_ATTACH_FAILED
    if requested_pid is not None:
        capability = _gateway_pid_capability(details)
        if capability is CapabilityState.UNSUPPORTED:
            return EtabsSafetyErrorCode.PID_ATTACH_UNSUPPORTED
    return EtabsSafetyErrorCode.ATTACH_FAILED


@dataclass(frozen=True, slots=True)
class EtabsVerifiedSession:
    """Verified ETABS session with no public raw COM capability.

    The gateway object is deliberately private and excluded from repr/equality.
    Safety and OAPI may submit bounded reads through the module-private helper;
    application/integration consumers receive only immutable factual metadata.
    """

    identity: EtabsSessionIdentity
    capabilities: EtabsCapabilitySnapshot
    diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    _gateway_session: ETABSGatewaySession = field(repr=False, compare=False, default=None)  # type: ignore[assignment]
    _attach_diagnostics: Mapping[str, object] = field(
        repr=False,
        compare=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.identity, EtabsSessionIdentity):
            raise TypeError("identity must be EtabsSessionIdentity")
        if not isinstance(self.capabilities, EtabsCapabilitySnapshot):
            raise TypeError("capabilities must be EtabsCapabilitySnapshot")
        if not isinstance(self._gateway_session, ETABSGatewaySession):
            raise TypeError("verified session requires an ETABSGatewaySession")
        object.__setattr__(
            self,
            "diagnostics",
            tuple(dict(item) for item in self.diagnostics),
        )
        object.__setattr__(self, "_attach_diagnostics", dict(self._attach_diagnostics))

    def close(self, *, timeout_seconds: float = 5.0) -> bool:
        """Close the owning gateway session without exposing its COM objects."""
        return self._gateway_session.close(timeout_seconds=timeout_seconds)


def _execute_verified_read(
    session: EtabsVerifiedSession,
    function: Callable[[object, object], T],
    *,
    operation: str,
    timeout_seconds: float = 30.0,
) -> T:
    """Safety/OAPI-only bridge into the gateway-owned STA execution boundary."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    return session._gateway_session.execute_bounded_read(
        function,
        operation=operation,
        timeout_seconds=timeout_seconds,
    )


def reread_verified_session_identity(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> EtabsSessionIdentity:
    """Re-read identity through the private gateway capability and return facts."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    return _execute_verified_read(
        session,
        lambda etabs_object, sap_model: read_session_identity(
            etabs_object,
            sap_model,
            process_id=session.identity.process_id,
            attach_strategy=session.identity.attach_strategy,
        ),
        operation="verified_session_identity_reread",
        timeout_seconds=timeout_seconds,
    )


def read_verified_unit_snapshot(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> EtabsUnitSnapshot:
    """Read current unit provenance without exporting SapModel."""
    return _execute_verified_read(
        session,
        lambda _etabs_object, sap_model: read_etabs_unit_snapshot(sap_model),
        operation="verified_session_unit_snapshot",
        timeout_seconds=timeout_seconds,
    )


def attach_verified_to_running_etabs(
    expected_model_full_path: str,
    *,
    pid: int | None = None,
    allow_pid_fallback: bool = False,
    comtypes_client: Any | None = None,
    win32com_client: Any | None = None,
) -> EtabsVerifiedSession:
    """Attach through the sole gateway owner, then hard-verify exact identity.

    ``comtypes_client``/``win32com_client`` remain bounded injection seams for
    existing offline tests. Production calls omit them and use the gateway's
    normal lazy Windows COM loaders.
    """
    injected = comtypes_client is not None or win32com_client is not None

    # When both historical test clients are supplied, leave the win32 loader at
    # its normal non-strict setting so a deliberately failing win32 fake cannot
    # suppress the injected comtypes fallback. A sole win32 injection remains
    # supported as a strict runtime seam.
    runtime_loader = (
        (lambda: win32com_client)
        if win32com_client is not None and comtypes_client is None
        else None
    )
    comtypes_loader = (
        (lambda: comtypes_client)
        if comtypes_client is not None
        else None
    )
    gateway = ETABSGatewaySession(
        com_module_loader=_injected_apartment_loader if injected else None,
        runtime_loader=runtime_loader,
        comtypes_loader=comtypes_loader,
    )
    request = ConnectionRequest(
        target_process_id=pid,
        require_exact_process_match=(not allow_pid_fallback if pid is not None else True),
    )

    try:
        gateway.start(request)
    except ETABSGatewayError as exc:
        code = _gateway_error_code(exc, requested_pid=pid)
        raise EtabsSafetyError(
            str(exc),
            code=code,
            details={
                "gateway_code": exc.code,
                "gateway_operation": exc.operation,
                "gateway_details": dict(exc.details),
            },
        ) from exc

    attach_diagnostics = dict(gateway.attach_diagnostics)
    strategy_raw = attach_diagnostics.get("strategy")
    strategy = str(strategy_raw) if strategy_raw is not None else None
    process_raw = attach_diagnostics.get("process_id")
    process_id = (
        int(process_raw)
        if isinstance(process_raw, int) and not isinstance(process_raw, bool) and process_raw > 0
        else None
    )

    try:
        identity = gateway.execute_bounded_read(
            lambda etabs_object, sap_model: read_session_identity(
                etabs_object,
                sap_model,
                process_id=process_id,
                attach_strategy=strategy,
            ),
            operation="verified_session_identity_read",
        )
        verify_target_model(identity, expected_model_full_path)
        capabilities = gateway.execute_bounded_read(
            lambda _etabs_object, sap_model: read_capability_snapshot(sap_model),
            operation="verified_session_capability_read",
        )
    except Exception:
        try:
            gateway.close()
        finally:
            pass
        raise

    pid_capability = _gateway_pid_capability(attach_diagnostics)
    capabilities = replace(capabilities, pid_attach=pid_capability)

    diagnostics: list[dict[str, Any]] = []
    if pid is not None and strategy != _GATEWAY_PID_STRATEGY:
        if pid_capability is CapabilityState.UNSUPPORTED:
            diagnostics.append({
                "code": EtabsSafetyErrorCode.PID_ATTACH_UNSUPPORTED.value,
                "requested_pid": int(pid),
                "fallback_used": True,
            })
        elif pid_capability is CapabilityState.SUPPORTED:
            diagnostics.append({
                "code": EtabsSafetyErrorCode.PID_ATTACH_FAILED.value,
                "requested_pid": int(pid),
                "fallback_used": True,
                "compatibility_opt_in": bool(allow_pid_fallback),
            })

    return EtabsVerifiedSession(
        identity=identity,
        capabilities=capabilities,
        diagnostics=tuple(diagnostics),
        _gateway_session=gateway,
        _attach_diagnostics=attach_diagnostics,
    )


__all__ = [
    "AnalysisCaseReadiness",
    "AnalysisReadiness",
    "CapabilityState",
    "DatabaseTablesReadTransaction",
    "DatabaseTablesSelectionSnapshot",
    "EtabsCapabilityError",
    "EtabsCapabilitySnapshot",
    "EtabsIdentityMismatchError",
    "EtabsSafetyError",
    "EtabsSafetyErrorCode",
    "EtabsSessionIdentity",
    "EtabsStateMutationKind",
    "EtabsStateRestoreError",
    "EtabsStateVerificationError",
    "EtabsUnitSnapshot",
    "EtabsVerifiedSession",
    "ResultsSetupReadTransaction",
    "ResultsSetupSelectionSnapshot",
    "RuntimeCaptureStatus",
    "attach_verified_to_running_etabs",
    "classify_capture_status",
    "process_local_acquisition_lock",
    "read_analysis_readiness",
    "read_capability_snapshot",
    "read_etabs_unit_snapshot",
    "read_session_identity",
    "read_verified_unit_snapshot",
    "reread_verified_session_identity",
    "verify_target_model",
]
