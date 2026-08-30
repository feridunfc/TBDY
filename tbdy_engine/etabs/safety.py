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
import threading
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
_PRIVATE_COMPATIBILITY_IMPLEMENTATION_DEBT = "PRIVATE_COMPATIBILITY_IMPLEMENTATION_DEBT"


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
    """Verified ETABS session with no public raw COM capability."""

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
        object.__setattr__(self, "diagnostics", tuple(dict(item) for item in self.diagnostics))
        object.__setattr__(self, "_attach_diagnostics", dict(self._attach_diagnostics))

    def close(self, *, timeout_seconds: float = 5.0) -> bool:
        return self._gateway_session.close(timeout_seconds=timeout_seconds)


@dataclass(frozen=True, slots=True)
class VerifiedSTAExecutionFact:
    """Factual proof that a bounded read executed on the gateway worker thread."""

    worker_thread_id: int
    executing_thread_id: int
    gateway_state: str
    worker_state: str

    @property
    def exact_worker_thread_match(self) -> bool:
        return self.worker_thread_id == self.executing_thread_id


@dataclass(frozen=True, slots=True)
class VerifiedResultsSetupTransactionFact:
    """Typed proof of one temporary Results.Setup selection and exact restoration."""

    selection_kind: str
    selection_name: str
    before: ResultsSetupSelectionSnapshot
    after: ResultsSetupSelectionSnapshot
    diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    @property
    def restoration_verified_exact(self) -> bool:
        return self.before == self.after



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
    return _execute_verified_read(
        session,
        lambda _etabs_object, sap_model: read_etabs_unit_snapshot(sap_model),
        operation="verified_session_unit_snapshot",
        timeout_seconds=timeout_seconds,
    )


def read_verified_analysis_readiness(
    session: EtabsVerifiedSession,
    case_name: str,
    *,
    timeout_seconds: float = 30.0,
) -> AnalysisCaseReadiness:
    """Read factual analysis readiness without running analysis."""
    return _execute_verified_read(
        session,
        lambda _etabs_object, sap_model: read_analysis_readiness(sap_model, case_name),
        operation="verified_session_analysis_readiness",
        timeout_seconds=timeout_seconds,
    )


def read_verified_database_tables_selection(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> DatabaseTablesSelectionSnapshot:
    """Snapshot DatabaseTables selection through its safety-owned transaction."""

    def acquire(_etabs_object: object, sap_model: Any) -> DatabaseTablesSelectionSnapshot:
        with DatabaseTablesReadTransaction(sap_model.DatabaseTables) as transaction:
            snapshot = transaction.snapshot
            if snapshot is None:
                raise EtabsCapabilityError(
                    "DatabaseTables selection snapshot was not captured.",
                    code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
                )
            return snapshot

    return _execute_verified_read(
        session,
        acquire,
        operation="verified_database_tables_selection_snapshot",
        timeout_seconds=timeout_seconds,
    )


def read_verified_results_setup_selection(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> ResultsSetupSelectionSnapshot:
    """Snapshot Results.Setup selection through its independent safety transaction."""

    def acquire(_etabs_object: object, sap_model: Any) -> ResultsSetupSelectionSnapshot:
        with ResultsSetupReadTransaction(sap_model) as transaction:
            snapshot = transaction.snapshot
            if snapshot is None:
                raise EtabsCapabilityError(
                    "Results.Setup selection snapshot was not captured.",
                    code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
                )
            return snapshot

    return _execute_verified_read(
        session,
        acquire,
        operation="verified_results_setup_selection_snapshot",
        timeout_seconds=timeout_seconds,
    )


def read_verified_sta_execution_fact(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> VerifiedSTAExecutionFact:
    """Prove that a bounded factual callback executes on the gateway-owned STA."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    context = session._gateway_session.context
    if context is None:
        raise EtabsSafetyError(
            "verified gateway session has no factual context",
            code=EtabsSafetyErrorCode.ATTACH_FAILED,
        )
    executing_thread_id = _execute_verified_read(
        session,
        lambda _etabs_object, _sap_model: threading.get_ident(),
        operation="verified_sta_execution_probe",
        timeout_seconds=timeout_seconds,
    )
    fact = VerifiedSTAExecutionFact(
        worker_thread_id=int(context.attachment.worker_thread_id),
        executing_thread_id=int(executing_thread_id),
        gateway_state=session._gateway_session.state.value,
        worker_state=session._gateway_session.worker_state.value,
    )
    if not fact.exact_worker_thread_match:
        raise EtabsStateVerificationError(
            "bounded ETABS callback did not execute on the gateway worker thread",
            code=EtabsSafetyErrorCode.TEMPORARY_STATE_VERIFY_FAILED,
            details={
                "worker_thread_id": fact.worker_thread_id,
                "executing_thread_id": fact.executing_thread_id,
            },
        )
    return fact


def exercise_verified_results_setup_selection(
    session: EtabsVerifiedSession,
    *,
    case_name: str | None = None,
    combo_name: str | None = None,
    timeout_seconds: float = 30.0,
) -> VerifiedResultsSetupTransactionFact:
    """Exercise one reversible Results.Setup selection entirely inside safety/STA.

    Exactly one case or combo is required. If restoration fails, the transaction
    exception is propagated immediately and no verification read is attempted.
    """
    case = str(case_name or "").strip()
    combo = str(combo_name or "").strip()
    if bool(case) == bool(combo):
        raise ValueError("exactly one of case_name or combo_name is required")

    def acquire(_etabs_object: object, sap_model: Any) -> VerifiedResultsSetupTransactionFact:
        transaction = ResultsSetupReadTransaction(sap_model)
        with transaction:
            before = transaction.snapshot
            if before is None:
                raise EtabsCapabilityError(
                    "Results.Setup selection snapshot was not captured.",
                    code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
                )
            if case:
                transaction.select_case(case)
                selection_kind = "case"
                selection_name = case
            else:
                transaction.select_combo(combo)
                selection_kind = "combo"
                selection_name = combo

        # This block is intentionally reached only after the first transaction
        # restored successfully. A known restoration failure aborts immediately.
        verification = ResultsSetupReadTransaction(sap_model)
        with verification:
            after = verification.snapshot
            if after is None:
                raise EtabsCapabilityError(
                    "Results.Setup restoration verification snapshot was not captured.",
                    code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
                )

        if before != after:
            raise EtabsStateRestoreError(
                "Results.Setup selection did not restore exactly after verified transaction.",
                code=EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED,
            )
        return VerifiedResultsSetupTransactionFact(
            selection_kind=selection_kind,
            selection_name=selection_name,
            before=before,
            after=after,
            diagnostics=tuple(dict(item) for item in transaction.diagnostics),
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="verified_results_setup_temporary_selection",
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
    """Attach through the sole gateway owner, then hard-verify exact identity."""
    injected = comtypes_client is not None or win32com_client is not None
    runtime_loader = (
        (lambda: win32com_client)
        if win32com_client is not None and comtypes_client is None
        else None
    )
    comtypes_loader = (lambda: comtypes_client) if comtypes_client is not None else None
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
    "VerifiedResultsSetupTransactionFact",
    "VerifiedSTAExecutionFact",
    "attach_verified_to_running_etabs",
    "classify_capture_status",
    "exercise_verified_results_setup_selection",
    "process_local_acquisition_lock",
    "read_analysis_readiness",
    "read_capability_snapshot",
    "read_etabs_unit_snapshot",
    "read_session_identity",
    "read_verified_analysis_readiness",
    "read_verified_database_tables_selection",
    "read_verified_results_setup_selection",
    "read_verified_sta_execution_fact",
    "read_verified_unit_snapshot",
    "reread_verified_session_identity",
    "verify_target_model",
]
